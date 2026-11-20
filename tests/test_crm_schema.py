"""CRM schema and legacy ownership migration regressions."""
import os
import unittest
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0007_chat_crm_storage.sql"


class CrmSchemaTests(unittest.TestCase):
    def test_versioned_migration_contains_required_fields_without_seed_rows(self):
        sql = MIGRATION.read_text(encoding="utf-8-sig")
        for field in ("customer_name", "visitor_name", "next_followup_date", "followup_time", "status", "owner_user_id"):
            self.assertIn(field, sql)
        self.assertNotIn("INSERT INTO", sql.upper())

    def test_legacy_ownership_transfer_requires_one_exact_username_match(self):
        sql = MIGRATION.read_text(encoding="utf-8-sig")
        self.assertIn("ci.visitor_name IN (u.username, '@' || u.username)", sql)
        self.assertIn("HAVING COUNT(DISTINCT u.id) = 1", sql)
        self.assertNotIn("u.full_name", sql)


@unittest.skipUnless(
    os.getenv("KIARAD_TEST_CRM_SCHEMA_DB") == "1",
    "Opt-in disposable PostgreSQL schema",
)
class CrmOwnershipMigrationDatabaseTests(unittest.TestCase):
    def setUp(self):
        from db import engine

        self.conn = engine.connect()
        self.addCleanup(self.conn.close)
        transaction = self.conn.begin()
        self.addCleanup(transaction.rollback)
        self.assertEqual(self.conn.exec_driver_sql("SHOW search_path").scalar(), "pg_temp")

        self.conn.exec_driver_sql("""
            CREATE TEMP TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(100),
                full_name VARCHAR(160)
            )
        """)
        self.conn.exec_driver_sql("""
            CREATE TEMP TABLE customer_interactions (
                id INTEGER PRIMARY KEY,
                customer_name VARCHAR(200) NOT NULL,
                visitor_name VARCHAR(100),
                interaction_type VARCHAR(50),
                product_discussed VARCHAR(150),
                notes TEXT,
                next_followup_date DATE,
                followup_time VARCHAR(20),
                status VARCHAR(50) NOT NULL DEFAULT 'در انتظار تماس',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute(text("""
            INSERT INTO users (id, username, full_name) VALUES
                (1, 'alice', 'Alice Smith'),
                (2, 'bob', 'Bob Smith'),
                (3, 'duplicate', 'Duplicate One'),
                (4, 'duplicate', 'Duplicate Two')
        """))
        self.conn.execute(text("""
            INSERT INTO customer_interactions (id, customer_name, visitor_name) VALUES
                (101, 'Exact username without prefix', 'alice'),
                (102, 'Exact username with prefix', '@bob'),
                (103, 'Display name only', 'Alice Smith'),
                (104, 'Unmatched label', 'unknown-user'),
                (105, 'Ambiguous duplicate username', 'duplicate')
        """))

    def apply_migration(self):
        self.conn.exec_driver_sql(MIGRATION.read_text(encoding="utf-8-sig"))

    def test_only_unique_exact_usernames_transfer_and_migration_is_idempotent(self):
        self.apply_migration()
        owners = {
            row.id: row.owner_user_id
            for row in self.conn.execute(text(
                "SELECT id, owner_user_id FROM customer_interactions ORDER BY id"
            ))
        }
        self.assertEqual(owners, {
            101: 1,
            102: 2,
            103: None,
            104: None,
            105: None,
        })

        self.conn.execute(text("UPDATE users SET username='alice-renamed' WHERE id=1"))
        self.apply_migration()
        self.assertEqual(
            self.conn.execute(text(
                "SELECT owner_user_id FROM customer_interactions WHERE id=101"
            )).scalar_one(),
            1,
        )


if __name__ == "__main__":
    unittest.main()
