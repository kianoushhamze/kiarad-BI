"""Payroll period and SQL workflow checks in rollback-only temporary tables.

Opt in with KIARAD_TEST_PAYROLL_DB=1. The search path contains only pg_temp;
the real schema is not visible. No real contracts, ledger rows or approvals
are created. Service functions own neither the connection nor the transaction.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
import unittest

from fastapi import HTTPException

import payroll_service as service
from payroll_periods import payroll_period, period_is_approved


class PayrollPeriodTests(unittest.TestCase):
    def test_persian_digits_and_nowruz_half_open_period(self):
        month, start, end, calendar = payroll_period("۱۴۰۵-۰۱")
        self.assertEqual((month, calendar), ("1405-01", "persian"))
        self.assertEqual(start, datetime(2026, 3, 21))
        self.assertEqual(end, datetime(2026, 4, 21))
        self.assertEqual((end - start).days, 31)

    def test_persian_leap_esfand_and_nonleap_esfand(self):
        _, start, end, _ = payroll_period("1403-12")
        self.assertEqual((end - start).days, 30)
        _, start, end, _ = payroll_period("1404-12")
        self.assertEqual((end - start).days, 29)

    def test_legacy_gregorian_period_is_explicitly_labelled(self):
        month, start, end, calendar = payroll_period("2026-10")
        self.assertEqual((month, start, end, calendar),
                         ("2026-10", datetime(2026, 10, 1), datetime(2026, 11, 1), "gregorian"))

    def test_invalid_months_become_validation_errors(self):
        for value in ["1405/07", "1405-13", "1405-00", "1405-7", "1700-01", "", None]:
            with self.subTest(value=value), self.assertRaises(HTTPException) as error:
                service.period(value)
            self.assertEqual(error.exception.status_code, 422)


@unittest.skipUnless(os.getenv("KIARAD_TEST_PAYROLL_DB") == "1", "Opt-in temporary database test")
class PayrollServiceDatabaseTests(unittest.TestCase):
    def setUp(self):
        from db import get_connection

        self.conn = get_connection()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.cur = self.conn.cursor()
        self.addCleanup(self.cur.close)
        self.cur.execute("SET LOCAL search_path TO pg_temp")
        self.cur.execute("SET LOCAL statement_timeout='10s'")
        self.cur.execute("SET LOCAL lock_timeout='3s'")
        for statement in (
            "CREATE TEMP TABLE salespersons(id INTEGER PRIMARY KEY,name TEXT)",
            "CREATE TEMP TABLE users(id INTEGER PRIMARY KEY,role TEXT)",
            """CREATE TEMP TABLE salesperson_contracts(id SERIAL PRIMARY KEY,salesperson_id INTEGER UNIQUE,
                hourly_rate NUMERIC,min_monthly_hours NUMERIC,settlement_commission_percent NUMERIC,
                daily_mission_allowance NUMERIC,per_km_rate NUMERIC)""",
            """CREATE TEMP TABLE salesperson_targets(contract_id INTEGER,target_type TEXT,item_identifier TEXT,
                item_title TEXT,target_amount NUMERIC,target_quantity INTEGER,commission_percent NUMERIC)""",
            """CREATE TEMP TABLE attendance_sessions(id SERIAL PRIMARY KEY,salesperson_id INTEGER,
                start_time TIMESTAMP,end_time TIMESTAMP,duration_hours NUMERIC,is_active BOOLEAN)""",
            """CREATE TEMP TABLE base_checkins(id SERIAL PRIMARY KEY,salesperson_id INTEGER,
                checked_in_at TIMESTAMP,status TEXT)""",
            """CREATE TEMP TABLE payroll_approvals(id SERIAL PRIMARY KEY,salesperson_id INTEGER,
                payroll_month TEXT,worked_hours NUMERIC,verified_visit_days INTEGER,base_pay NUMERIC,
                visit_allowance NUMERIC,additions NUMERIC,deductions NUMERIC,approved_total NUMERIC,
                note TEXT,status TEXT,approved_by INTEGER,approved_at TIMESTAMP,
                UNIQUE(salesperson_id,payroll_month))""",
            "INSERT INTO salespersons VALUES(10,'پرسنل موقت اول'),(11,'پرسنل موقت دوم')",
            "INSERT INTO users VALUES(1,'ceo'),(2,'salesperson')",
        ):
            self.cur.execute(statement)
        service.ensure_payroll_schema(self.cur)
        self.user = {"id": 1, "role": "ceo"}
        self.month = "1405-07"
        _, self.start, self.end, _ = payroll_period(self.month)

    def count(self, table):
        allowed = {"compensation_rule_versions", "compensation_facts", "compensation_source_checks",
                   "payroll_approval_history", "payroll_approvals"}
        self.assertIn(table, allowed)
        self.cur.execute("SELECT COUNT(*) FROM " + table)
        return self.cur.fetchone()[0]

    def save(self, *, approved=True, month=None, person=10, **changes):
        data = {"effective_month": month or self.month, "rules_approved": approved,
                "salary_mode": "hourly", "hourly_rate": 100, "min_monthly_hours": 0, **changes}
        return service.save_contract(self.cur, person, data, self.user)

    def attendance(self, start=None, end=None, person=10, active=False, stored_hours=999):
        start = self.start + timedelta(hours=8) if start is None else start
        end = start + timedelta(hours=2) if end is None and not active else end
        self.cur.execute("""INSERT INTO attendance_sessions(salesperson_id,start_time,end_time,duration_hours,is_active)
            VALUES(%s,%s,%s,%s,%s)""", (person, start, end, stored_hours, active))

    def fact(self, *, key="sale-001", kind="sale", amount=1000, quantity=10, person=10, event_date=None):
        return service.record_fact(self.cur, person, {
            "event_key": key, "kind": kind, "amount": amount, "quantity": quantity,
            "product_id": "7", "brand": "برند موقت", "source_note": "سند آزمایشی در تراکنش موقت",
            "event_date": (event_date or self.start.date()).isoformat(),
        }, self.user)

    def complete(self, source="sales", value=True, person=10, month=None):
        self.cur.execute("""INSERT INTO compensation_source_checks(salesperson_id,payroll_month,source,
            complete,note,verified_by) VALUES(%s,%s,%s,%s,%s,1)
            ON CONFLICT(salesperson_id,payroll_month,source) DO UPDATE SET complete=EXCLUDED.complete""",
            (person, month or self.month, source, value, "تطبیق موقت منبع آزمایشی"))

    def codes(self, result):
        return {item["code"] for item in result["blockers"]}

    def test_schema_is_idempotent_and_every_relation_is_temporary(self):
        saved = self.save()
        service.ensure_payroll_schema(self.cur)
        self.assertEqual(self.count("compensation_rule_versions"), 1)
        self.assertEqual(service.get_contract(self.cur, 10, self.month)["rule_version"], saved["rule_version"])
        self.cur.execute("""SELECT c.relname,c.relpersistence FROM pg_class c
            WHERE c.relnamespace=pg_my_temp_schema() AND c.relkind IN ('r','S')""")
        relations = self.cur.fetchall()
        self.assertGreaterEqual(len(relations), 12)
        self.assertTrue(all(persistence == "t" for _, persistence in relations))
        self.cur.execute("SHOW search_path")
        self.assertEqual(self.cur.fetchone()[0], "pg_temp")

    def test_empty_and_legacy_contracts_are_unapproved(self):
        contract = service.get_contract(self.cur, 10, self.month)
        self.assertFalse(contract["configured"])
        self.assertFalse(contract["rules_approved"])
        self.cur.execute("""INSERT INTO salesperson_contracts(salesperson_id,hourly_rate,min_monthly_hours,
            settlement_commission_percent,daily_mission_allowance,per_km_rate) VALUES(10,500,176,0,0,0)""")
        contract = service.get_contract(self.cur, 10, self.month)
        self.assertTrue(contract["configured"])
        self.assertFalse(contract["rules_approved"])
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertIn("rules_not_approved", self.codes(result))
        self.assertFalse(result["can_approve"])

    def test_draft_is_visible_but_cannot_be_used_to_approve_payroll(self):
        saved = self.save(approved=False, hourly_rate=999)
        self.assertFalse(saved["rules_approved"])
        self.assertFalse(service.get_contract(self.cur, 10, self.month)["rules_approved"])
        self.attendance()
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertIn("rules_not_approved", self.codes(result))
        self.assertIsNone(result["rule_version"])
        with self.assertRaises(HTTPException) as error:
            service.approve(self.cur, 10, self.month, {}, self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.count("payroll_approval_history"), 0)

    def test_approved_versions_are_append_only_and_choose_latest_applicable(self):
        first = self.save(hourly_rate=100)
        second = self.save(hourly_rate=200)
        future = self.save(month="1405-08", hourly_rate=300)
        self.assertLess(first["rule_version"], second["rule_version"])
        self.assertLess(second["rule_version"], future["rule_version"])
        self.assertEqual(self.count("compensation_rule_versions"), 3)
        self.assertEqual(service.get_contract(self.cur, 10, self.month)["hourly_rate"], 200)
        self.assertEqual(service.get_contract(self.cur, 10, "1405-08")["hourly_rate"], 300)
        self.cur.execute("SELECT rules_json->>'hourly_rate' FROM compensation_rule_versions WHERE id=%s", (first["rule_version"],))
        self.assertEqual(Decimal(self.cur.fetchone()[0]), Decimal("100"))

    def test_later_draft_never_activates_unapproved_amount(self):
        approved = self.save(hourly_rate=100)
        self.save(approved=False, hourly_rate=999)
        self.attendance()
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual(result["rule_version"], approved["rule_version"])
        self.assertEqual(result["base_pay"], 200)

    def test_unresolved_questions_and_invalid_boolean_cannot_be_approved(self):
        for changes in [{"rules_approved": "true"},
                        {"rules_approved": True, "unresolved_questions": ["مبنای درصد مشخص نیست"]}]:
            with self.subTest(changes=changes), self.assertRaises(HTTPException) as error:
                self.save(**changes)
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.count("compensation_rule_versions"), 0)

    def test_draft_preserves_questions_and_manager_decision_note(self):
        saved = self.save(approved=False, unresolved_questions=["درصد بعد از سقف نیاز به تصمیم دارد"],
                          decision_note="پیش‌نویس برای بررسی مدیر")
        contract = service.get_contract(self.cur, 10, self.month)
        self.assertEqual(contract["rule_version"], saved["rule_version"])
        self.assertEqual(contract["unresolved_questions"], ["درصد بعد از سقف نیاز به تصمیم دارد"])
        self.assertEqual(contract["decision_note"], "پیش‌نویس برای بررسی مدیر")

    def test_unsupported_currency_is_rejected_without_silent_conversion(self):
        for currency in ["IRT", "تومان", "USD", None]:
            with self.subTest(currency=currency), self.assertRaises(HTTPException) as error:
                self.save(currency=currency)
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.count("compensation_rule_versions"), 0)

    def test_cross_month_shift_is_clipped_and_stored_duration_is_not_trusted(self):
        self.save(hourly_rate=100)
        self.attendance(self.start - timedelta(hours=2), self.start + timedelta(hours=3))
        self.attendance(self.end - timedelta(hours=2), self.end + timedelta(hours=5))
        self.attendance(self.start - timedelta(days=2), self.start)
        self.attendance(self.end, self.end + timedelta(hours=3))
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual(result["worked_hours"], 5)
        self.assertEqual(result["base_pay"], 500)
        self.assertEqual(result["calendar"], "persian")
        self.assertEqual(result["period_start"], self.start.isoformat() + "+03:30")
        self.assertEqual(result["period_end"], self.end.isoformat() + "+03:30")

    def test_distinct_verified_visit_days_are_counted_inside_half_open_period(self):
        self.save(hourly_rate=0, daily_mission_allowance=100)
        for timestamp, status in [(self.start, "verified"), (self.start + timedelta(hours=5), "verified"),
                                  (self.start + timedelta(days=1), "verified"),
                                  (self.start + timedelta(days=2), "pending_review"),
                                  (self.end, "verified")]:
            self.cur.execute("INSERT INTO base_checkins(salesperson_id,checked_in_at,status) VALUES(10,%s,%s)",
                             (timestamp, status))
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual(result["verified_visit_days"], 2)
        self.assertEqual(result["verified_visit_allowance"], 200)

    def test_open_overlapping_shift_blocks_approval_future_shift_does_not(self):
        self.save()
        self.attendance(self.end + timedelta(hours=1), active=True)
        self.assertNotIn("open_attendance", self.codes(service.calculate_period(self.cur, 10, self.month)))
        self.attendance(self.start - timedelta(days=1), active=True)
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertIn("open_attendance", self.codes(result))
        with self.assertRaises(HTTPException) as error:
            service.approve(self.cur, 10, self.month, {}, self.user)
        self.assertEqual(error.exception.status_code, 409)

    def test_sources_and_facts_are_scoped_to_person_and_month(self):
        self.save(salary_mode="commission_only", sales_scope="personal", commission_tier_basis="marginal",
                  sales_tiers=[{"up_to_amount": None, "percent": 5}])
        self.fact(amount=1000)
        self.fact(key="other-person-sale", person=11, amount=90000)
        self.fact(key="next-month-sale", amount=90000, event_date=self.end.date())
        self.complete(person=11)
        self.complete(month="1405-08")
        self.assertIn("sales_source_incomplete", self.codes(service.calculate_period(self.cur, 10, self.month)))
        self.complete()
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual(result["source_event_keys"], ["sale-001"])
        self.assertEqual(result["sales_commission"], 50)
        self.assertEqual(result["blockers"], [])

    def test_missing_source_prevents_approval_instead_of_approving_zero(self):
        self.save(salary_mode="commission_only", settlement_commission_percent=1)
        with self.assertRaises(HTTPException) as error:
            service.approve(self.cur, 10, self.month, {}, self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("collections_source_incomplete", {b["code"] for b in error.exception.detail["blockers"]})
        self.assertEqual(self.count("payroll_approvals"), 0)

    def test_ledger_rejects_duplicates_and_incomplete_source_descriptions(self):
        self.fact()
        with self.assertRaises(HTTPException) as error:
            self.fact()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.count("compensation_facts"), 1)
        with self.assertRaises(HTTPException) as error:
            service.record_fact(self.cur, 10, {"event_key": "incomplete", "kind": "sale",
                                "event_date": self.start.date().isoformat(), "source_note": "کوتاه"}, self.user)
        self.assertEqual(error.exception.status_code, 422)

    def test_workday_cannot_be_duplicated_with_a_different_event_key(self):
        self.fact(key="workday-first", kind="workday", amount=0, quantity=0.5)
        with self.assertRaises(HTTPException) as error:
            self.fact(key="workday-different-key", kind="workday", amount=0, quantity=0.5)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.count("compensation_facts"), 1)

    def test_content_ledger_requires_production_editing_and_publication(self):
        base = {"event_key": "content-post-first", "kind": "content_post", "quantity": 1,
                "event_date": self.start.date().isoformat(), "source_note": "شواهد موقت تولید و انتشار"}
        for evidence in [{}, {"produced": True}, {"produced": True, "edited": True},
                         {"produced": "true", "edited": True, "published": True},
                         {"produced": True, "edited": True, "published": True, "quantity": 0.5}]:
            with self.subTest(evidence=evidence), self.assertRaises(HTTPException) as error:
                service.record_fact(self.cur, 10, {**base, **evidence}, self.user)
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.count("compensation_facts"), 0)
        service.record_fact(self.cur, 10, {**base, "produced": True, "edited": True, "published": True}, self.user)
        self.assertEqual(self.count("compensation_facts"), 1)

    def test_content_story_gate_and_source_must_both_be_complete_for_approval(self):
        self.save(salary_mode="commission_only", content_bonus={
            "monthly_amount": 200, "per_post_amount": 50, "required_posts": 4,
            "required_stories": 30, "story_requirement": "gate_full"})
        base = {"event_date": self.start.date().isoformat(), "source_note": "صورت تأییدشدهٔ محتوای موقت"}
        service.record_fact(self.cur, 10, {**base, "event_key": "posts-complete", "kind": "content_post",
                            "quantity": 4, "produced": True, "edited": True, "published": True}, self.user)
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertIn("content_source_incomplete", self.codes(result))
        self.assertIn("content_story_target_pending", self.codes(result))
        self.complete(source="content")
        with self.assertRaises(HTTPException) as error:
            service.approve(self.cur, 10, self.month, {}, self.user)
        self.assertEqual(error.exception.status_code, 409)
        service.record_fact(self.cur, 10, {**base, "event_key": "stories-complete", "kind": "content_story",
                            "quantity": 30, "published": True}, self.user)
        self.assertIn("content_source_incomplete", self.codes(service.calculate_period(self.cur, 10, self.month)))
        self.complete(source="content")
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual((result["content_posts"], result["content_stories"], result["content_pay"]), (4, 30, 200))
        self.assertEqual(result["blockers"], [])
        self.assertEqual(service.approve(self.cur, 10, self.month, {}, self.user)["approved_total"], 200)

    def test_unknown_content_story_policy_is_draft_only(self):
        bonus = {"monthly_amount": 200, "per_post_amount": 50, "required_posts": 4,
                 "required_stories": 30, "story_requirement": None}
        draft = self.save(approved=False, salary_mode="commission_only", content_bonus=bonus)
        self.assertFalse(draft["rules_approved"])
        with self.assertRaises(HTTPException) as error:
            self.save(salary_mode="commission_only", content_bonus=bonus)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.count("compensation_rule_versions"), 1)

    def test_unknown_sales_policy_cannot_be_marked_approved(self):
        for changes in [
            {"salary_mode": "commission_only", "sales_tiers": [{"up_to_amount": None, "percent": 5}]},
            {"salary_mode": "commission_only", "sales_scope": "personal", "commission_tier_basis": None,
             "sales_tiers": [{"up_to_amount": None, "percent": 5}]},
            {"targets": [{"target_type": "product", "item_identifier": "7", "target_amount": 0,
                          "target_quantity": 0, "commission_percent": 5}], "sales_scope": "personal"},
            {"salary_mode": "fixed", "fixed_monthly_amount": 100},
        ]:
            with self.subTest(changes=changes), self.assertRaises(HTTPException) as error:
                self.save(**changes)
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.count("compensation_rule_versions"), 0)

    def test_actual_overtime_without_multiplier_blocks_financial_approval(self):
        self.save(min_monthly_hours=176, overtime_multiplier=None)
        self.attendance(self.start, self.start + timedelta(hours=180))
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual(result["overtime_hours"], 4)
        self.assertIn("overtime_policy_missing", self.codes(result))
        with self.assertRaises(HTTPException) as error:
            service.approve(self.cur, 10, self.month, {}, self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.count("payroll_approval_history"), 0)

    def test_new_fact_invalidates_only_affected_person_period_and_source_attestation(self):
        mapping = {"sale": "sales", "return": "sales", "collection": "collections",
                   "collection_reversal": "collections", "mileage": "mileage", "workday": "workdays",
                   "content_post": "content", "content_story": "content", "reward": "rewards"}
        sources = {"sales", "collections", "mileage", "workdays", "content", "company_sales", "rewards"}
        gregorian_month = self.start.strftime("%Y-%m")
        for index, (kind, affected) in enumerate(mapping.items()):
            for source in sources:
                self.complete(source=source)
                self.complete(source=source, month=gregorian_month)
                self.complete(source=source, person=11)
                self.complete(source=source, month="1405-08")
            service.record_fact(self.cur, 10, {
                "event_key": f"new-fact-{index}", "kind": kind, "event_date": self.start.date().isoformat(),
                "source_note": "سند تازه برای آزمون ابطال گواهی منبع", "amount": 0, "quantity": 1,
                "produced": True, "edited": True, "published": True,
            }, self.user)
            self.cur.execute("SELECT source,complete FROM compensation_source_checks WHERE salesperson_id=10 AND payroll_month=%s", (self.month,))
            states = dict(self.cur.fetchall())
            self.assertFalse(states[affected], kind)
            self.assertTrue(all(value for source, value in states.items() if source != affected), kind)
            self.cur.execute("SELECT complete FROM compensation_source_checks WHERE salesperson_id=10 AND payroll_month=%s AND source=%s",
                             (gregorian_month, affected))
            self.assertFalse(self.cur.fetchone()[0], kind)
            self.cur.execute("""SELECT complete FROM compensation_source_checks WHERE
                (salesperson_id=11 AND payroll_month=%s) OR (salesperson_id=10 AND payroll_month='1405-08')""", (self.month,))
            self.assertTrue(all(row[0] for row in self.cur.fetchall()), kind)

    def test_duplicate_fact_does_not_invalidate_existing_fresh_attestation(self):
        self.fact()
        self.complete()
        with self.assertRaises(HTTPException):
            self.fact()
        self.cur.execute("SELECT complete FROM compensation_source_checks WHERE salesperson_id=10 AND payroll_month=%s AND source='sales'", (self.month,))
        self.assertTrue(self.cur.fetchone()[0])

    def test_closed_shift_days_are_automatic_unique_scoped_and_never_persisted(self):
        self.save(salary_mode="fixed", fixed_monthly_amount=2500, fixed_proration="working_days", required_workdays=25)
        day = self.start + timedelta(days=1, hours=8)
        self.attendance(day, day + timedelta(hours=2))
        self.attendance(day + timedelta(hours=5), day + timedelta(hours=7))
        self.attendance(day + timedelta(days=1), day + timedelta(days=1, hours=2))
        self.attendance(day + timedelta(days=2), day + timedelta(days=2, hours=2), person=11)
        self.attendance(self.start - timedelta(hours=1), self.start + timedelta(hours=1))
        self.attendance(self.end, self.end + timedelta(hours=2))
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual(result["worked_days"], 2)
        self.assertEqual(result["fixed_pay"], 200)
        self.assertTrue(result["source_complete"]["workdays"])
        self.assertIn("closed_shift_workdays", result["automatically_filled"])
        self.assertEqual(result["source_event_keys"], ["attendance-day:" + day.date().isoformat(),
                                                      "attendance-day:" + (day + timedelta(days=1)).date().isoformat()])
        self.assertEqual(self.count("compensation_facts"), 0)
        self.assertEqual(self.count("compensation_source_checks"), 0)
        self.assertEqual(self.count("payroll_approval_history"), 0)

    def test_manager_workday_correction_replaces_attendance_day_draft_and_needs_attestation(self):
        self.save(salary_mode="fixed", fixed_monthly_amount=2500, fixed_proration="working_days", required_workdays=25)
        self.attendance()
        self.attendance(self.start + timedelta(days=1), self.start + timedelta(days=1, hours=2))
        self.fact(key="manager-workday-correction", kind="workday", amount=0, quantity=0.5)
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual(result["worked_days"], 0.5)
        self.assertEqual(result["source_event_keys"], ["manager-workday-correction"])
        self.assertNotIn("closed_shift_workdays", result["automatically_filled"])
        self.assertIn("workdays_source_incomplete", self.codes(result))
        self.complete(source="workdays")
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual(result["fixed_pay"], 50)
        self.assertEqual(result["blockers"], [])
        self.assertEqual(self.count("compensation_facts"), 1)

    def test_explicit_incomplete_workday_check_or_open_shift_prevents_automatic_certification(self):
        self.save(salary_mode="fixed", fixed_monthly_amount=2500, fixed_proration="working_days", required_workdays=25)
        self.attendance()
        self.complete(source="workdays", value=False)
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertFalse(result["source_complete"]["workdays"])
        self.assertIn("workdays_source_incomplete", self.codes(result))
        self.cur.execute("DELETE FROM compensation_source_checks")
        self.attendance(self.start + timedelta(days=1), active=True)
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertIn("open_attendance", self.codes(result))
        self.assertIn("workdays_source_incomplete", self.codes(result))
        self.assertEqual(self.count("compensation_facts"), 0)

    def test_reward_requires_fresh_attestation_and_is_saved_in_immutable_snapshot(self):
        self.save(salary_mode="commission_only", bonus_note="پاداش مبتنی بر تأیید مدیریت")
        self.fact(key="reward-001", kind="reward", amount=50, quantity=0)
        with self.assertRaises(HTTPException) as error:
            service.approve(self.cur, 10, self.month, {}, self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("rewards_source_incomplete", {item["code"] for item in error.exception.detail["blockers"]})
        self.complete(source="rewards")
        approved = service.approve(self.cur, 10, self.month, {}, self.user)
        self.assertEqual(approved["approved_total"], 50)
        self.cur.execute("UPDATE compensation_facts SET amount=1000 WHERE kind='reward'")
        result = service.summary(self.cur, 10, self.month)
        self.assertEqual(result["reward_pay"], 50)
        self.assertEqual(result["approval"]["approved_total"], Decimal("50"))
        self.assertEqual(result["source_event_keys"], ["reward-001"])
        self.assertEqual(result["rules"]["bonus_note"], "پاداش مبتنی بر تأیید مدیریت")

    def test_negative_reward_is_rejected_without_writing_or_invalidating_source(self):
        self.complete(source="rewards")
        with self.assertRaises(HTTPException) as error:
            self.fact(key="negative-reward", kind="reward", amount=-1, quantity=0)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.count("compensation_facts"), 0)
        self.cur.execute("SELECT complete FROM compensation_source_checks WHERE salesperson_id=10 AND source='rewards'")
        self.assertTrue(self.cur.fetchone()[0])

    def test_money_upper_bound_is_accepted_and_excess_is_rejected(self):
        self.save(salary_mode="commission_only")
        maximum = Decimal("1000000000000000000")
        approved = service.approve(self.cur, 10, self.month,
                                   {"additions": str(maximum), "note": "آزمون موقت سقف عدد معتبر"}, self.user)
        self.assertEqual(Decimal(str(approved["approved_total"])), maximum)
        for value in [str(maximum + Decimal("0.01")), "1e19", "Infinity", "NaN", "-1"]:
            with self.subTest(value=value), self.assertRaises(HTTPException) as error:
                service.approve(self.cur, 10, self.month,
                                {"additions": value, "note": "آزمون مبلغ نامعتبر"}, self.user)
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.count("payroll_approval_history"), 1)

    def test_approval_captures_rule_source_keys_currency_and_period_lock(self):
        version = self.save(salary_mode="commission_only", sales_scope="personal", commission_tier_basis="marginal",
                            sales_tiers=[{"up_to_amount": None, "percent": 5}])
        self.fact()
        self.complete()
        approved = service.approve(self.cur, 10, self.month, {}, self.user)
        self.assertEqual((approved["revision"], approved["approved_total"]), (1, 50))
        result = service.summary(self.cur, 10, self.month)
        self.assertFalse(result["provisional"])
        self.assertEqual(result["currency"], "IRR")
        self.assertEqual(result["rule_version"], version["rule_version"])
        self.assertEqual(result["source_event_keys"], ["sale-001"])
        self.assertEqual(Decimal(str(result["approval"]["approved_total"])), Decimal("50"))
        self.assertTrue(period_is_approved(self.cur, 10, self.start))
        self.assertTrue(period_is_approved(self.cur, 10, self.end - timedelta(microseconds=1)))
        self.assertFalse(period_is_approved(self.cur, 10, self.end))

    def test_snapshot_remains_fixed_if_underlying_input_is_changed_outside_service(self):
        version = self.save()
        self.attendance()
        service.approve(self.cur, 10, self.month, {}, self.user)
        before = service.summary(self.cur, 10, self.month)
        self.cur.execute("UPDATE attendance_sessions SET end_time=end_time+INTERVAL '8 hours'")
        self.cur.execute("UPDATE compensation_rule_versions SET rules_json=jsonb_set(rules_json,'{hourly_rate}','999') WHERE id=%s",
                         (version["rule_version"],))
        after = service.summary(self.cur, 10, self.month)
        self.assertEqual(before, after)
        self.assertEqual(after["base_pay"], 200)
        self.assertEqual(after["rules"]["hourly_rate"], 100)

    def test_approved_period_blocks_new_contract_or_ledger_fact(self):
        self.save()
        service.approve(self.cur, 10, self.month, {}, self.user)
        for action in [lambda: self.save(hourly_rate=900), lambda: self.fact()]:
            with self.assertRaises(HTTPException) as error:
                action()
            self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.count("compensation_rule_versions"), 1)
        self.assertEqual(self.count("compensation_facts"), 0)
        self.save(month="1405-08", hourly_rate=900)
        self.assertEqual(self.count("compensation_rule_versions"), 2)

    def test_revision_preserves_original_snapshot_and_requires_reason(self):
        self.save()
        self.attendance()
        service.approve(self.cur, 10, self.month, {}, self.user)
        self.cur.execute("SELECT snapshot,approved_total FROM payroll_approval_history WHERE revision=1")
        original_snapshot, original_total = self.cur.fetchone()
        with self.assertRaises(HTTPException) as error:
            service.approve(self.cur, 10, self.month, {"additions": 10}, self.user)
        self.assertEqual(error.exception.status_code, 422)
        revised = service.approve(self.cur, 10, self.month,
                                   {"additions": 10, "deductions": 5, "note": "اصلاح آزمایشی مستند"}, self.user)
        self.assertEqual((revised["revision"], revised["approved_total"]), (2, 205))
        self.assertEqual(self.count("payroll_approval_history"), 2)
        self.cur.execute("SELECT snapshot,approved_total FROM payroll_approval_history WHERE revision=1")
        self.assertEqual(self.cur.fetchone(), (original_snapshot, original_total))
        result = service.summary(self.cur, 10, self.month)
        self.assertEqual(result["approval"]["revision"], 2)
        self.assertEqual(result["approval"]["approved_total"], Decimal("205"))

    def test_invalid_adjustments_and_negative_total_are_rejected(self):
        self.save()
        for payload in [{"additions": -1}, {"deductions": "NaN"}, {"additions": "Infinity"},
                        {"deductions": 1, "note": "کسورات بیش از کارکرد"},
                        {"additions": 1, "note": ""}]:
            with self.subTest(payload=payload), self.assertRaises(HTTPException) as error:
                service.approve(self.cur, 10, self.month, payload, self.user)
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.count("payroll_approval_history"), 0)

    def test_rials_are_stored_without_implicit_toman_conversion(self):
        saved = self.save(salary_mode="fixed", fixed_monthly_amount=130000000, fixed_proration="full")
        self.assertEqual(saved["rules"]["fixed_monthly_amount"], 130000000)
        result = service.calculate_period(self.cur, 10, self.month)
        self.assertEqual(result["currency"], "IRR")
        self.assertEqual(result["base_pay"], 130000000)
        approved = service.approve(self.cur, 10, self.month, {}, self.user)
        self.assertEqual(approved["approved_total"], 130000000)

    def test_aware_utc_timestamp_uses_tehran_period_boundary_for_lock(self):
        self.save()
        service.approve(self.cur, 10, self.month, {}, self.user)
        before = (self.start - timedelta(hours=3, minutes=30, microseconds=1)).replace(tzinfo=timezone.utc)
        at_start = (self.start - timedelta(hours=3, minutes=30)).replace(tzinfo=timezone.utc)
        self.assertFalse(period_is_approved(self.cur, 10, before))
        self.assertTrue(period_is_approved(self.cur, 10, at_start))


if __name__ == "__main__":
    unittest.main()
