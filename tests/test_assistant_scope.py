"""Assistant context must not leak unrelated company data to staff or provider."""

import unittest
from unittest.mock import patch

import assistant_engine as assistant


class AssistantScopeTests(unittest.TestCase):
    def test_general_question_sends_no_company_metrics(self):
        context = {"today": "2026-10-13", "scope": "personal", "cash_balance": 900,
                   "top_debtors": [{"name": "private"}], "my_contract": [{"hourly_rate": 1}]}
        result = assistant.context_for_question(None, {"role": "salesperson", "salesperson_id": 7},
                                                "چطور مذاکره فروش را یاد بگیرم؟", context)
        self.assertEqual(set(result), {"today", "scope"})

    def test_staff_inventory_omits_company_valuation(self):
        with patch.object(assistant, "role_has_module_permission", return_value=True), \
             patch.object(assistant, "_safe_query", return_value=0), \
             patch.object(assistant, "_safe_rows", return_value=[]):
            result = assistant.build_live_context(None, {"role": "salesperson", "id": 1, "salesperson_id": 7})
        self.assertNotIn("inventory_value", result)
        self.assertNotIn("cash_balance", result)
        self.assertNotIn("debt_total", result)
        self.assertNotIn("top_debtors", result)
        self.assertIn("my_customer_balances", result)
        self.assertIn("my_contract", result)

    def test_product_lookup_is_authorized_and_bounded(self):
        with patch.object(assistant, "role_has_module_permission", return_value=True), \
             patch.object(assistant, "_safe_rows", return_value=[]) as query:
            result = assistant.context_for_question(None, {"role": "salesperson", "salesperson_id": 7},
                                                    "قیمت کرم", {"today": "2026-10-13", "scope": "personal"})
        self.assertIn("products", result)
        self.assertIn("LIMIT 40", query.call_args.args[1])
        self.assertEqual(query.call_args.args[2]["term"], "%کرم%")

    def test_staff_management_finance_is_blocked_before_database_and_model(self):
        with patch.object(assistant.engine, "connect") as database, \
             patch.object(assistant, "call_gpt") as external:
            result = assistant.chat(assistant.ChatRequest(message="مانده خزانه شرکت چقدر است؟"),
                                    user={"id": 1, "role": "salesperson", "salesperson_id": 7})
        self.assertEqual(result["mode"], "access_limited")
        database.assert_not_called()
        external.assert_not_called()


if __name__ == "__main__":
    unittest.main()
