"""Regression coverage using PostgreSQL temporary tables."""
import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import HTTPException

from sqlalchemy import text
from sqlalchemy.orm import Session

import api

from db import engine
from monthly_visit_plans import month_window
from reconciliation_engine import calculate_monthly_reconciliation


@unittest.skipUnless(
    os.getenv("KIARAD_TEST_MONTHLY_RECONCILIATION_DB") == "1",
    "Opt-in PostgreSQL test",
)
class MonthlyReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.conn = engine.connect()
        self.addCleanup(self.conn.close)
        statements = (
            "CREATE TEMP TABLE monthly_visit_plans (id integer, month text, salesperson_id integer, user_id integer)",
            """CREATE TEMP TABLE monthly_visit_plan_stops (
                id integer, plan_id integer, visit_date date, base_source text,
                base_id integer, objective text, outcome_status text, order_amount_rial bigint)""",
            """CREATE TEMP TABLE base_checkins (
                salesperson_id integer, checked_in_at timestamp, base_source text,
                base_id integer, status text)""",
            "CREATE TEMP TABLE daily_reports (salesperson_id integer, report_date date)",
            "CREATE TEMP TABLE pharmacies (id integer, name text)",
            "CREATE TEMP TABLE cosmetics_shops (id integer, name text)",
            "CREATE TEMP TABLE kerman_bases_manual (id integer, name text)",
        )
        for statement in statements:
            self.conn.execute(text(statement))

    def test_cutoff_and_confirmed_unplanned_visits(self):
        start, end = month_window("1405-08")
        cutoff = start + timedelta(days=2)
        future = cutoff + timedelta(days=1)
        self.conn.execute(text("INSERT INTO monthly_visit_plans VALUES (1, '1405-08', 10, 100)"))
        self.conn.execute(text("INSERT INTO pharmacies VALUES (8, 'Pharmacy Eight')"))
        self.conn.execute(
            text("""INSERT INTO monthly_visit_plan_stops VALUES
                (1, 1, :start, 'pharmacies', 1, 'follow up', NULL, 0),
                (2, 1, :cutoff, 'pharmacies', 2, 'follow up', 'rescheduled', 200),
                (3, 1, :cutoff, 'pharmacies', 3, 'follow up', NULL, 0),
                (4, 1, :future, 'pharmacies', 4, 'follow up', 'order_placed', 900)"""),
            {"start": start, "cutoff": cutoff, "future": future},
        )
        self.conn.execute(
            text("INSERT INTO daily_reports VALUES (10, :start)"), {"start": start}
        )
        self.conn.execute(
            text("""INSERT INTO base_checkins VALUES
                (10, :start, 'pharmacies', 1, 'verified'),
                (10, :cutoff, 'pharmacies', 8, 'verified'),
                (10, :cutoff, 'pharmacies', 8, 'verified'),
                (10, :cutoff, 'pharmacies', 4, 'verified'),
                (10, :cutoff, 'cosmetics_shops', 4, 'verified'),
                (10, :cutoff, 'pharmacies', 7, 'pending'),
                (10, :before, 'pharmacies', 8, 'verified'),
                (10, :end, 'pharmacies', 8, 'verified'),
                (11, :cutoff, 'pharmacies', 9, 'verified')"""),
            {"start": start, "cutoff": cutoff, "before": start - timedelta(days=1), "end": end},
        )

        report = calculate_monthly_reconciliation(self.conn, 1, cutoff)
        self.assertEqual(report["summary"], {
            "total_planned_up_to_date": 3,
            "on_schedule_count": 1,
            "rescheduled_count": 1,
            "missed_count": 1,
            "unplanned_count": 2,
            "strict_compliance_percent": 33.3,
            "effective_coverage_percent": 66.7,
            "total_orders_rial": 200,
        })
        self.assertEqual(
            [(item["base_source"], item["center_id"], item["center_name"])
             for item in report["buckets"]["unplanned"]],
            [("cosmetics_shops", 4, None), ("pharmacies", 8, "Pharmacy Eight")],
        )
        later_report = calculate_monthly_reconciliation(self.conn, 1, end)
        self.assertEqual(later_report["summary"]["unplanned_count"], 2)
        self.assertEqual(later_report["summary"]["total_planned_up_to_date"], 4)

    def test_reconciliation_and_outcome_respect_plan_ownership(self):
        self.conn.execute(text("INSERT INTO monthly_visit_plans VALUES (1, '1405-08', 10, 100)"))
        self.conn.execute(text("INSERT INTO monthly_visit_plan_stops (id, plan_id) VALUES (1, 1)"))
        colleague = {"id": 101, "role": "visitor"}

        with patch("db.SessionLocal", side_effect=lambda: Session(bind=self.conn)):
            with self.assertRaises(HTTPException) as report_error:
                api.get_plan_reconciliation_4buckets(1, user=colleague)
            with self.assertRaises(HTTPException) as write_error:
                api.record_stop_structured_outcome(1, {}, user=colleague)
            with self.assertRaises(HTTPException) as missing_error:
                api.record_stop_structured_outcome(2, {}, user=colleague)

        self.assertEqual(report_error.exception.status_code, 403)
        self.assertEqual(write_error.exception.status_code, 403)
        self.assertEqual(missing_error.exception.status_code, 404)
