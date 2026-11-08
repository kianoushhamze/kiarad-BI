"""Read-only Holoo contract tests; synthetic values and no external traffic."""
import time
import unittest

from holoo_finance import currency_factor, invoice_pages, numeric, safe_rows, summarize_snapshot, with_retry


class HolooFinanceTests(unittest.TestCase):
    def test_currency_unit_comes_from_settings_and_normalizes_arabic_yeh(self):
        self.assertEqual(currency_factor({"CurrencyUnit": [{"name": "RepVahedPooli", "string": "ريال"}]}), (1, "ریال"))
        self.assertEqual(currency_factor({"CurrencyUnit": [{"name": "RepVahedPooli", "string": "تومان"}]}), (10, "تومان"))

    def test_unknown_currency_is_not_assumed_rial(self):
        self.assertIsNone(currency_factor({"CurrencyUnit": [{"name": "RepVahedPooli", "string": "unknown"}]})[0])

    def test_safe_projection_removes_contacts_bank_numbers_and_token(self):
        self.assertEqual(safe_rows([{"Code": "1", "Name": "synthetic", "Mandeh": 100, "Mobile": "synthetic-private", "Token": "synthetic-token"}], "customers"), [{"Code": "1", "Name": "synthetic", "Mandeh": 100}])
        self.assertEqual(safe_rows([{"Code": "2", "Name": "bank", "Price": 50, "accountNumber": "private", "sheba": "private"}], "banks"), [{"Code": "2", "Name": "bank", "Price": 50}])

    def test_invoice_details_are_allowlisted_recursively(self):
        result = safe_rows([{"ErpCode": "1", "SumPrice": 100, "CustomerPhone": "private", "Detail": [{"ProductErpCode": "p1", "Price": 100, "Comment": "private"}]}], "invoices")
        self.assertNotIn("CustomerPhone", result[0])
        self.assertNotIn("Comment", result[0]["Detail"][0])

    def test_pagination_fetches_until_short_page(self):
        def fetch(path, token, timeout):
            page = int(path.split("page=")[1].split("&")[0])
            count = 200 if page == 1 else 1
            return {"invoice": [{"ErpCode": f"{page}-{i}", "SumPrice": 1} for i in range(count)]}
        rows, complete, warning = invoice_pages("synthetic", 2, "2026-03-21", "2026-10-19", fetch)
        self.assertEqual(len(rows), 201)
        self.assertTrue(complete)
        self.assertIsNone(warning)

    def test_ignored_pagination_is_incomplete_and_never_leaks_unknown_fields(self):
        page = [{"ErpCode": str(i), "SumPrice": 1, "secret": "private"} for i in range(200)]
        rows, complete, _ = invoice_pages("synthetic", 2, "2026-03-21", "2026-10-19", lambda *args, **kwargs: {"invoice": page})
        self.assertFalse(complete)
        self.assertEqual(len(rows), 200)
        self.assertNotIn("secret", rows[0])

    def test_deadline_stops_pagination_without_calling_holoo(self):
        rows, complete, warning = invoice_pages("synthetic", 2, "2026-03-21", "2026-10-19",
                                                lambda *args, **kwargs: self.fail("deadline must not fetch"),
                                                deadline=time.monotonic() - 1)
        self.assertEqual(rows, [])
        self.assertFalse(complete)
        self.assertIn("مهلت", warning)

    def test_transient_timeout_is_retried_once(self):
        calls = {"count": 0}

        def action():
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimeoutError("synthetic slow ERP")
            return {"ok": True}

        self.assertEqual(with_retry(action, delay=0), {"ok": True})
        self.assertEqual(calls["count"], 2)

    def test_permanent_error_surfaces_after_retries(self):
        calls = {"count": 0}

        def action():
            calls["count"] += 1
            raise TimeoutError("synthetic slow ERP")

        with self.assertRaises(TimeoutError):
            with_retry(action, delay=0)
        self.assertEqual(calls["count"], 2)

    def summary(self, rows, factor=1, complete=True):
        return summarize_snapshot({"sources": {"sales": {"rows": rows, "ok": True, "complete": complete}}, "currency_factor": factor, "from_date": "2026-03-21", "to_date": "2026-10-19"})

    def test_total_uses_verified_currency_and_preserves_no_profit_claim(self):
        result = self.summary([{"ErpCode": "1", "SumPrice": "125"}], factor=10)
        self.assertEqual(result["sources"][0]["total_irr"], 1250)
        self.assertFalse(result["net_profit_available"])

    def test_missing_amount_currency_or_partial_response_has_unknown_total(self):
        for result in (self.summary([{"ErpCode": "1"}]), self.summary([{"ErpCode": "1", "SumPrice": 100}], factor=None), self.summary([{"ErpCode": "1", "SumPrice": 100}], complete=False)):
            self.assertIsNone(result["sources"][0]["total_irr"])

    def test_duplicate_or_missing_invoice_keys_block_the_total(self):
        for rows in ([{"SumPrice": 10}], [{"ErpCode": "1", "SumPrice": 10}, {"ErpCode": "1", "SumPrice": 10}]):
            self.assertIsNone(self.summary(rows)["sources"][0]["total_irr"])

    def test_nonfinite_numeric_is_rejected(self):
        for value in (None, True, "NaN", "Infinity", "bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                numeric(value)


if __name__ == "__main__":
    unittest.main()
