"""Regression coverage for check metadata and recognized accounting totals."""
from contextlib import contextmanager
from datetime import date
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text

from assistant_reports import trim
import treasury
import treasury_accounting as accounting


class CheckDetailTests(unittest.TestCase):
    def test_spent_requires_destination_and_normalizes_identifiers(self):
        with self.assertRaises(ValidationError):
            treasury.CheckUpdate(status="spent", check_details={"spent_for": "  "})
        value = treasury.CheckUpdate(status="spent", check_details={
            "spent_for": "تأمین‌کننده", "national_id": "۰۰۱۲۳۴۵۶۷۸",
            "sayad_id": "۰۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵", "sayad_registration": "unregistered",
        }).check_details
        self.assertEqual(value.national_id, "0012345678")
        self.assertEqual(value.sayad_id, "0123456789012345")
        self.assertEqual(trim({"check_details": value.model_dump()})["check_details"]["spent_for"], "تأمین‌کننده")
        self.assertNotIn("national_id", trim(value.model_dump()))
        self.assertNotIn("sayad_id", trim(value.model_dump()))

    def test_treasury_access_excludes_visitors(self):
        with self.assertRaises(HTTPException) as result:
            treasury.require_treasury_access({"role": "visitor"})
        self.assertEqual(result.exception.status_code, 403)


@unittest.skipUnless(os.getenv("KIARAD_TEST_TREASURY_ACCOUNTING_DB") == "1", "Disposable PostgreSQL required")
class AccountingDatabaseTests(unittest.TestCase):
    def test_existing_schema_check_write_and_ledger_totals(self):
        from db import engine

        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                schema = "accounting_" + uuid4().hex
                conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
                conn.exec_driver_sql(f"SET LOCAL search_path TO {schema}")
                conn.execute(text("""
                    CREATE TABLE financial_documents (
                        id SERIAL PRIMARY KEY, document_type TEXT, counterparty TEXT,
                        amount NUMERIC, due_date DATE, status TEXT, reference_number TEXT,
                        collection_probability NUMERIC, customer_id INTEGER, notes TEXT, created_at TIMESTAMPTZ
                    )
                """))

                @contextmanager
                def same_transaction():
                    yield conn

                database = SimpleNamespace(begin=same_transaction)
                with patch.object(accounting, "engine", database), patch.object(treasury, "engine", database):
                    actor = {"id": 1, "role": "finance"}
                    period = date(2026, 11, 25)
                    document = treasury.create_financial_document(treasury.FinancialDocumentCreate(
                        document_type="payable", counterparty="تأمین‌کننده", amount=200, due_date=period,
                        check={"status": "open", "check_details": {"sayad_registration": "registered"}},
                    ), actor)
                    check_id = document["id"]
                    treasury.update_check_details(check_id, treasury.CheckUpdate(
                        status="spent", check_details={"spent_for": "انبار", "sayad_registration": "registered"},
                    ), actor)
                    expense = accounting.add_category(accounting.AccountingCategory(name="حمل", kind="expense"))
                    income = accounting.add_category(accounting.AccountingCategory(name="فروش", kind="income"))
                    event = accounting.AccountingEntry(
                        category_id=expense["id"], amount=200, recognized_on=period, description="کرایه", check_id=check_id,
                    )
                    accounting.add_entry(event, actor["id"])
                    with self.assertRaises(HTTPException) as duplicate:
                        accounting.add_entry(event, actor["id"])
                    self.assertEqual(duplicate.exception.status_code, 409)
                    accounting.add_entry(accounting.AccountingEntry(
                        category_id=income["id"], amount=500, recognized_on=period, description="فروش مستقیم",
                    ), actor["id"])
                    report = accounting.accounting_report(period, period, include_entries=True)
                    self.assertEqual((report["income"], report["expense"], report["profit"]), (500, 200, 300))
                    self.assertEqual(report["checks_by_due_date"][0]["status"], "spent")
                    self.assertEqual(report["spent_checks_by_destination"][0]["destination"], "انبار")
                    self.assertEqual(len(report["entries"]), 2)
            finally:
                transaction.rollback()
