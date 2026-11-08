import unittest

from holoo_dashboard_sync import _parse_invoice


class HolooDashboardSyncTests(unittest.TestCase):
    def test_valid_invoice_is_normalized(self):
        result = _parse_invoice({
            "SanadCode": "12", "customerCodeC": "C-1",
            "Date": "2026/10/17", "SumPrice": "1250.5",
        })
        self.assertEqual(result[0], 12)
        self.assertEqual(result[1], "C-1")
        self.assertEqual(result[2].date().isoformat(), "2026-10-17")
        self.assertEqual(result[3], 1250.5)

    def test_missing_identity_is_skipped(self):
        self.assertIsNone(_parse_invoice({"Date": "2026/10/17", "SumPrice": 1}))

    def test_invalid_date_is_skipped(self):
        self.assertIsNone(_parse_invoice({
            "SanadCode": 1, "customerCodeC": "C-1", "Date": "bad", "SumPrice": 1,
        }))


if __name__ == "__main__":
    unittest.main()
