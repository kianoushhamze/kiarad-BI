"""CRM schema bootstrapping tests; no real database writes are performed."""
import unittest
from unittest.mock import MagicMock

from api import _ensure_crm_table


class CrmSchemaTests(unittest.TestCase):
    def test_empty_schema_contains_required_fields_without_seed_rows(self):
        conn = MagicMock()
        _ensure_crm_table(conn)

        sql = "\n".join(str(call.args[0]) for call in conn.execute.call_args_list)
        for field in ("customer_name", "visitor_name", "next_followup_date", "followup_time", "status"):
            self.assertIn(field, sql)
        self.assertNotIn("INSERT INTO", sql.upper())


if __name__ == "__main__":
    unittest.main()
