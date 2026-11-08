"""Synthetic workbooks and in-memory SQL mocks; no database or external requests."""
import asyncio
from contextlib import contextmanager
from datetime import date
from io import BytesIO
import unittest
from unittest.mock import Mock, patch
from xml.sax.saxutils import escape
from zipfile import ZipFile

from fastapi import HTTPException, UploadFile

import treasury


HEADERS = ["طرف حساب", "نوع چک", "مبلغ ریال", "تاریخ سررسید", "شماره چک"]
ROW = ["طرف آزمایشی", "پرداختنی", "125000", "۱۴۰۵/۰۷/۲۷", "1234567890123456"]


def workbook(rows):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="checks" sheetId="1" r:id="r1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        xml_rows = []
        for number, row in enumerate(rows, 1):
            cells = [f'<c r="{chr(65 + column)}{number}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>' for column, value in enumerate(row)]
            xml_rows.append(f'<row r="{number}">{"".join(cells)}</row>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + '</sheetData></worksheet>')
    return output.getvalue()


class MemoryResult:
    def __init__(self, values=(), scalar=0):
        self.values, self.single = values, scalar

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return self.values

    def scalar(self):
        return self.single


class MemoryEngine:
    def __init__(self, references=(), documents=()):
        self.references = list(references)
        self.inserts = []
        self.documents = documents
        self.transactions = 0

    @contextmanager
    def begin(self):
        self.transactions += 1
        yield self

    connect = begin

    def execute(self, sql, params=None):
        sql = str(sql)
        if "SELECT reference_number" in sql:
            return MemoryResult(self.references)
        if "INSERT INTO financial_documents" in sql:
            self.inserts.append(params)
            self.references.append(params["ref_num"])
        if "SUM(current_balance)" in sql:
            return MemoryResult(scalar=100)
        if "FROM financial_documents" in sql:
            return MemoryResult(self.documents)
        return MemoryResult()


class TreasuryImportSafetyTests(unittest.TestCase):
    def parse(self, row=None, headers=None):
        return treasury.parse_checks_workbook(workbook([headers or HEADERS, row or ROW]))

    def assert_invalid(self, row=None, headers=None):
        with self.assertRaises(HTTPException) as caught:
            self.parse(row, headers)
        self.assertEqual(caught.exception.status_code, 422)

    def test_explicit_direction_amount_reference_and_jalali_date(self):
        item = self.parse()[0]
        self.assertEqual(item["doc_type"], "payable_check")
        self.assertEqual(item["amount"], 125000)
        self.assertEqual(item["ref_num"], "1234567890123456")
        self.assertEqual(item["due_date"], date(2026, 10, 19))

    def test_toman_conversion_is_exact(self):
        item = self.parse([*ROW[:2], "12.3", *ROW[3:]], [*HEADERS[:2], "مبلغ تومان", *HEADERS[3:]])[0]
        self.assertEqual(item["amount"], 123)

    def test_gregorian_is_explicit_and_validated(self):
        self.assertEqual(self.parse([*ROW[:3], "2026-10-19", ROW[4]])[0]["due_date"], date(2026, 10, 19))

    def test_missing_or_invalid_direction_never_defaults_to_receivable(self):
        for value in ("", "نامشخص", "چک"):
            with self.subTest(value=value):
                self.assert_invalid([ROW[0], value, *ROW[2:]])

    def test_ambiguous_unit_is_rejected(self):
        self.assert_invalid(headers=[*HEADERS[:2], "مبلغ", *HEADERS[3:]])

    def test_two_units_are_rejected(self):
        self.assert_invalid([*ROW, "1"], [*HEADERS, "مبلغ تومان"])

    def test_duplicate_headers_rejected(self):
        self.assert_invalid([*ROW, "other"], [*HEADERS, "طرف حساب"])

    def test_invalid_missing_serial_and_impossible_dates_never_guessed(self):
        for value in ("", "1405/12/30", "1405/13/01", "2026-02-30", "46000", "روز بعد"):
            with self.subTest(value=value):
                self.assert_invalid([*ROW[:3], value, ROW[4]])

    def test_missing_reference_is_rejected(self):
        self.assert_invalid([*ROW[:4], ""])

    def test_unsafe_amounts_rejected(self):
        for value in ("-1", "0", "NaN", "Infinity", "=1+2", "1.1", "1000000000000001"):
            with self.subTest(value=value):
                self.assert_invalid([*ROW[:2], value, *ROW[3:]])

    def test_reference_zeros_and_digits_are_preserved(self):
        item = self.parse([*ROW[:4], "۰۰۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵۶"])[0]
        self.assertEqual(item["ref_num"], "001234567890123456")

    def test_duplicate_reference_within_file_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            treasury.parse_checks_workbook(workbook([HEADERS, ROW, ROW]))
        self.assertEqual(caught.exception.status_code, 422)

    def test_bad_final_row_prevents_any_database_transaction(self):
        blocked = Mock()
        blocked.begin.side_effect = AssertionError("Database must not be used")
        content = workbook([HEADERS, ROW, [*ROW[:3], "invalid", "another"]])
        with patch.object(treasury, "engine", blocked), self.assertRaises(HTTPException):
            asyncio.run(treasury.import_checks_excel(UploadFile(file=BytesIO(content)), {}))
        blocked.begin.assert_not_called()

    def test_existing_reference_prevents_all_inserts(self):
        engine = MemoryEngine([ROW[4]])
        with patch.object(treasury, "engine", engine), self.assertRaises(HTTPException) as caught:
            asyncio.run(treasury.import_checks_excel(UploadFile(file=BytesIO(workbook([HEADERS, ROW]))), {}))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(engine.inserts, [])

    def test_reimport_is_rejected(self):
        engine = MemoryEngine()
        content = workbook([HEADERS, ROW])
        with patch.object(treasury, "engine", engine):
            result = asyncio.run(treasury.import_checks_excel(UploadFile(file=BytesIO(content)), {}))
            self.assertEqual(result["inserted_count"], 1)
            with self.assertRaises(HTTPException):
                asyncio.run(treasury.import_checks_excel(UploadFile(file=BytesIO(content)), {}))
        self.assertEqual(len(engine.inserts), 1)

    def test_non_workbook_is_rejected_without_database(self):
        with patch.object(treasury, "engine", Mock()) as blocked, self.assertRaises(HTTPException):
            asyncio.run(treasury.import_checks_excel(UploadFile(file=BytesIO(b"not a workbook")), {}))
        blocked.begin.assert_not_called()

    def test_unsupported_holoo_check_route_makes_no_http_call(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No external traffic")) as request:
            result = treasury.sync_checks_from_holoo({})
        request.assert_not_called()
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["connected"])
        self.assertEqual(result["inserted_count"], 0)

    def test_balance_sheet_keeps_overdue_and_bounced_payable_obligations(self):
        docs = [{"id": n, "document_type": kind, "amount": amount, "counterparty": "synthetic", "due_date": date(2026, 10, 18), "status": state, "reference_number": str(n), "notes": "synthetic"} for n, kind, amount, state in ((1, "receivable_check", 50, "overdue"), (2, "payable_check", 200, "bounced"), (3, "payable", 30, "overdue"), (4, "receivable_check", 9000, "bounced"), (5, "payable_check", 9999, "settled"))]
        with patch.object(treasury, "engine", MemoryEngine(documents=docs)), patch.object(treasury, "iran_today", return_value=date(2026, 10, 19)):
            result = treasury.get_checks_balance_sheet({})
        self.assertEqual(result["summary"]["receivable_open_total"], 50)
        self.assertEqual(result["summary"]["payable_open_total"], 230)
        self.assertEqual(result["summary"]["payable_bounced_total"], 200)
        self.assertEqual(result["summary"]["net_position"], -80)
        self.assertEqual(result["aging_buckets"]["overdue"]["payable"], 230)


if __name__ == "__main__":
    unittest.main()
