"""Synthetic purchase-profit evidence checks; no database or external traffic."""
import json
import unittest

import jdatetime

from purchase_profit import estimate_purchase_profit


class PurchaseProfitTests(unittest.TestCase):
    def line(self, quantity=10, price=100, product="p1", **extra):
        return {"ProductErpCode": product, "Few": quantity, "Price": price,
                "SumPrice": quantity * price, **extra}

    def invoice(self, ident, day, lines, total=None, **extra):
        return {"ErpCode": str(ident), "Date": day, "Detail": lines,
                "SumPrice": total if total is not None else sum(line["SumPrice"] for line in lines), **extra}

    def payload(self, purchases=None, sales=None, purchase_returns=None, sales_returns=None,
                start="2026-10-01", end="2026-10-31", **extra):
        return {"from_date": start, "to_date": end, "currency_factor": 1,
                "sources": {kind: {"ok": True, "complete": True, "rows": rows or []}
                            for kind, rows in {"purchases": purchases, "sales": sales,
                                               "purchase_returns": purchase_returns,
                                               "sales_returns": sales_returns}.items()}, **extra}

    def month(self, result, month="1405-07"):
        return next(row for row in result["months"] if row["month"] == month)

    def test_purchase_offer_spreads_net_cost_over_paid_and_free_same_product(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100), self.line(2, 0)], total=900, SumDiscount=100)
        sale = self.invoice(2, "2026-10-02", [self.line(6, 150)])
        result = estimate_purchase_profit(self.payload([purchase], [sale]), 0)
        month = self.month(result)
        self.assertEqual(month["estimated_cogs_irr"], 450)
        self.assertEqual(month["estimated_gross_profit_irr"], 450)
        self.assertFalse(result["approved_profit"])
        self.assertFalse(result["opening_inventory_known"])
        self.assertIsNone(month["net_profit_irr"])

    def test_equivalent_amount_and_percent_discount_are_not_added(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100, Discount=100, PersentDiscount=10)], total=900, SumDiscount=100)
        sale = self.invoice(2, "2026-10-02", [self.line(1, 150)])
        month = self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))
        self.assertEqual(month["estimated_cogs_irr"], 90)

    def test_net_line_sum_is_not_discounted_twice(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100, SumPrice=900, Discount=100)], total=900, SumDiscount=100)
        sale = self.invoice(2, "2026-10-02", [self.line(1, 150)])
        self.assertEqual(self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))["estimated_cogs_irr"], 90)

    def test_additional_header_discount_reconciles_once(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100, Discount=100)], total=850, SumDiscount=50)
        sale = self.invoice(2, "2026-10-02", [self.line(1, 150)])
        self.assertEqual(self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))["estimated_cogs_irr"], 85)

    def test_header_discount_containing_line_discount_is_not_repeated(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100, Discount=100)], total=850, SumDiscount=150)
        sale = self.invoice(2, "2026-10-02", [self.line(1, 150)])
        self.assertEqual(self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))["estimated_cogs_irr"], 85)

    def test_contradictory_discount_stays_unknown(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100, Discount=100, PersentDiscount=20)], total=900)
        sale = self.invoice(2, "2026-10-02", [self.line(1, 150)])
        result = estimate_purchase_profit(self.payload([purchase], [sale]), 0)
        self.assertIsNone(self.month(result)["estimated_net_profit_irr"])
        self.assertIn("invoice_amount_ambiguous", [row["code"] for row in result["blockers"]])

    def test_sales_gift_has_cost_and_zero_revenue(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(20, 100)])
        sale = self.invoice(2, "2026-10-02", [self.line(10, 150), self.line(2, 0)])
        month = self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))
        self.assertEqual(month["net_sales_irr"], 1500)
        self.assertEqual(month["estimated_cogs_irr"], 1200)
        self.assertEqual(month["estimated_net_profit_irr"], 300)

    def test_future_purchase_never_costs_previous_sale(self):
        purchase = self.invoice(1, "2026-10-03", [self.line(20, 100)])
        sale = self.invoice(2, "2026-10-02", [self.line(10, 150)])
        month = self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))
        self.assertIsNone(month["estimated_cogs_irr"])
        self.assertIsNone(month["estimated_net_profit_irr"])

    def test_same_day_purchase_without_order_never_costs_sale(self):
        purchase = self.invoice(1, "2026-10-02", [self.line(20, 100)])
        sale = self.invoice(2, "2026-10-02", [self.line(10, 150)])
        self.assertIsNone(self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))["estimated_cogs_irr"])

    def test_explicit_earlier_time_allows_same_day_purchase(self):
        purchase = self.invoice(1, "2026-10-02", [self.line(20, 100)], Time="09:00:00")
        sale = self.invoice(2, "2026-10-02", [self.line(10, 150)], Time="10:00:00")
        self.assertEqual(self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))["estimated_cogs_irr"], 1000)

    def test_equal_time_does_not_prove_order(self):
        purchase = self.invoice(1, "2026-10-02", [self.line(20, 100)], Time="10:00:00")
        sale = self.invoice(2, "2026-10-02", [self.line(10, 150)], Time="10:00:00")
        self.assertIsNone(self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))["estimated_cogs_irr"])

    def test_sale_exceeding_known_quantity_has_unknown_cost(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(2, 100)])
        sale = self.invoice(2, "2026-10-02", [self.line(3, 150)])
        self.assertIsNone(self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))["estimated_cogs_irr"])

    def test_overdrawn_stock_is_not_reused_by_later_sales(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(2, 100)])
        sales = [self.invoice(2, "2026-10-02", [self.line(3, 150)]), self.invoice(3, "2026-10-03", [self.line(1, 150)])]
        result = estimate_purchase_profit(self.payload([purchase], sales), 0)
        self.assertEqual(self.month(result)["costed_sales_lines"], 0)

    def test_different_product_gift_needs_cost_allocation_policy(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100), self.line(2, 0, product="p2")])
        sale = self.invoice(2, "2026-10-02", [self.line(1, 150, product="p2")])
        result = estimate_purchase_profit(self.payload([purchase], [sale]), 0)
        self.assertIsNone(self.month(result)["estimated_cogs_irr"])
        self.assertIn("mixed_product_offer_allocation_unknown", [row["code"] for row in result["blockers"]])

    def test_moving_average_changes_only_after_receipt(self):
        purchases = [self.invoice(1, "2026-10-01", [self.line(10, 100)]), self.invoice(2, "2026-10-04", [self.line(10, 200)])]
        sales = [self.invoice(3, "2026-10-02", [self.line(5, 300)]), self.invoice(4, "2026-10-05", [self.line(3, 300)])]
        month = self.month(estimate_purchase_profit(self.payload(purchases, sales), 0))
        self.assertEqual(month["estimated_cogs_irr"], 1000)

    def test_purchase_return_reduces_known_pool_quantity_and_value(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100)])
        returned = self.invoice(2, "2026-10-02", [self.line(2, 100)])
        sale = self.invoice(3, "2026-10-03", [self.line(8, 150)])
        month = self.month(estimate_purchase_profit(self.payload([purchase], [sale], [returned]), 0))
        self.assertEqual(month["estimated_cogs_irr"], 800)

    def test_sales_return_restores_known_original_cost(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100)])
        sale = self.invoice(2, "2026-10-02", [self.line(5, 150)])
        returned = self.invoice(3, "2026-10-03", [self.line(2, 150)])
        month = self.month(estimate_purchase_profit(self.payload([purchase], [sale], sales_returns=[returned]), 0))
        self.assertEqual(month["net_sales_irr"], 450)
        self.assertEqual(month["estimated_cogs_irr"], 300)

    def test_unknown_original_sales_return_cost_is_not_zero(self):
        returned = self.invoice(3, "2026-10-03", [self.line(2, 150)])
        month = self.month(estimate_purchase_profit(self.payload(sales_returns=[returned]), 0))
        self.assertIsNone(month["estimated_cogs_irr"])

    def test_missing_currency_is_blocked(self):
        result = estimate_purchase_profit(self.payload(currency_factor=None))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["months"], [])

    def test_incomplete_source_blocks_full_month_profit(self):
        payload = self.payload()
        payload["sources"]["purchases"]["complete"] = False
        result = estimate_purchase_profit(payload)
        self.assertTrue(all(row["estimated_net_profit_irr"] is None for row in result["months"]))

    def test_unverified_purchase_tax_blocks_final_estimate_but_retains_reference(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100)], total=1100, SumLevy=100)
        sale = self.invoice(2, "2026-10-02", [self.line(5, 150)])
        month = self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))
        self.assertIsNone(month["estimated_net_profit_irr"])
        self.assertEqual(month["estimated_profit_before_unverified_purchase_tax_irr"], 250)

    def test_sales_tax_is_excluded_from_merchandise_revenue(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100)])
        sale = self.invoice(2, "2026-10-02", [self.line(5, 150)], total=825, SumLevy=75)
        month = self.month(estimate_purchase_profit(self.payload([purchase], [sale]), 0))
        self.assertEqual(month["net_sales_irr"], 750)
        self.assertEqual(month["estimated_net_profit_irr"], 250)

    def test_explicit_gross_header_reconciles_payments_and_discount_once(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100, PersentDiscount=10)], total=1000, SumDiscount=150,
                                SumNaghd=850, SumCard=0, SumNesiyeh=0, SumCheck=0)
        sale = self.invoice(2, "2026-10-02", [self.line(5, 150, PersentDiscount=10)], total=750, SumDiscount=75,
                            SumNaghd=0, SumCard=0, SumNesiyeh=675, SumCheck=0)
        semantics = {kind: {"header_sum_price": "gross_before_discount_tax", "header_discount_scope": "includes_line_discounts"}
                     for kind in ("purchases", "sales", "purchase_returns", "sales_returns")}
        month = self.month(estimate_purchase_profit(self.payload([purchase], [sale], invoice_amount_semantics=semantics), 0))
        self.assertEqual(month["net_sales_irr"], 675)
        self.assertEqual(month["estimated_cogs_irr"], 425)
        self.assertEqual(month["purchase_gross_irr"], 1000)
        self.assertEqual(month["purchase_discount_irr"], 150)
        self.assertEqual(month["purchase_net_irr"], 850)
        self.assertEqual(month["sales_discount_irr"], 75)

    def test_payment_mismatch_blocks_invoice(self):
        sale = self.invoice(1, "2026-10-02", [self.line(5, 150)], SumNaghd=700, SumCard=0, SumNesiyeh=0, SumCheck=0)
        month = self.month(estimate_purchase_profit(self.payload(sales=[sale]), 0))
        self.assertIsNone(month["net_sales_irr"])

    def test_purchase_header_rounding_preserves_authoritative_total(self):
        lines = [self.line(1, 100, product="p1") for _ in range(6)]
        purchase = self.invoice(1, "2026-10-01", lines, total=597.8,
                                SumNaghd=597.8, SumCard=0, SumNesiyeh=0, SumCheck=0)
        sale = self.invoice(2, "2026-10-02", [self.line(6, 150)])
        semantics = {kind: {"header_sum_price": "gross_before_discount_tax", "header_discount_scope": "includes_line_discounts"}
                     for kind in ("purchases", "sales")}
        month = self.month(estimate_purchase_profit(self.payload([purchase], [sale], invoice_amount_semantics=semantics), 0))
        self.assertEqual(month["estimated_cogs_irr"], 598)
        self.assertEqual(month["purchase_net_irr"], 598)

    def test_revenue_is_independent_of_incomplete_purchase_source(self):
        sale = self.invoice(1, "2026-10-02", [self.line(5, 150)])
        payload = self.payload(sales=[sale])
        payload["sources"]["purchases"]["complete"] = False
        month = self.month(estimate_purchase_profit(payload, 0))
        self.assertEqual(month["net_sales_irr"], 750)
        self.assertIsNone(month["estimated_net_profit_irr"])

    def test_combined_expense_once_and_partial_month_proration(self):
        start = jdatetime.date(1405, 7, 1).togregorian().isoformat()
        end = jdatetime.date(1405, 7, 15).togregorian().isoformat()
        month = self.month(estimate_purchase_profit(self.payload(start=start, end=end)))
        self.assertEqual(month["budget_full_month_expense_irr"], 3000000000)
        self.assertEqual(month["budget_expense_for_period_irr"], 1500000000)
        self.assertEqual(month["estimated_net_profit_irr"], -1500000000)

    def test_toman_currency_applies_exactly_once(self):
        purchase = self.invoice(1, "2026-10-01", [self.line(10, 100)])
        sale = self.invoice(2, "2026-10-02", [self.line(5, 150)])
        result = estimate_purchase_profit(self.payload([purchase], [sale], currency_factor=10), 0)
        self.assertEqual(self.month(result)["estimated_cogs_irr"], 5000)
        self.assertEqual(self.month(result)["estimated_net_profit_irr"], 2500)
        json.dumps(result, allow_nan=False)

    def test_duplicate_invoice_blocks_complete_results(self):
        sale = self.invoice(1, "2026-10-02", [self.line(5, 150)])
        result = estimate_purchase_profit(self.payload(sales=[sale, sale]), 0)
        self.assertFalse(result["coverage"]["all_sources_complete"])
        self.assertIsNone(self.month(result)["estimated_net_profit_irr"])


if __name__ == "__main__":
    unittest.main()
