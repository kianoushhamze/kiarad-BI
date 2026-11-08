import csv
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import daily_proforma_export as exporter


class DailyExportSafetyTests(unittest.TestCase):
    def test_text_formula_prefixes_are_escaped_without_changing_numbers(self):
        for value in ('=SUM(1,2)', '+cmd', '-text', '@SUM(1)', ' \t=link'):
            self.assertEqual(exporter.safe_csv_cell(value), "'" + value)
        self.assertEqual(exporter.safe_csv_cell(Decimal('-12.5')), Decimal('-12.5'))
        self.assertEqual(exporter.safe_csv_cell('داروخانه'), 'داروخانه')

    def test_export_is_private_read_only_and_protects_free_text(self):
        rows=[{'id':1,'customer_name':'=formula','salesperson_name':'آزمون','total_amount':123,
               'items_json':[{'product_name':'@product','quantity':2}],'notes':' +formula'}]
        calls=[]
        def execute(query,params):
            calls.append((str(query),params))
            return SimpleNamespace(mappings=lambda:SimpleNamespace(all=lambda:rows))
        engine=SimpleNamespace(connect=lambda:nullcontext(SimpleNamespace(execute=execute)))
        with tempfile.TemporaryDirectory() as folder, patch.object(exporter,'engine',engine),patch.object(exporter,'EXPORT_DIR',Path(folder)):
            path,count=exporter.build_export(date(2026,10,26))
            with path.open(encoding='utf-8-sig',newline='') as handle: output=list(csv.reader(handle))
        self.assertEqual(count,1)
        self.assertTrue(calls[0][0].lstrip().startswith('SELECT'))
        self.assertEqual(calls[0][1]['export_date'],date(2026,10,26))
        self.assertEqual(output[1][2],"'=formula")
        self.assertEqual(output[1][4],'123')
        self.assertTrue(output[1][7].startswith("'@product"))
        self.assertEqual(output[1][8],"' +formula")
