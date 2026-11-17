"""Feed mapping tests; no database or network."""
import unittest

import marketplace_feeds as mf

BASE = "https://shop.example.ir"


class FeedMappingTests(unittest.TestCase):
    def row(self, **kw):
        base = {"code": "A1", "name": "شامپو", "category": "مو", "price": 4_745_000, "image_url": "/uploads/a.jpg", "discount_price_irr": None}
        base.update(kw)
        return base

    def test_price_converted_to_toman_and_urls_absolute(self):
        item = mf.build_item(self.row(), BASE, 5)
        self.assertEqual(item["current_price"], 474_500)
        self.assertEqual(item["old_price"], 0)
        self.assertEqual(item["image_link"], BASE + "/uploads/a.jpg")
        self.assertEqual(item["page_url"], BASE + "/buy/?p=A1")
        self.assertEqual(item["availability"], "instock")

    def test_discount_becomes_current_price(self):
        item = mf.build_item(self.row(discount_price_irr=4_000_000), BASE, 1)
        self.assertEqual((item["current_price"], item["old_price"]), (400_000, 474_500))

    def test_invalid_discount_is_ignored(self):
        item = mf.build_item(self.row(discount_price_irr=9_000_000), BASE, 1)
        self.assertEqual(item["current_price"], 474_500)

    def test_zero_stock_is_outofstock_and_no_stock_number_leaks(self):
        item = mf.build_item(self.row(), BASE, 0)
        self.assertEqual(item["availability"], "outofstock")
        self.assertNotIn("stock", item)

    def test_unpriced_product_is_not_published(self):
        self.assertIsNone(mf.build_item(self.row(price=None), BASE, 3))
        self.assertIsNone(mf.build_item(self.row(price=0), BASE, 3))

    def test_paging(self):
        items = [{"page_unique": str(i)} for i in range(250)]
        page = mf.page_slice(items, 3)
        self.assertEqual((page["count"], page["max_pages"]), (50, 3))
        self.assertEqual(mf.page_slice([], 1)["max_pages"], 1)

    def test_single_lookup(self):
        items = [mf.build_item(self.row(), BASE, 1)]
        self.assertIsNotNone(mf._find_single(items, "A1", None))
        self.assertIsNotNone(mf._find_single(items, None, BASE + "/buy/?p=A1/"))
        self.assertIsNone(mf._find_single(items, "ZZ", None))

    def test_csv_has_bom_and_header(self):
        out = mf.to_csv([mf.build_item(self.row(), BASE, 1)])
        self.assertTrue(out.startswith("\ufeffpage_unique,title"))


if __name__ == "__main__":
    unittest.main()
