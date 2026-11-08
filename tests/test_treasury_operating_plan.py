"""Synthetic-only tests: no database, credentials or Holoo calls."""
from datetime import date, timedelta
import json
import unittest

import jdatetime

from treasury_operating_plan import default_operating_plan, operating_cash_plan


class OperatingPlanTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 10, 19)
        self.summary = {"currency_verified": True, "to_date": self.today.isoformat(),
            "sources": [{"kind": "cash", "ok": True, "complete": True, "count": 1, "valid_amounts": 1},
                        {"kind": "banks", "ok": True, "complete": True, "count": 1, "valid_amounts": 1}],
            "balances": [{"source": "cash", "code": "1", "balance": 10000000000},
                         {"source": "banks", "code": "2", "balance": 10000000000}]}

    def ready(self, **kwargs):
        return {**default_operating_plan(), "bank_balances_current": True,
                "receivable_checks_current": True, "payable_checks_current": True,
                "endorsed_checks_current": True, "checks_registry_complete": True, **kwargs}

    def doc(self, ident=1, **kwargs):
        return {"id": ident, "document_type": "receivable_check", "status": "open", "amount": 1000,
                "due_date": self.today, "collection_probability": 1, **kwargs}

    def run_plan(self, docs=None, plan=None, summary=None, today=None):
        active_today = today or self.today
        if summary is None:
            summary = json.loads(json.dumps(self.summary))
            summary["to_date"] = active_today.isoformat()
        return operating_cash_plan(plan if plan is not None else default_operating_plan(),
                                   summary, docs or [], active_today)

    def test_default_is_total_300_million_toman_and_source_states(self):
        plan = default_operating_plan()
        self.assertEqual(plan["monthly_expense_irr"], 3000000000)
        self.assertTrue(plan["receivable_checks_current"])
        for key in ("bank_balances_current", "payable_checks_current", "endorsed_checks_current", "checks_registry_complete"):
            self.assertFalse(plan[key])
        plan["monthly_expense_irr"] = 0
        self.assertEqual(default_operating_plan()["monthly_expense_irr"], 3000000000)

    def test_default_is_incomplete_even_with_known_positive_bank_balance(self):
        result = self.run_plan()
        self.assertEqual(result["opening_balance_irr"], 20000000000)
        self.assertFalse(result["health_confirmed"])
        self.assertFalse(result["readiness"]["complete"])
        self.assertTrue(result["estimated"])

    def test_missing_bank_balance_produces_null_cash_gap_not_zero(self):
        result = self.run_plan(summary={})
        self.assertIsNone(result["opening_balance_irr"])
        self.assertIsNone(result["totals"]["required_extra_collections_irr"])
        self.assertTrue(all(row["projected_balance_irr"] is None for row in result["daily"]))
        self.assertFalse(result["health_confirmed"])
        self.assertGreater(result["totals"]["operating_envelope_outflow_irr"], 0)

    def test_invalid_or_incomplete_balance_cannot_be_used(self):
        for modify in (lambda s: s.update(currency_verified=False),
                       lambda s: s["sources"][0].update(complete=False),
                       lambda s: s["sources"][1].update(valid_amounts=0),
                       lambda s: s["balances"][0].update(balance="NaN"),
                       lambda s: s["balances"].append(s["balances"][0].copy())):
            summary = json.loads(json.dumps(self.summary))
            modify(summary)
            with self.subTest(summary=summary):
                self.assertIsNone(self.run_plan(summary=summary)["opening_balance_irr"])

    def test_all_ready_and_positive_has_confirmed_coverage_and_cash(self):
        result = self.run_plan(plan=self.ready())
        self.assertTrue(result["readiness"]["complete"])
        self.assertTrue(result["scenario_obligations_covered"])
        self.assertFalse(result["health_confirmed"])
        self.assertEqual(result["totals"]["required_extra_collections_irr"], 0)

    def test_91_calendar_days_jalali_budget_and_full_month_exact_rounding(self):
        today = jdatetime.date(1405, 8, 1).togregorian()
        result = self.run_plan(today=today, plan=self.ready(monthly_expense_irr=101))
        self.assertEqual(len(result["daily"]), 91)
        self.assertEqual(result["end"], (today + timedelta(days=90)).isoformat())
        for month in result["months"][:3]:
            self.assertEqual(month["period_expense_budget_irr"], 101)
            self.assertEqual(month["operating_envelope_outflow_irr"], 101)

    def test_esfand_leap_days(self):
        for year, days in ((1403, 30), (1405, 29)):
            start = jdatetime.date(year, 12, 1).togregorian()
            result = self.run_plan(today=start, plan=self.ready(monthly_expense_irr=300))
            self.assertEqual(result["months"][0]["days_in_month"], days)
            self.assertEqual(result["months"][0]["period_expense_budget_irr"], 300)

    def test_receivable_probability_bounce_and_full_payable(self):
        docs = [self.doc(amount=1000, collection_probability=.25),
                self.doc(2, amount=1000, status="bounced"),
                self.doc(3, document_type="payable_check", amount=200, status="bounced", collection_probability=.01)]
        result = self.run_plan(docs, self.ready(monthly_expense_irr=0))
        self.assertEqual(result["totals"]["expected_receipts_irr"], 250)
        self.assertEqual(result["totals"]["payable_outflow_irr"], 200)

    def test_closed_cancelled_and_out_of_horizon_are_not_cash_events(self):
        docs = [self.doc(i, status=status) for i, status in enumerate(("settled", "cleared", "cancelled"), 1)]
        docs.append(self.doc(4, due_date=self.today + timedelta(days=91)))
        result = self.run_plan(docs, self.ready(monthly_expense_irr=0))
        self.assertEqual(result["totals"]["expected_receipts_irr"], 0)

    def test_overdue_occurs_on_today(self):
        result = self.run_plan([self.doc(due_date=self.today - timedelta(days=50))], self.ready(monthly_expense_irr=0))
        self.assertEqual(result["daily"][0]["expected_receipts_irr"], 1000)

    def test_linked_open_and_settled_expenses_reduce_same_month_envelope_once(self):
        start = jdatetime.date(1405, 8, 1).togregorian()
        docs = [self.doc(1, document_type="payable", due_date=start, amount=300, fixed_expense_id=1),
                self.doc(2, document_type="payable", due_date=start, amount=200, fixed_expense_id=2, status="settled")]
        result = self.run_plan(docs, self.ready(monthly_expense_irr=1000), today=start)
        month = result["months"][0]
        self.assertEqual(month["operating_envelope_outflow_irr"], 500)
        self.assertEqual(month["linked_expense_coverage_irr"], 500)
        self.assertEqual(month["payable_outflow_irr"], 300)
        self.assertEqual(result["months"][1]["operating_envelope_outflow_irr"], 1000)

    def test_unlinked_payable_stays_full_and_does_not_reduce_budget(self):
        start = jdatetime.date(1405, 8, 1).togregorian()
        result = self.run_plan([self.doc(document_type="payable", amount=200, due_date=start)], self.ready(monthly_expense_irr=1000), today=start)
        self.assertEqual(result["months"][0]["operating_envelope_outflow_irr"], 1000)
        self.assertEqual(result["months"][0]["payable_outflow_irr"], 200)
        self.assertEqual(result["coverage"]["unlinked_open_payables"], 1)

    def test_cancelled_linked_cost_does_not_consume_envelope_and_excess_never_negative(self):
        start = jdatetime.date(1405, 8, 1).togregorian()
        docs = [self.doc(1, document_type="payable", amount=900, fixed_expense_id=1, due_date=start, status="cancelled"),
                self.doc(2, document_type="payable", amount=1200, fixed_expense_id=2, due_date=start)]
        result = self.run_plan(docs, self.ready(monthly_expense_irr=1000), today=start)
        self.assertEqual(result["months"][0]["operating_envelope_outflow_irr"], 0)
        self.assertEqual(result["months"][0]["payable_outflow_irr"], 1200)

    def test_unknown_endorsed_direction_not_added_as_receipt_or_payment(self):
        result = self.run_plan([self.doc(document_type="endorsed_check")], self.ready(monthly_expense_irr=0))
        self.assertEqual(result["totals"]["expected_receipts_irr"], 0)
        self.assertEqual(result["totals"]["payable_outflow_irr"], 0)
        self.assertFalse(result["readiness"]["complete"])

    def test_duplicate_documents_not_double_counted_and_block_readiness(self):
        docs = [self.doc(1, reference_number="A"), self.doc(2, reference_number="A"), self.doc(1)]
        result = self.run_plan(docs, self.ready(monthly_expense_irr=0))
        self.assertEqual(result["totals"]["expected_receipts_irr"], 1000)
        self.assertEqual(result["coverage"]["duplicate_documents"], 2)
        self.assertFalse(result["health_confirmed"])

    def test_invalid_document_amount_date_and_probability_do_not_produce_income(self):
        docs = [self.doc(1, amount="NaN"), self.doc(2, due_date="bad"), self.doc(3, amount=-1),
                self.doc(4, collection_probability=2), self.doc(5, status="unknown")]
        result = self.run_plan(docs, self.ready(monthly_expense_irr=0))
        self.assertEqual(result["coverage"]["invalid_documents"], 5)
        self.assertEqual(result["totals"]["expected_receipts_irr"], 0)
        self.assertFalse(result["readiness"]["complete"])

    def test_unknown_probability_is_explicit_assumption(self):
        doc = self.doc()
        del doc["collection_probability"]
        result = self.run_plan([doc], self.ready(monthly_expense_irr=0))
        self.assertEqual(result["coverage"]["assumed_collection_probability"], 1)
        self.assertFalse(result["health_confirmed"])

    def test_missing_stable_identifier_blocks_confirmed_coverage(self):
        result = self.run_plan([self.doc(ident=None)], self.ready(monthly_expense_irr=0))
        self.assertEqual(result["coverage"]["missing_document_identifiers"], 1)
        self.assertFalse(result["readiness"]["complete"])
        self.assertTrue(result["readiness"]["blockers"])

    def test_invalid_expense_link_does_not_reduce_envelope_or_erase_obligation(self):
        start = jdatetime.date(1405, 8, 1).togregorian()
        result = self.run_plan([self.doc(document_type="payable", amount=100, fixed_expense_id=True, due_date=start)],
                               self.ready(monthly_expense_irr=1000), today=start)
        self.assertEqual(result["months"][0]["operating_envelope_outflow_irr"], 1000)
        self.assertEqual(result["months"][0]["payable_outflow_irr"], 100)
        self.assertFalse(result["readiness"]["complete"])

    def test_required_extra_collections_uses_daily_minimum_not_end_balance(self):
        summary = json.loads(json.dumps(self.summary))
        summary["balances"][0]["balance"] = 100
        summary["balances"][1]["balance"] = 0
        docs = [self.doc(1, document_type="payable", amount=300),
                self.doc(2, amount=1000, due_date=self.today + timedelta(days=2))]
        result = self.run_plan(docs, self.ready(monthly_expense_irr=0), summary)
        self.assertEqual(result["totals"]["closing_balance_irr"], 800)
        self.assertEqual(result["totals"]["required_extra_collections_irr"], 200)
        self.assertFalse(result["health_confirmed"])

    def test_boolean_and_invalid_monthly_budgets_rejected(self):
        for amount in (True, -1, "NaN", "Infinity", 1.5):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.run_plan(plan=self.ready(monthly_expense_irr=amount))

    def test_json_safe_no_mutation_and_no_manual_account_mixing(self):
        plan = self.ready(monthly_expense_irr=0)
        before = json.dumps(plan)
        result = self.run_plan(plan=plan)
        json.dumps(result, allow_nan=False)
        self.assertEqual(json.dumps(plan), before)
        self.assertEqual(result["opening_source"], "holoo_only")

    def test_stale_snapshot_overrides_current_flag(self):
        summary = json.loads(json.dumps(self.summary))
        summary["to_date"] = (self.today - timedelta(days=1)).isoformat()
        result = self.run_plan(plan=self.ready(), summary=summary)
        self.assertFalse(result["readiness"]["complete"])
        self.assertFalse(result["scenario_obligations_covered"])
        self.assertEqual(result["opening_balance_irr"], 20000000000)

    def test_captured_timestamp_takes_precedence_and_is_converted_to_tehran(self):
        summary = json.loads(json.dumps(self.summary))
        summary["captured_at"] = "2026-10-18T21:00:00Z"
        self.assertTrue(self.run_plan(plan=self.ready(), summary=summary)["readiness"]["complete"])
        summary["captured_at"] = "2026-10-18T19:00:00Z"
        self.assertFalse(self.run_plan(plan=self.ready(), summary=summary)["readiness"]["complete"])

    def test_attestation_must_be_current_and_tied_to_same_snapshot_when_present(self):
        summary = {**self.summary, "id": 7}
        plan = self.ready(attested_at=self.today.isoformat(), source_snapshot_id=7)
        self.assertTrue(self.run_plan(plan=plan, summary=summary)["readiness"]["complete"])
        for update in ({"attested_at": "2026-10-18"}, {"attested_at": "bad"}, {"source_snapshot_id": 8}):
            with self.subTest(update=update):
                result = self.run_plan(plan={**plan, **update}, summary=summary)
                self.assertFalse(result["readiness"]["complete"])
                self.assertTrue(result["readiness"]["blockers"])


if __name__ == "__main__":
    unittest.main()
