"""Synthetic calculations only; no database or Holoo traffic."""
import unittest
from datetime import date, timedelta

import jdatetime

from treasury_finance import (
    MONEY_FIELDS, collection_analysis, dec, growth_scenario, growth_targets,
    liquidity_projection, month_days, month_key, profit_statement, recurring_dates,
)


class TreasuryFinanceTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 10, 19)
        self.accounts = [{"current_balance": 1000, "minimum_reserve": 100}]
        self.values = dict.fromkeys(MONEY_FIELDS, 0)
        self.values.update(revenue=10000, returns=500, discounts=500, cogs=4000,
                           variable_costs=1000, fixed_costs=2000, finance_costs=100, taxes=100, other_income=200)

    def doc(self, ident=1, **kwargs):
        return {"id": ident, "document_type": "receivable", "status": "open", "amount": 100,
                "counterparty": "synthetic", "due_date": self.today, "collection_probability": 1,
                "customer_id": None, **kwargs}

    def test_profit_reconciles_each_component(self):
        p = profit_statement(self.values, "1405-06")
        self.assertEqual(p["net_sales"], 9000)
        self.assertEqual(p["gross_profit"], 5000)
        self.assertEqual(p["contribution"], 4000)
        self.assertEqual(p["operating_profit"], 2000)
        self.assertEqual(p["net_profit"], 2000)
        self.assertEqual(p["break_even_sales"], 4500)

    def test_missing_ratios_are_unknown_not_zero(self):
        p = profit_statement(self.values, "1405-06")
        for field in ("dso", "dio", "dpo", "cash_conversion_days", "current_ratio"):
            self.assertIsNone(p[field])

    def test_working_capital_uses_month_days_and_correct_denominators(self):
        values = {**self.values, "credit_sales": 9000, "average_receivables": 4500,
                  "average_inventory": 2000, "credit_purchases": 3000,
                  "average_payables": 1000, "current_assets": 10000, "current_liabilities": 5000}
        p = profit_statement(values, "1405-06")
        self.assertEqual(p["dso"], 15.5)
        self.assertEqual(p["dio"], 15.5)
        self.assertEqual(p["dpo"], 10.33)
        self.assertEqual(p["cash_conversion_days"], 20.67)
        self.assertEqual(p["current_ratio"], 2)

    def test_zero_sales_has_no_margins_or_break_even(self):
        p = profit_statement(dict.fromkeys(MONEY_FIELDS, 0), "1405-06")
        self.assertEqual(p["net_profit"], 0)
        self.assertIsNone(p["net_margin_percent"])
        self.assertIsNone(p["break_even_sales"])

    def test_negative_profit_is_preserved(self):
        p = profit_statement({**self.values, "fixed_costs": 9000}, "1405-06")
        self.assertEqual(p["net_profit"], -5000)

    def test_persian_month_normalization_and_invalid_month(self):
        self.assertEqual(month_key("۱۴۰۵/۶"), "1405-06")
        for month in ("1405-13", "2026-01", "1405", "1405-0", "1405--1"):
            with self.subTest(month=month), self.assertRaises(ValueError):
                month_key(month)

    def test_jalali_recurring_expenses_and_short_month(self):
        start = jdatetime.date(1405, 12, 1).togregorian()
        end = jdatetime.date(1406, 1, 31).togregorian()
        result = list(recurring_dates(start, end, 31))
        self.assertEqual(result, [jdatetime.date(1405, 12, 29).togregorian(), jdatetime.date(1406, 1, 31).togregorian()])
        self.assertEqual(month_days("1403-12"), 30)

    def test_twenty_percent_compounds_from_fixed_baseline(self):
        rows = growth_targets("1405-07", 1000000000, 20, "1405-12", {})["rows"]
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[1]["target"], 1200000000)
        self.assertEqual(rows[-1]["target"], 2488320000)
        self.assertTrue(all(row["actual"] is None for row in rows))

    def test_missing_zero_or_negative_baseline_never_fakes_growth(self):
        self.assertEqual(growth_targets(None, None, 20, "1405-12", {})["status"], "baseline_missing")
        for amount in (0, -100):
            self.assertEqual(growth_targets("1405-06", amount, 20, "1405-12", {})["status"], "positive_baseline_required")

    def test_draft_actual_is_not_counted_as_achievement(self):
        actuals = {"1405-07": {"approved_by": None, "statement": {"net_profit": 999}}}
        rows = growth_targets("1405-06", 100, 20, "1405-08", actuals)["rows"]
        self.assertIsNone(rows[1]["actual"])
        self.assertEqual(rows[2]["target"], 144)

    def test_missed_target_does_not_lower_next_target(self):
        actuals = {"1405-07": {"approved_by": 1, "statement": {"net_profit": 50}}}
        rows = growth_targets("1405-06", 100, 20, "1405-08", actuals)["rows"]
        self.assertEqual(rows[1]["gap"], 70)
        self.assertEqual(rows[2]["target"], 144)

    def test_forecast_receivable_and_payable_checks_correct_direction(self):
        docs = [self.doc(document_type="receivable_check", amount=500),
                self.doc(2, document_type="payable_check", amount=200)]
        p = liquidity_projection(self.accounts, docs, [], self.today)
        self.assertEqual(p["scenarios"]["base"]["closing"], 1300)
        self.assertEqual(p["scenarios"]["no_inflows"]["closing"], 800)
        self.assertEqual(len(p["weeks"]), 13)
        self.assertEqual(p["end"], self.today + timedelta(days=90))

    def test_bounced_receivable_zero_but_payable_obligation_remains(self):
        docs = [self.doc(document_type="receivable_check", status="bounced", amount=500),
                self.doc(2, document_type="payable_check", status="bounced", amount=200)]
        p = liquidity_projection(self.accounts, docs, [], self.today)
        self.assertEqual(p["scenarios"]["base"]["closing"], 800)

    def test_cleared_settled_cancelled_not_counted_twice(self):
        docs = [self.doc(i, status=status) for i, status in enumerate(("cleared", "settled", "cancelled"), 1)]
        p = liquidity_projection(self.accounts, docs, [], self.today)
        self.assertEqual(p["scenarios"]["base"]["closing"], 1000)

    def test_probability_and_delay_are_applied_once(self):
        docs = [self.doc(amount=1000, collection_probability=.5)]
        p = liquidity_projection(self.accounts, docs, [], self.today,
                                 {"collection_percent": 50, "collection_delay_days": 7, "extra_outflow": 100})
        self.assertEqual(p["scenarios"]["base"]["closing"], 1500)
        self.assertEqual(p["scenarios"]["scenario"]["closing"], 1150)
        self.assertEqual(p["weeks"][0]["scenario"], 900)

    def test_delayed_inflow_beyond_horizon_not_included(self):
        docs = [self.doc(due_date=self.today + timedelta(days=85))]
        p = liquidity_projection(self.accounts, docs, [], self.today, {"collection_delay_days": 10})
        self.assertEqual(p["scenarios"]["base"]["closing"], 1100)
        self.assertEqual(p["scenarios"]["scenario"]["closing"], 1000)

    def test_first_daily_shortage_detected_even_if_week_closes_positive(self):
        docs = [self.doc(document_type="payable", amount=1000), self.doc(2, amount=2000, due_date=self.today + timedelta(days=1))]
        p = liquidity_projection(self.accounts, docs, [], self.today)
        self.assertEqual(p["scenarios"]["base"]["first_shortage"], self.today)
        self.assertEqual(p["scenarios"]["base"]["shortage"], 100)
        self.assertEqual(p["weeks"][0]["base_minimum"], 0)
        self.assertEqual(p["weeks"][0]["base"], 2000)

    def test_opening_shortage_is_reported_even_if_today_collects(self):
        p = liquidity_projection([{"current_balance": 50, "minimum_reserve": 100}], [self.doc(amount=1000)], [], self.today)
        self.assertEqual(p["scenarios"]["base"]["first_shortage"], self.today)
        self.assertEqual(p["scenarios"]["base"]["minimum"], 50)

    def test_linked_payable_prevents_duplicate_fixed_expense(self):
        day = jdatetime.date(1405, 8, 1).togregorian()
        expenses = [{"id": 8, "due_day": 1, "amount": 100}]
        docs = [self.doc(document_type="payable", fixed_expense_id=8, due_date=day, amount=100)]
        p = liquidity_projection(self.accounts, docs, expenses, self.today)
        # Aban, Azar, Dey each 100; Aban is represented by the payable.
        self.assertEqual(p["scenarios"]["base"]["outflow"], 300)

    def test_partial_and_settled_linked_expense_only_schedules_remainder(self):
        day = jdatetime.date(1405, 8, 1).togregorian()
        expenses = [{"id": 8, "due_day": 1, "amount": 100}]
        docs = [self.doc(document_type="payable", fixed_expense_id=8, due_date=day, amount=40, status="settled")]
        p = liquidity_projection(self.accounts, docs, expenses, self.today)
        self.assertEqual(p["scenarios"]["base"]["outflow"], 260)

    def test_scenario_can_exclude_recurring_expenses(self):
        p = liquidity_projection(self.accounts, [], [{"id": 8, "due_day": 1, "amount": 100}], self.today, {"include_recurring": False})
        self.assertEqual(p["scenarios"]["scenario"]["closing"], 1000)
        self.assertEqual(p["scenarios"]["base"]["closing"], 700)

    def test_aging_exact_boundaries(self):
        days = [0, 1, 7, 8, 30, 31, 60, 61, 90, 91]
        analysis = collection_analysis([self.doc(i, due_date=self.today - timedelta(days=n)) for i, n in enumerate(days)], self.today)
        self.assertEqual([b["count"] for b in analysis["aging"]], [1, 2, 2, 2, 2, 1])
        self.assertEqual(sum(b["receivable"] for b in analysis["aging"]), 1000)

    def test_bounced_documents_are_prioritized_and_duplicate_references_flagged(self):
        docs = [self.doc(reference_number="same", due_date=self.today-timedelta(days=40)),
                self.doc(2, reference_number="same", status="bounced")]
        result = collection_analysis(docs, self.today)
        self.assertEqual(result["queue"][0]["id"], 2)
        self.assertEqual(result["duplicate_references"], [[1, 2]])

    def test_concentration_does_not_merge_distinct_customer_ids(self):
        docs = [self.doc(customer_id=1), self.doc(2, customer_id=2)]
        self.assertEqual(len(collection_analysis(docs, self.today)["concentration"]), 2)

    def test_profit_sensitivity_keeps_cost_assumptions_explicit(self):
        result = growth_scenario(self.values, {"month": "1405-06", "volume_change_percent": 20}, 2400)
        self.assertEqual(result["net_sales"], 10800)
        self.assertEqual(result["net_profit"], 2800)
        self.assertEqual(result["profit_change"], 800)
        self.assertEqual(result["required_sales_at_current_margin"], 9900)

    def test_price_change_does_not_raise_unit_purchase_cost(self):
        result = growth_scenario(self.values, {"month": "1405-06", "price_change_percent": 10})
        self.assertEqual(result["net_sales"], 9900)
        self.assertEqual(result["net_profit"], 2800)

    def test_nonfinite_amount_is_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                dec(value)


if __name__ == "__main__":
    unittest.main()
