"""Unit tests for route_builder (no database): area extraction and route grouping."""
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

import route_builder as rb
from route_builder import build_proposal, chunk_routes, extract_area


MANAGER = {"id": 1, "role": "ceo", "username": "admin", "full_name": "مدیر"}
SALES = {"id": 2, "role": "salesperson", "username": "field", "full_name": "ویزیتور"}


class ExtractAreaTests(unittest.TestCase):
    def test_street_keyword(self):
        self.assertEqual(extract_area("کرمان، خیابان شریعتی، نبش کوچه ۵"), "خیابان شریعتی")

    def test_boulevard_two_tokens(self):
        self.assertEqual(extract_area("بلوار جمهوری اسلامی، پلاک ۱۲"), "بلوار جمهوری")

    def test_flke_and_meydan(self):
        self.assertEqual(extract_area("فلکه گلها"), "فلکه گلها")
        self.assertEqual(extract_area("میدان شهدا"), "میدان شهدا")

    def test_takes_last_match(self):
        self.assertEqual(extract_area("خیابان فردوسی، جنب بازار سردار"), "بازار سردار")

    def test_stops_before_connector_words(self):
        self.assertEqual(extract_area("بلوار امام خمینی، نبش خیابان اعلمی"), "خیابان اعلمی")

    def test_empty_or_none(self):
        self.assertIsNone(extract_area(None))
        self.assertIsNone(extract_area(""))
        self.assertIsNone(extract_area("بدون نشانه محله"))


class ChunkTests(unittest.TestCase):
    def test_even_chunks(self):
        self.assertEqual(chunk_routes(list(range(10)), 3), [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]])

    def test_empty(self):
        self.assertEqual(chunk_routes([], 5), [])

    def test_per_route_minimum_one(self):
        self.assertEqual(chunk_routes([1, 2], 0), [[1], [2]])


class BuildProposalTests(unittest.TestCase):
    def test_groups_by_city_and_area(self):
        rows = [
            {"name": "دکتر الف", "city": "کرمان", "address": "خیابان شریعتی ۱"},
            {"name": "دکتر ب", "city": "کرمان", "address": "خیابان شریعتی ۲"},
            {"name": "بازار الف", "city": "کرمان", "address": "بازار بزرگ"},
            {"name": "پایگاه سیرجان", "city": "سیرجان", "address": "بلوار امام"},
        ]
        proposal = build_proposal(rows, "physicians", 2, "morning")
        self.assertEqual(proposal["summary"], {"cities": 2, "routes": 3})
        self.assertEqual(proposal["total_items"], 4)
        kerman = next(c for c in proposal["cities"] if c["city"] == "کرمان")
        titles = {r["area"] for r in kerman["routes"]}
        self.assertEqual(titles, {"خیابان شریعتی", "بازار بزرگ"})
        self.assertEqual([r["route"] for r in kerman["routes"]], ["مسیر ۱", "مسیر ۲"])
        self.assertTrue(all(r["session"] == "صبح" for r in kerman["routes"]))
        street = next(r for r in kerman["routes"] if r["area"] == "خیابان شریعتی")
        self.assertEqual(street["stops"], ["دکتر الف", "دکتر ب"])

    def test_city_filter_and_spread_bucket(self):
        rows = [
            {"name": "الف", "city": "کرمان", "address": "خیابان شریعتی"},
            {"name": "ب", "city": "کرمان", "address": None},
            {"name": "بومی", "city": "رفسنجان", "address": "خیابان عزیزی"},
        ]
        proposal = build_proposal(rows, "bases", 10, "evening", city="کرمان")
        self.assertEqual(proposal["total_items"], 2)
        self.assertEqual(proposal["summary"]["cities"], 1)
        areas = [r["area"] for r in proposal["cities"][0]["routes"]]
        self.assertIn("پراکنده", areas)
        self.assertTrue(all(r["session"] == "عصر" for r in proposal["cities"][0]["routes"]))


class AccessTests(unittest.TestCase):
    def test_ceo_passes(self):
        self.assertEqual(rb._manager(MANAGER), MANAGER)

    def test_salesperson_rejected(self):
        with patch.object(rb, "role_has_module_permission", return_value=False):
            with self.assertRaises(HTTPException) as caught:
                rb._manager(SALES)
            self.assertEqual(caught.exception.status_code, 403)

    def test_role_with_manager_write_passes(self):
        officer = {"id": 3, "role": "ops_manager", "username": "ops", "full_name": "کارشناس"}
        with patch.object(rb, "role_has_module_permission", return_value=True):
            self.assertEqual(rb._manager(officer), officer)


class ImportJsonlTests(unittest.TestCase):
    def test_missing_file_returns_reason(self):
        with patch.object(rb, "PHYSICIANS_JSONL", rb.Path("no/such/file.jsonl")):
            result = rb.import_physicians_jsonl(MANAGER)
            self.assertFalse(result["imported"])
            self.assertIn("یافت نشد", result["reason"])


if __name__ == "__main__":
    unittest.main()
