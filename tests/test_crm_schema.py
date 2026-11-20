"""CRM schema bootstrapping tests; no real database writes are performed."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CrmSchemaTests(unittest.TestCase):
    def test_versioned_migration_contains_required_fields_without_seed_rows(self):
        sql = (ROOT / "migrations" / "0007_chat_crm_storage.sql").read_text(encoding="utf-8-sig")
        for field in ("customer_name", "visitor_name", "next_followup_date", "followup_time", "status", "owner_user_id"):
            self.assertIn(field, sql)
        self.assertNotIn("INSERT INTO", sql.upper())


if __name__ == "__main__":
    unittest.main()
