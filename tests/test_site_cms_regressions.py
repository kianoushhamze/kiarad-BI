"""CMS contract tests; optional SQL tests use a rolled-back, isolated schema."""
import os
import unittest
from contextlib import nullcontext
from uuid import uuid4
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy import text

import site_cms as cms

CEO = {"id": 1, "role": "ceo"}


class CmsContractTests(unittest.TestCase):
    def test_price_response_describes_local_update(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {"name": "Test", "price": 1000}
        with patch.object(cms.engine, "begin", return_value=nullcontext(conn)):
            result = cms.update_price("A", cms.PriceUpdate(price_irr=2000), CEO)
        self.assertEqual(result["new_price_irr"], 2000)
        self.assertIn("قیمت در نرم‌افزار هلو تغییر نکرده است", result["note"])

    def test_visitor_cannot_change_metadata_or_price(self):
        with patch.object(cms.engine, "begin") as begin:
            for action in (
                lambda: cms.patch_product_meta("A", cms.ProductMetaPatch(discount_price_irr=None), {"id": 2, "role": "visitor"}),
                lambda: cms.update_price("A", cms.PriceUpdate(price_irr=2000), {"id": 2, "role": "visitor"}),
            ):
                with self.assertRaises(HTTPException) as error:
                    action()
                self.assertEqual(error.exception.status_code, 403)
            begin.assert_not_called()


@unittest.skipUnless(os.getenv("KIARAD_TEST_CMS_DB") == "1", "Opt-in isolated PostgreSQL schema")
class CmsDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = cms.engine.connect()
        self.addCleanup(self.conn.close)
        transaction = self.conn.begin()
        self.addCleanup(transaction.rollback)
        schema = "cms_test_" + uuid4().hex
        self.conn.execute(text("CREATE SCHEMA " + schema))
        self.conn.execute(text("SET LOCAL search_path TO " + schema))
        self.conn.execute(text("CREATE TABLE products(code TEXT PRIMARY KEY, name TEXT, price BIGINT)"))
        self.conn.execute(text("INSERT INTO products VALUES ('A', 'Test', 1000)"))
        cms.ensure(self.conn)
        patcher = patch.object(cms, "engine")
        fake_engine = patcher.start()
        self.addCleanup(patcher.stop)
        fake_engine.begin.side_effect = lambda: nullcontext(self.conn)

    def update(self, **values):
        return cms.patch_product_meta("A", cms.ProductMetaPatch(**values), CEO)

    def row(self):
        return self.conn.execute(text("SELECT * FROM cms_product_meta WHERE code='A'")).mappings().one()

    def test_first_patch_without_hidden_creates_visible_product(self):
        self.update(site_category="Test category")
        self.assertIs(self.row()["hidden"], False)

    def test_discount_lifecycle_and_omitted_fields(self):
        self.update(discount_price_irr=800, hidden=True)
        self.assertEqual(self.row()["discount_price_irr"], 800)
        self.update(image_url="https://example.invalid/image.png")
        self.assertEqual(self.row()["discount_price_irr"], 800)
        self.assertIs(self.row()["hidden"], True)
        self.update(discount_price_irr=700)
        self.assertEqual(self.row()["discount_price_irr"], 700)
        self.update(discount_price_irr=None)
        self.assertIsNone(self.row()["discount_price_irr"])
        self.assertIs(self.row()["hidden"], True)

    def test_unknown_product_returns_404(self):
        with self.assertRaises(HTTPException) as error:
            cms.patch_product_meta("missing", cms.ProductMetaPatch(hidden=True), CEO)
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
