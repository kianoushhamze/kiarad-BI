import unittest

from integrations import CHANNELS, channel_status


class IntegrationReadinessTests(unittest.TestCase):
    def test_every_requested_channel_is_available(self):
        self.assertEqual(
            set(CHANNELS),
            {"digikala", "basalam", "snappshop", "isam", "divar", "emalls", "torob", "instagram", "youtube", "tiktok", "linkedin", "telegram", "bale", "rubika", "whatsapp"},
        )

    def test_draft_and_old_sync_do_not_claim_live_connection(self):
        status = channel_status(
            "digikala",
            {"account_label": "shop", "notes": "pending", "updated_at": None},
            {"last_success": "old", "last_attempt": "new", "last_status": "failed"},
            0,
        )
        for flag in ("connected", "sync_enabled", "stock_push_enabled", "price_push_enabled"):
            self.assertFalse(status[flag])
        self.assertEqual(status["last_attempt_status"], "failed")


if __name__ == "__main__":
    unittest.main()
