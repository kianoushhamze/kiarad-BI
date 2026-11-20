"""Role checks and optional rollback-only PostgreSQL persistence checks."""
from contextlib import contextmanager
from datetime import date
from pathlib import Path
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

import treasury
import treasury_strategy as strategy
from treasury_finance import MONEY_FIELDS


def report_payload(**extra):
    return {"month": "1405-06", "kind": "actual", **dict.fromkeys(MONEY_FIELDS, 0),
            "revenue": 10000, "cogs": 4000, "fixed_costs": 2000,
            "source_note": "synthetic source for isolated financial checks", **extra}


class TreasuryStrategyRoleTests(unittest.TestCase):
    def setUp(self):
        self.user = {"id": 2, "role": "salesperson"}
        app = FastAPI()
        app.include_router(strategy.router)
        app.dependency_overrides[treasury.current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        blocked = Mock()
        blocked.begin.side_effect = AssertionError("Real database blocked")
        guard = patch.object(strategy, "engine", blocked)
        guard.start()
        self.addCleanup(guard.stop)

    def test_staff_cannot_read_or_change_financial_planning(self):
        for role in ("salesperson", "visitor", "sales_manager"):
            self.user["role"] = role
            with self.subTest(role=role):
                self.assertEqual(self.client.get("/treasury/strategy/overview").status_code, 403)
                for suffix in ("settings", "monthly", "cash-scenario", "profit-scenario", "reconciliation-preview", "operating-plan", "holoo-refresh"):
                    self.assertEqual(self.client.post(f"/treasury/strategy/{suffix}", json={}).status_code, 403)
                self.assertEqual(self.client.get("/treasury/strategy/holoo-refresh").status_code, 403)

    def test_finance_cannot_attest_operating_plan(self):
        self.user["role"] = "finance"
        response = self.client.post("/treasury/strategy/operating-plan", json={"monthly_expense_irr": 3000000000, "source_note": "synthetic planning note"})
        self.assertEqual(response.status_code, 403)

    def test_operating_plan_cannot_override_registry_completeness(self):
        with self.assertRaises(ValidationError):
            strategy.OperatingPlan.model_validate({"monthly_expense_irr": 3000000000, "source_note": "synthetic planning note", "checks_registry_complete": True})

    def test_finance_cannot_approve_actuals(self):
        self.user["role"] = "finance"
        response = self.client.post("/treasury/strategy/monthly", json=report_payload(approve=True, coverage_confirmed=True))
        self.assertEqual(response.status_code, 403)

    def test_finance_cannot_change_growth_goal(self):
        self.user["role"] = "finance"
        response = self.client.post("/treasury/strategy/settings", json={"end_month": "1405-12", "source_note": "synthetic note"})
        self.assertEqual(response.status_code, 403)

    def test_ceo_cannot_approve_incomplete_report(self):
        self.user["role"] = "ceo"
        self.assertEqual(self.client.post("/treasury/strategy/monthly", json=report_payload(approve=True)).status_code, 422)

    def test_ceo_cannot_approve_budget_as_actual(self):
        self.user["role"] = "ceo"
        self.assertEqual(self.client.post("/treasury/strategy/monthly", json=report_payload(kind="budget", approve=True, coverage_confirmed=True)).status_code, 422)

    def test_ceo_cannot_approve_current_or_future_month(self):
        self.user["role"] = "ceo"
        with patch.object(strategy, "iran_today", return_value=date(2026, 10, 19)):
            for month in ("1405-07", "1405-08"):
                self.assertEqual(self.client.post("/treasury/strategy/monthly", json=report_payload(month=month, approve=True, coverage_confirmed=True)).status_code, 422)

    def test_negative_nan_missing_and_unknown_fields_are_rejected(self):
        self.user["role"] = "ceo"
        for extra in ({"revenue": -1}, {"cogs": "NaN"}, {"fixed_costs": "Infinity"}, {"inject": "code"}, {"revenue": "1 + 2"}):
            self.assertEqual(self.client.post("/treasury/strategy/monthly", json=report_payload(**extra)).status_code, 422)
        missing = report_payload()
        missing.pop("taxes")
        self.assertEqual(self.client.post("/treasury/strategy/monthly", json=missing).status_code, 422)

    def test_month_and_growth_window_validation(self):
        for payload in ({"end_month": "1405-13"}, {"baseline_month": "1405-06", "end_month": "1405-05"}, {"baseline_month": "1405-01", "end_month": "1408-01"}, {"end_month": "1405-12", "monthly_growth_percent": "NaN"}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                strategy.StrategySettings.model_validate({"source_note": "synthetic validation", **payload})

    def test_cash_scenario_limits(self):
        for payload in ({"collection_percent": 101}, {"collection_delay_days": -1}, {"collection_delay_days": 1.5}, {"extra_outflow": "NaN"}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                strategy.CashScenario.model_validate(payload)

    def test_old_treasury_rejects_nonfinite_and_negative_check_amounts(self):
        with self.assertRaises(ValidationError):
            treasury.CashAccountCreate(name="test account", account_type="cash", current_balance="NaN")
        with self.assertRaises(ValidationError):
            treasury.ManualCheckCreate(check_type="receivable", counterparty="synthetic", amount=-1, due_date="1405/01/01")

    def test_jalali_parser_accepts_persian_digits_and_rejects_invalid_day(self):
        self.assertEqual(treasury.parse_jalali_date("۱۴۰۵/۰۱/۰۱")[1], date(2026, 3, 21))
        self.assertIsNone(treasury.parse_jalali_date("1405/12/30")[1])

    def test_preview_routes_use_read_permission_and_saving_requires_write(self):
        import api
        for suffix in ("cash-scenario", "profit-scenario", "reconciliation-preview"):
            self.assertEqual(api._required_permission("POST", f"/treasury/strategy/{suffix}"), "can_read")
            self.assertEqual(api._required_module(f"/treasury/strategy/{suffix}"), "treasury")
        self.assertEqual(api._required_permission("POST", "/treasury/strategy/monthly"), "can_write")


@unittest.skipUnless(os.getenv("KIARAD_TEST_TREASURY_DB") == "1", "Isolated PostgreSQL opt-in required")
class TreasuryStrategyDatabaseTests(unittest.TestCase):
    def setUp(self):
        import db
        self.conn = db.engine.connect()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.assertEqual(self.conn.exec_driver_sql("SHOW search_path").scalar(), "pg_temp")
        for statement in (
            "CREATE TEMP TABLE financial_documents(id INT PRIMARY KEY,document_type TEXT,counterparty TEXT,amount NUMERIC,due_date DATE,status TEXT,collection_probability NUMERIC,reference_number TEXT,customer_id INT)",
            "CREATE TEMP TABLE cash_accounts(id INT PRIMARY KEY,current_balance NUMERIC,minimum_reserve NUMERIC,is_active INT,updated_at TIMESTAMP)",
            "CREATE TEMP TABLE fixed_expenses(id INT PRIMARY KEY,title TEXT,amount NUMERIC,due_day INT,is_active INT)",
            "CREATE TEMP TABLE receivable_snapshots(id INT PRIMARY KEY,snapshot_date DATE,total_amount NUMERIC,row_count INT)",
            "CREATE TEMP TABLE tasks(id INT PRIMARY KEY,title TEXT,status TEXT)",
        ):
            self.conn.execute(text(statement))
        raw = self.conn.connection.driver_connection
        with raw.cursor() as cursor:
            for name in ("0008_visit_treasury_columns.sql", "0010_treasury_excel_storage.sql"):
                migration = Path(__file__).resolve().parents[1] / "migrations" / name
                cursor.execute(migration.read_text(encoding="utf-8-sig"))
        strategy.ensure_schema(self.conn)

        @contextmanager
        def transaction():
            yield self.conn
        for patcher in (patch.object(strategy, "engine", SimpleNamespace(begin=transaction, connect=transaction)),
                        patch.object(treasury, "engine", SimpleNamespace(begin=transaction, connect=transaction)),
                        patch.object(treasury, "iran_today", return_value=date(2026, 10, 19)),
                        patch.object(strategy, "iran_today", return_value=date(2026, 10, 19))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.user = {"id": 1, "role": "ceo"}

    def save(self, **extra):
        return strategy.save_monthly_finance(strategy.MonthlyFinance.model_validate(report_payload(**extra)), self.user)

    def test_drafts_are_excluded_until_ceo_approves(self):
        self.save()
        result = strategy.strategy_overview(self.user)
        self.assertEqual(result["approved_actuals"], [])
        self.save(expected_revision=1, approve=True, coverage_confirmed=True)
        result = strategy.strategy_overview(self.user)
        self.assertEqual(len(result["approved_actuals"]), 1)
        self.assertEqual(result["approved_actuals"][0]["statement"]["net_profit"], 4000)

    def test_optimistic_concurrency_rejects_stale_revision(self):
        self.save()
        with self.assertRaises(strategy.HTTPException) as caught:
            self.save()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.conn.execute(text("SELECT COUNT(*) FROM treasury_strategy_revisions")).scalar(), 1)

    def test_operating_plan_is_versioned_separate_from_actual_reports(self):
        model = strategy.OperatingPlan(monthly_expense_irr=3000000000, source_note="synthetic approved monthly envelope", receivable_checks_current=True)
        saved = strategy.save_operating_plan(model, self.user)
        self.assertEqual(saved["revision"], 1)
        result = strategy.strategy_overview(self.user)
        self.assertEqual(result["reports"], [])
        self.assertEqual(result["approved_actuals"], [])
        self.assertEqual(int(result["operating_plan"]["monthly_expense_irr"]), 3000000000)
        self.assertFalse(result["operating_plan"]["checks_registry_complete"])
        self.assertFalse(result["operating_projection"]["health_confirmed"])
        self.assertEqual(len(result["operating_projection"]["daily"]), 91)
        with self.assertRaises(strategy.HTTPException) as caught:
            strategy.save_operating_plan(model, self.user)
        self.assertEqual(caught.exception.status_code, 409)

    def test_bank_attestation_requires_today_complete_verified_snapshot(self):
        data = strategy.OperatingPlan(monthly_expense_irr=3000000000, bank_balances_current=True, source_note="synthetic bank attestation")
        with self.assertRaises(strategy.HTTPException) as caught:
            strategy.save_operating_plan(data, self.user)
        self.assertEqual(caught.exception.status_code, 422)

    def test_corrected_draft_keeps_previous_approved_actual(self):
        self.save(approve=True, coverage_confirmed=True)
        self.save(expected_revision=1, revenue=11000)
        result = strategy.strategy_overview(self.user)
        self.assertEqual(result["reports"][0]["revision"], 2)
        self.assertIsNone(result["reports"][0]["approved_by"])
        self.assertEqual(result["approved_actuals"][0]["revision"], 1)
        self.assertEqual(len(result["history"]), 2)

    def test_growth_uses_frozen_baseline_revision(self):
        self.save(approve=True, coverage_confirmed=True)
        config = strategy.StrategySettings(baseline_month="1405-06", end_month="1405-12", source_note="synthetic baseline source")
        saved = strategy.save_strategy_settings(config, self.user)
        self.assertEqual(saved["payload"]["baseline_profit"], 4000)
        self.save(expected_revision=1, revenue=12000, approve=True, coverage_confirmed=True)
        result = strategy.strategy_overview(self.user)
        self.assertEqual(result["growth"]["rows"][0]["target"], 4000)
        self.assertEqual(result["growth"]["rows"][0]["actual"], 6000)

    def test_missing_baseline_report_is_rejected(self):
        config = strategy.StrategySettings(baseline_month="1405-06", end_month="1405-12", source_note="synthetic baseline source")
        with self.assertRaises(strategy.HTTPException) as caught:
            strategy.save_strategy_settings(config, self.user)
        self.assertEqual(caught.exception.status_code, 422)

    def test_cash_and_profit_scenarios_do_not_persist_revisions(self):
        self.save(approve=True, coverage_confirmed=True)
        count = self.conn.execute(text("SELECT COUNT(*) FROM treasury_strategy_revisions")).scalar()
        self.assertFalse(strategy.cash_scenario(strategy.CashScenario(), self.user)["saved"])
        result = strategy.profit_scenario(strategy.ProfitScenario(month="1405-06", volume_change_percent=20), self.user)
        self.assertTrue(result["preview_only"])
        self.assertEqual(self.conn.execute(text("SELECT COUNT(*) FROM treasury_strategy_revisions")).scalar(), count)

    def test_empty_finance_does_not_claim_health_or_zero_profit(self):
        result = strategy.strategy_overview(self.user)
        self.assertEqual(result["growth"]["status"], "baseline_missing")
        self.assertFalse(result["projection"]["cash_accounts_available"])
        self.assertEqual(result["actions"], [])
        self.assertFalse(any(row["available"] for row in result["coverage"]))

    def test_bank_balance_comparison_does_not_mutate_account(self):
        self.conn.execute(text("INSERT INTO cash_accounts VALUES(1,1000,100,1,NOW())"))
        result = strategy.reconciliation_preview(strategy.ReconciliationPreview(account_id=1, statement_balance=850), self.user)
        self.assertEqual(result["difference"], -150)
        self.assertFalse(result["matched"])
        self.assertFalse(result["saved"])
        self.assertEqual(self.conn.execute(text("SELECT current_balance FROM cash_accounts WHERE id=1")).scalar(), 1000)

    def test_equal_bank_balances_match_and_unknown_account_is_rejected(self):
        self.conn.execute(text("INSERT INTO cash_accounts VALUES(1,1000,100,1,NOW())"))
        result = strategy.reconciliation_preview(strategy.ReconciliationPreview(account_id=1, statement_balance=1000), self.user)
        self.assertTrue(result["matched"])
        with self.assertRaises(strategy.HTTPException) as caught:
            strategy.reconciliation_preview(strategy.ReconciliationPreview(account_id=99, statement_balance=1000), self.user)
        self.assertEqual(caught.exception.status_code, 404)

    def test_legacy_forecast_check_direction_bounced_and_settled(self):
        self.conn.execute(text("INSERT INTO cash_accounts VALUES(1,1000,0,1,NOW())"))
        for ident, kind, status, amount in ((1, "receivable_check", "open", 500), (2, "payable_check", "open", 200), (3, "receivable_check", "bounced", 9999), (4, "payable", "settled", 9000)):
            self.conn.execute(text("INSERT INTO financial_documents(id,document_type,counterparty,amount,due_date,status,collection_probability) VALUES(:id,:kind,'synthetic',:amount,'2026-10-19',:status,1)"), {"id": ident, "kind": kind, "amount": amount, "status": status})
        result = treasury.cashflow_forecast(days=60, _=self.user)
        self.assertEqual(result["summary"]["closing_expected_balance"], 1300)
        self.assertEqual(result["summary"]["planned_outflow"], 200)

    def test_legacy_forecast_linked_expense_not_counted_twice(self):
        self.conn.execute(text("INSERT INTO cash_accounts VALUES(1,1000,0,1,NOW())"))
        self.conn.execute(text("INSERT INTO fixed_expenses VALUES(8,'synthetic expense',100,1,1)"))
        self.conn.execute(text("INSERT INTO financial_documents(id,document_type,counterparty,amount,due_date,status,collection_probability,fixed_expense_id) VALUES(1,'payable','synthetic',100,'2026-10-23','open',1,8)"))
        result = treasury.cashflow_forecast(days=60, _=self.user)
        self.assertEqual(result["summary"]["planned_outflow"], 200)


if __name__ == "__main__":
    unittest.main()
