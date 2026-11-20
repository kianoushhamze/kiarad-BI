"""CMS changes against disposable PostgreSQL schemas; never uses company data."""
import os
import base64
from pathlib import Path
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
        self.conn.execute(text("CREATE TABLE products(id SERIAL PRIMARY KEY, code TEXT UNIQUE, name TEXT, price BIGINT)"))
        self.conn.execute(text("CREATE TABLE customers(id SERIAL PRIMARY KEY, code TEXT UNIQUE, name TEXT, credit_limit NUMERIC)"))
        self.conn.execute(text("CREATE TABLE salespersons(id SERIAL PRIMARY KEY)"))
        self.conn.execute(text("INSERT INTO products(code,name,price) VALUES ('A','Synthetic product',10000)"))
        root = Path(__file__).resolve().parents[1]
        for migration in ("0005_cms_product_meta.sql", "0006_storefront_platform_storage.sql"):
            self.conn.exec_driver_sql((root / "migrations" / migration).read_text(encoding="utf-8-sig"))
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



    def test_product_image_urls_reject_scriptable_and_external_plain_http_targets(self):
        for value in ("javascript:alert(1)", "data:image/svg+xml,<svg>", "//attacker.invalid/image.png", "http://attacker.invalid/image.png", "https://user:pass@example.test/image.png"):
            with self.subTest(value=value):
                self.assertIsNone(cms._safe_public_link(value))
        self.assertEqual(cms._safe_public_link("/uploads/product.png"), "/uploads/product.png")
        self.assertEqual(cms._safe_public_link("https://cdn.example.test/product.png"), "https://cdn.example.test/product.png")

class BannerInputSecurityTests(unittest.TestCase):
    def test_banner_links_reject_scriptable_and_protocol_relative_urls(self):
        for value in ("javascript:alert(1)", "data:text/html,<script>", "//attacker.invalid/path", "https://user:pass@example.test/", "https://[::1"):
            with self.subTest(value=value), self.assertRaises(HTTPException):
                cms._clean_link_url(value)
        self.assertEqual(cms._clean_link_url("/campaign/summer"), "/campaign/summer")
        self.assertEqual(cms._clean_link_url("https://example.test/campaign"), "https://example.test/campaign")

    def test_legacy_unsafe_banner_link_is_not_returned_to_public_site(self):
        self.assertIsNone(cms._safe_public_link("javascript:alert(1)"))
        self.assertIsNone(cms._safe_public_link("//attacker.invalid"))
        self.assertEqual(cms._safe_public_link("/safe/path"), "/safe/path")

    def test_banner_upload_requires_real_supported_image_bytes(self):
        fake = base64.b64encode(b"not-an-image" * 8).decode("ascii")
        with self.assertRaises(HTTPException):
            cms._clean_image(fake)
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        encoded = base64.b64encode(png).decode("ascii")
        self.assertEqual(cms._image_media(cms._clean_image(encoded)), "image/png")
        with self.assertRaises(HTTPException):
            cms._clean_image("data:image/jpeg;base64," + encoded)
