"""PostgreSQL regressions for the CMS metadata migration and public feeds.

All writes are confined to a transaction-local disposable schema.
"""
import os
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import event, inspect, text

from db import engine
import marketplace_feeds as feeds
import api


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0005_cms_product_meta.sql"


@unittest.skipUnless(
    os.getenv("KIARAD_TEST_MARKETPLACE_FEEDS_DB") == "1",
    "Opt-in disposable PostgreSQL schema",
)
class MarketplaceFeedDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = engine.connect()
        self.addCleanup(self.conn.close)
        transaction = self.conn.begin()
        self.addCleanup(transaction.rollback)
        schema = "marketplace_feed_" + uuid4().hex
        self.conn.execute(text(f"CREATE SCHEMA {schema}"))
        self.conn.execute(text(f"SET LOCAL search_path TO {schema}"))
        self.conn.execute(text("""
            CREATE TABLE products (
                id BIGINT PRIMARY KEY,
                code VARCHAR(100) NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT,
                price BIGINT,
                stock NUMERIC NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """))
        self.conn.execute(text("""
            CREATE TABLE inventory_reservations (
                product_id BIGINT NOT NULL,
                quantity NUMERIC NOT NULL,
                status TEXT NOT NULL
            )
        """))
        self.conn.execute(text("""
            INSERT INTO products (id, code, name, category, price, stock, is_active) VALUES
                (1, 'A1', 'Synthetic shampoo', 'Hair', 10000, 5, 1),
                (2, 'B2', 'Synthetic cream', 'Skin', 20000, 1, 1),
                (3, 'C3', 'Hidden item', 'Skin', 30000, 10, 1)
        """))
        self.conn.execute(text("""
            INSERT INTO inventory_reservations (product_id, quantity, status) VALUES
                (1, 2, 'reserved'),
                (2, 1, 'reserved'),
                (1, 50, 'cancelled')
        """))

    def apply_migration(self):
        self.conn.exec_driver_sql(MIGRATION.read_text(encoding="utf-8"))

    def add_metadata_fixtures(self):
        self.apply_migration()
        self.conn.execute(text("""
            INSERT INTO cms_product_meta (code, site_category, image_url, hidden, discount_price_irr)
            VALUES
                ('A1', 'Hair care', '/uploads/a1.jpg', FALSE, 8000),
                ('C3', 'Skin care', '/uploads/c3.jpg', TRUE, NULL)
        """))

    def capture_ddl(self):
        statements = []

        def listener(conn, cursor, statement, parameters, context, executemany):
            first = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
            if first in {"CREATE", "ALTER", "DROP", "TRUNCATE"}:
                statements.append(statement)

        event.listen(self.conn, "before_cursor_execute", listener)
        return statements, listener

    def test_migration_creates_missing_table(self):
        self.apply_migration()
        columns = {column["name"] for column in inspect(self.conn).get_columns("cms_product_meta")}
        self.assertTrue({"code", "site_category", "image_url", "hidden", "updated_at", "discount_price_irr"} <= columns)

    def test_migration_upgrades_legacy_table_and_is_idempotent(self):
        self.conn.execute(text("""
            CREATE TABLE cms_product_meta (
                code VARCHAR(100) PRIMARY KEY,
                site_category TEXT,
                image_url TEXT,
                hidden BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        self.apply_migration()
        self.apply_migration()
        columns = {column["name"] for column in inspect(self.conn).get_columns("cms_product_meta")}
        self.assertIn("discount_price_irr", columns)

    def test_feed_reads_discount_visibility_and_reserved_stock_without_ddl(self):
        self.add_metadata_fixtures()
        statements, listener = self.capture_ddl()
        try:
            with patch.object(feeds.engine, "connect", return_value=nullcontext(self.conn)):
                items = feeds.load_items()
        finally:
            event.remove(self.conn, "before_cursor_execute", listener)

        self.assertEqual([item["page_unique"] for item in items], ["A1", "B2"])
        first, second = items
        self.assertEqual((first["current_price"], first["old_price"]), (800, 1000))
        self.assertEqual(first["availability"], "instock")
        self.assertEqual(second["availability"], "outofstock")
        self.assertNotIn("stock", first)
        self.assertEqual(statements, [], "Public feed requests must not execute schema DDL.")

    def test_public_catalog_reads_migrated_metadata_without_ddl(self):
        self.add_metadata_fixtures()
        statements, listener = self.capture_ddl()
        try:
            with patch.object(api.engine, "connect", return_value=nullcontext(self.conn)):
                result = api.public_catalog()
        finally:
            event.remove(self.conn, "before_cursor_execute", listener)

        self.assertEqual(result["currency"], "IRR")
        products = {item["code"]: item for item in result["products"]}
        self.assertEqual(set(products), {"A1", "B2"})
        self.assertEqual(products["A1"]["discount_price_irr"], 8000)
        self.assertEqual(products["A1"]["stock"], 3.0)
        self.assertEqual(products["B2"]["stock"], 0.0)
        self.assertEqual(statements, [], "Public catalog requests must not execute schema DDL.")


if __name__ == "__main__":
    unittest.main()
