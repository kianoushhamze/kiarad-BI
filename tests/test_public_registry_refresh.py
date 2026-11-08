import unittest
from public_registry_refresh import parse_my


class RefreshParserTests(unittest.TestCase):
    def test_only_province_and_exact_duplicates_removed(self):
        content = '''<table id="tablepress-1">
        <tr><td>تهران</td><td>خارج استان</td><td>نشانی</td></tr>
        <tr><td>اختیارآباد</td><td>آرامیس</td><td>نشانی اول</td></tr>
        <tr><td>کرمان</td><td>فروشگاه الف</td><td>نشانی دوم</td></tr>
        <tr><td>کرمان</td><td>فروشگاه الف</td><td>نشانی دوم</td></tr>
        <tr><td>نگار</td><td>داروخانه عقیلی</td><td>نشانی سوم</td></tr>
        <tr><td>تهران</td><td>خارج استان</td><td>نشانی</td></tr></table>'''.encode()
        rows = parse_my(content)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r['source_id'] for r in rows}), 3)
        self.assertFalse(any(r['city'] == 'تهران' for r in rows))
        self.assertEqual(parse_my(content)[0]['source_id'], rows[0]['source_id'])

    def test_missing_boundary_rejected(self):
        with self.assertRaises(ValueError):
            parse_my(b'<table id="tablepress-1"></table>')

    def test_ambiguous_boundary_rejected(self):
        content = '<table id="tablepress-1">' + '<tr><td>اختیارآباد</td><td>آرامیس</td><td>الف</td></tr>' * 2 + '<tr><td>نگار</td><td>داروخانه عقیلی</td><td>ب</td></tr></table>'
        with self.assertRaises(ValueError):
            parse_my(content.encode())
