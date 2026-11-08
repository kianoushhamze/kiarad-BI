"""Mocked cancellation tests; no real database rows are changed."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from proformas import _holoo_queue_readiness, approve_proforma, cancel_proforma, queue_proforma, reject_proforma


class ProformaCancellationTests(unittest.TestCase):
    def setUp(self):
        self.transaction = MagicMock()
        self.conn = self.transaction.__enter__.return_value
        self.proforma_result = MagicMock()
        self.proforma_result.mappings.return_value.first.return_value = {
            "id": 17,
            "salesperson_id": 4,
            "status": "approved",
        }
        self.conn.execute.side_effect = [self.proforma_result, MagicMock(rowcount=1), MagicMock(rowcount=2)]
        self.begin_patch = patch("proformas.engine.begin")
        self.begin = self.begin_patch.start()
        self.addCleanup(self.begin_patch.stop)
        self.begin.return_value.__enter__.return_value = self.conn

    def test_owner_cancels_and_reservations_are_released(self):
        result = cancel_proforma(17, {"role": "salesperson", "salesperson_id": 4})

        self.assertEqual(result, {"proforma_id": 17, "status": "cancelled", "reservations_released": 2})
        self.assertEqual(self.conn.execute.call_count, 3)
        self.assertIn("SET status = 'cancelled'", str(self.conn.execute.call_args_list[1].args[0]))
        self.assertIn("SET status = 'released'", str(self.conn.execute.call_args_list[2].args[0]))

    def test_other_salesperson_cannot_cancel(self):
        with self.assertRaises(HTTPException) as raised:
            cancel_proforma(17, {"role": "salesperson", "salesperson_id": 9})

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.conn.execute.call_count, 1)

    def test_already_cancelled_is_idempotent(self):
        self.proforma_result.mappings.return_value.first.return_value["status"] = "cancelled"

        result = cancel_proforma(17, {"role": "salesperson", "salesperson_id": 4})

        self.assertEqual(result, {"proforma_id": 17, "status": "cancelled", "reservations_released": 0})
        self.assertEqual(self.conn.execute.call_count, 1)

    def test_unknown_proforma_returns_404(self):
        self.proforma_result.mappings.return_value.first.return_value = None

        with self.assertRaises(HTTPException) as raised:
            cancel_proforma(404, {"role": "ceo"})

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(self.conn.execute.call_count, 1)

    def test_manager_can_cancel_another_salespersons_proforma(self):
        result = cancel_proforma(17, {"role": "ceo"})
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reservations_released"], 2)

    def test_queue_accepts_approved_with_items(self):
        self.proforma_result.mappings.return_value.first.return_value["items_json"] = [{"product_id": 1, "quantity": 2}]
        queue_result = MagicMock()
        queue_result.mappings.return_value.first.return_value = {
            "id": 8, "operation_key": "holoo:proforma:17", "status": "pending", "attempt_count": 0,
        }
        self.conn.execute.side_effect = [self.proforma_result, queue_result, MagicMock(rowcount=1)]
        result = queue_proforma(17, {"role": "ceo"})
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["operation_key"], "holoo:proforma:17")
        self.assertEqual(result["queue_status"], "pending")
        self.assertFalse(result["external_submission"])
        self.assertEqual(self.conn.execute.call_count, 3)

    def test_queue_repeat_does_not_duplicate(self):
        self.proforma_result.mappings.return_value.first.return_value["status"] = "queued"
        self.proforma_result.mappings.return_value.first.return_value["items_json"] = [{"product_id": 1, "quantity": 2}]
        queue_result = MagicMock()
        queue_result.mappings.return_value.first.return_value = {
            "id": 8, "operation_key": "holoo:proforma:17", "status": "pending", "attempt_count": 0,
        }
        self.conn.execute.side_effect = [self.proforma_result, queue_result]
        self.assertEqual(queue_proforma(17, {"role": "ceo"})["status"], "queued")
        self.assertEqual(self.conn.execute.call_count, 2)
        self.assertIn("ON CONFLICT", str(self.conn.execute.call_args_list[1].args[0]))

    def test_queue_rejects_pending_or_cancelled(self):
        for status in ("pending", "cancelled"):
            with self.subTest(status=status):
                self.proforma_result.mappings.return_value.first.return_value["status"] = status
                self.conn.execute.reset_mock()
                self.conn.execute.side_effect = [self.proforma_result]
                with self.assertRaises(HTTPException) as raised:
                    queue_proforma(17, {"role": "ceo"})
                self.assertEqual(raised.exception.status_code, 409)
                self.assertEqual(self.conn.execute.call_count, 1)

    def test_manager_approves_pending_proforma(self):
        self.proforma_result.mappings.return_value.first.return_value = {"status": "pending"}
        self.conn.execute.side_effect = [self.proforma_result, MagicMock(rowcount=1)]
        result = approve_proforma(17, {"role": "ceo"})
        self.assertEqual(result, {"proforma_id": 17, "status": "approved"})
        self.assertIn("status='approved'", str(self.conn.execute.call_args_list[1].args[0]))

    def test_manager_rejects_pending_and_releases_reservations(self):
        self.proforma_result.mappings.return_value.first.return_value = {"status": "pending"}
        self.conn.execute.side_effect = [self.proforma_result, MagicMock(rowcount=1), MagicMock(rowcount=2)]
        result = reject_proforma(17, {"role": "ceo"})
        self.assertEqual(result, {"proforma_id": 17, "status": "rejected", "reservations_released": 2})
        self.assertIn("status='rejected'", str(self.conn.execute.call_args_list[1].args[0]))
        self.assertIn("status='released'", str(self.conn.execute.call_args_list[2].args[0]))

    def test_reject_is_idempotent(self):
        self.proforma_result.mappings.return_value.first.return_value = {"status": "rejected"}
        self.conn.execute.side_effect = [self.proforma_result]
        self.assertEqual(
            reject_proforma(17, {"role": "ceo"}),
            {"proforma_id": 17, "status": "rejected", "reservations_released": 0},
        )
        self.assertEqual(self.conn.execute.call_count, 1)

    def test_finalized_proforma_cannot_be_cancelled(self):
        for status in ("invoiced", "sent", "completed"):
            with self.subTest(status=status):
                self.proforma_result.mappings.return_value.first.return_value["status"] = status
                self.conn.execute.reset_mock()
                self.conn.execute.side_effect = [self.proforma_result]
                with self.assertRaises(HTTPException) as raised:
                    cancel_proforma(17, {"role": "ceo"})
                self.assertEqual(raised.exception.status_code, 409)
                self.assertEqual(self.conn.execute.call_count, 1)

    def test_holoo_preflight_accepts_complete_codes(self):
        result = _holoo_queue_readiness(
            "C-10", [{"product_id": 3, "quantity": 2}], {3: "P-3"},
        )
        self.assertEqual(result, {"mapping_ready": True, "blockers": []})

    def test_holoo_preflight_reports_all_missing_codes(self):
        result = _holoo_queue_readiness(
            "", [{"product_id": 3, "quantity": 2}, {"product_id": 4, "quantity": 1}], {3: ""},
        )
        self.assertFalse(result["mapping_ready"])
        self.assertEqual(len(result["blockers"]), 2)
        self.assertIn("مشتری", result["blockers"][0])
        self.assertIn("کالا", result["blockers"][1])

    def test_holoo_preflight_rejects_empty_items(self):
        result = _holoo_queue_readiness("C-10", [], {})
        self.assertEqual(result, {"mapping_ready": False, "blockers": ["پیش‌فاکتور قلم معتبر ندارد"]})


if __name__ == "__main__":
    unittest.main()
