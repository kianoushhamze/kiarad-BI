"""CMS changes against disposable PostgreSQL schemas; never uses company data."""
import os
import unittest
from contextlib import nullcontext
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
import site_cms as cms
from db import engine

CEO = {"id": 1, "role": "ceo"}


class CMSAccessTests(unittest.TestCase):
    def test_visitor_cannot_change_product_or_price(self):
        for action in (
            lambda: cms.patch_product_meta("A", cms.ProductMetaPatch(), {"id": 2, "role": "visitor"}),
            lambda: cms.update_price("A", cms.PriceUpdate(price_irr=1000), {"id": 2, "role": "visitor"}),
        ):
            with self.assertRaises(HTTPException) as error:
                action()
            self.assertEqual(error.exception.status_code, 403)


@unittest.skipUnless(os.getenv("KIARAD_TEST_CMS_DB") == "1", "Opt-in disposable PostgreSQL schema")
class CMSDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = engine.connect()
        self.addCleanup(self.conn.close)
        transaction = self.conn.begin()
        self.addCleanup(transaction.rollback)
        schema = "cms_test_" + uuid4().hex
        self.conn.execute(text(f"CREATE SCHEMA {schema}"))
        self.conn.execute(text(f"SET LOCAL search_path TO {schema}"))
        self.conn.execute(text("CREATE TABLE products(code TEXT PRIMARY KEY, name TEXT, price BIGINT)"))
        self.conn.execute(text("INSERT INTO products VALUES ('A','Synthetic product',10000)"))
        patcher = patch.object(cms, "engine")
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        mocked.begin.side_effect = lambda: nullcontext(self.conn)

    def metadata(self):
        return self.conn.execute(text("SELECT hidden, discount_price_irr FROM cms_product_meta WHERE code='A'")).mappings().one()

    def test_first_patch_defaults_visibility(self):
        cms.patch_product_meta("A", cms.ProductMetaPatch(image_url="/test.png"), CEO)
        self.assertIs(self.metadata()["hidden"], False)

    def test_discount_set_preserve_replace_and_clear(self):
        for payload, expected in (
            ({"discount_price_irr": 8000}, 8000),
            ({"site_category": "Test"}, 8000),
            ({"discount_price_irr": 7000}, 7000),
            ({"discount_price_irr": None}, None),
        ):
            cms.patch_product_meta("A", cms.ProductMetaPatch(**payload), CEO)
            self.assertEqual(self.metadata()["discount_price_irr"], expected)

    def test_omitted_visibility_preserves_hidden_product(self):
        cms.patch_product_meta("A", cms.ProductMetaPatch(hidden=True), CEO)
        cms.patch_product_meta("A", cms.ProductMetaPatch(discount_price_irr=8000), CEO)
        self.assertIs(self.metadata()["hidden"], True)

    def test_price_change_reports_local_scope(self):
        result = cms.update_price("A", cms.PriceUpdate(price_irr=12000), CEO)
        self.assertEqual(self.conn.execute(text("SELECT price FROM products WHERE code='A'")).scalar_one(), 12000)
        self.assertEqual(result["old_price_irr"], 10000)
        self.assertIn("در هلو تغییر نمی‌دهد", result["note"])
