"""Synthetic spreadsheets, strict source boundaries and rollback-only imports."""
from contextlib import contextmanager
from datetime import date
from io import BytesIO
import json
import os
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZipFile

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
import treasury
import treasury_excel as excel
import treasury_strategy as strategy


def workbook(headers, rows, formula=False, second=None):
    stream = BytesIO()
    def xml_cells(values):
        out=[]
        for n, row in enumerate(values,1):
            cells=[]
            for c,value in enumerate(row,1):
                ref=''
                while c:
                    c,r=divmod(c-1,26); ref=chr(65+r)+ref
                cells.append(f'<c r="{ref}{n}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
            out.append(f'<row r="{n}">'+''.join(cells)+'</row>')
        return '<worksheet xmlns="'+excel.NS+'"><sheetData>'+''.join(out)+'</sheetData>'+('<f>1+1</f>' if formula else '')+'</worksheet>'
    with ZipFile(stream,'w') as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns="'+excel.NS+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="دیتا" sheetId="1" r:id="rId1"/>'+('<sheet name="دوم" sheetId="2" r:id="rId2"/>' if second else '')+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'+('<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>' if second else '')+'</Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',xml_cells([headers,*rows]))
        if second:
            z.writestr('xl/worksheets/sheet2.xml',xml_cells(second))
    return stream.getvalue()


CHECK_HEADERS=['شماره مرجع','طرف حساب','نوع چک','مبلغ','سررسید','وضعیت','احتمال وصول']
BALANCE_HEADERS=['کد حساب','نام حساب','نوع حساب','مانده','تاریخ']
INVOICE_HEADERS=['شماره فاکتور','تاریخ','شناسه کالا','تعداد','قیمت واحد','تخفیف ردیف','درصد تخفیف ردیف','تخفیف کل فاکتور','مالیات و عوارض فاکتور']

class ExcelParsingTests(unittest.TestCase):
    def test_explicit_check_unit_status_and_probability(self):
        result=excel.parse_report(workbook(CHECK_HEADERS,[['0001','شخص آزمایشی','دریافتنی','۱۲۳','۱۴۰۵/۰۷/۲۷','برگشتی','۸۰']]),'checks','TOMAN')
        row=result['normalized'][0]
        self.assertEqual(row['amount'],1230)
        self.assertEqual(row['reference'],'0001')
        self.assertEqual(row['status'],'bounced')
        self.assertEqual(row['collection_probability'],'0.8')
        self.assertEqual(row['due_date'],'2026-10-19')

    def test_balances_keep_negative_amount_and_asof_date(self):
        result=excel.parse_report(workbook(BALANCE_HEADERS,[['b01','بانک آزمایشی','بانک','-50','2026/10/19']]),'balances','IRR')
        self.assertEqual(result['normalized'][0]['balance'],-50)
        self.assertEqual(result['as_of'],'2026-10-19')

    def test_date_mixed_balances_and_duplicate_keys_are_rejected(self):
        for rows in ([['b1','بانک','بانک','2','1405/07/27'],['b2','بانک','بانک','3','1405/07/26']], [['b1','بانک','بانک','2','1405/07/27'],['b1','بانک','بانک','3','1405/07/27']]):
            with self.assertRaises(HTTPException):
                excel.parse_report(workbook(BALANCE_HEADERS,rows),'balances','TOMAN')

    def test_unknown_missing_unit_amount_or_status_are_rejected(self):
        base=['a','شخص آزمایشی','پرداختنی','100','1405/07/27','باز','100']
        for pos,value in ((2,'خرج شده'),(3,''),(3,'NaN'),(4,'1405/12/30'),(5,'نامشخص'),(6,'101')):
            r=base.copy();r[pos]=value
            with self.assertRaises(HTTPException):
                excel.parse_report(workbook(CHECK_HEADERS,[r]),'checks','IRR')
        with self.assertRaises(HTTPException):
            excel.parse_report(workbook(CHECK_HEADERS,[base]),'checks','unknown')

    def test_unknown_columns_can_be_archived_as_general_without_classification(self):
        result=excel.parse_report(workbook(['عنوان دلخواه','مقدار'],[['گزارش آزمایشی','2']]),'general','TOMAN')
        self.assertEqual(result['normalized'],[])
        self.assertEqual(result['row_count'],1)

    def test_sheet_selection_is_exact_and_other_sheet_not_mixed(self):
        content=workbook(['اول'],[['a']],second=[['دوم'],['b']])
        self.assertEqual(excel.inspect_file(content),['دیتا','دوم'])
        self.assertEqual(excel.table(content,'دوم')[1],[['b']])
        with self.assertRaises(HTTPException):
            excel.table(content,'غایب')

    def test_formula_duplicate_headers_and_invalid_workbook_rejected(self):
        for content in (b'not spreadsheet',workbook(['نام','نام'],[['a','b']]),workbook(['نام'],[['a']],formula=True)):
            with self.assertRaises(HTTPException):
                excel.table(content)

    def test_export_neutralizes_spreadsheet_formula_prefixes(self):
        for value in ('=1+2','+cmd','-cmd','@sum','  =2'):
            self.assertTrue(excel.csv_cell(value).startswith("'"))
        self.assertEqual(excel.csv_cell('ordinary'),'ordinary')

    def test_monthly_requires_all_costs_and_does_not_guess_missing_zero(self):
        headers=['ماه','نوع گزارش',*excel.AMOUNTS]
        result=excel.parse_report(workbook(headers,[['1405/06','عملکرد',*([0]*9)]]),'monthly','TOMAN')
        self.assertEqual(result['normalized'][0]['kind'],'actual')
        self.assertEqual(result['normalized'][0]['month'],'1405-06')
        with self.assertRaises(HTTPException):
            excel.parse_report(workbook(headers,[['1405/06','عملکرد','',*([0]*8)]]),'monthly','TOMAN')

    def test_invoice_grouping_discount_once_and_out_of_period_rejection(self):
        rows=[['f1','1405/07/27','p1','2','100','0','10','20','0'],['f1','1405/07/27','p1','1','0','0','0','20','0']]
        result=excel.parse_report(workbook(INVOICE_HEADERS,rows),'sales','TOMAN',from_date='1405/07/01',to_date='1405/07/30')
        invoice=result['normalized'][0]
        self.assertEqual(invoice['SumPrice'],'2000')
        self.assertEqual(invoice['SumDiscount'],200)
        self.assertEqual(len(invoice['Detail']),2)
        with self.assertRaises(HTTPException):
            excel.parse_report(workbook(INVOICE_HEADERS,rows),'sales','TOMAN',from_date='1405/06/01',to_date='1405/06/31')

    def test_header_only_invoice_can_explicitly_report_no_returns(self):
        result=excel.parse_report(workbook(INVOICE_HEADERS,[]),'sales_returns','IRR',from_date='1405/07/01',to_date='1405/07/30')
        self.assertEqual(result['normalized'],[])
        self.assertEqual(result['row_count'],0)

    def test_inventory_keeps_value_separate_from_profit(self):
        result=excel.parse_report(workbook(['شناسه کالا','تعداد','ارزش موجودی','تاریخ'],[['p1','5','150','1405/07/27']]),'inventory','TOMAN')
        self.assertEqual(result['normalized'][0]['value_irr'],1500)
        self.assertNotIn('profit',result)

class ExcelRoleTests(unittest.TestCase):
    def test_personnel_cannot_read_preview_or_commit_finance(self):
        app=FastAPI();app.include_router(excel.router)
        app.dependency_overrides[treasury.current_user]=lambda:{'id':9,'role':'visitor'}
        with TestClient(app) as client, patch.object(excel,'engine') as blocked:
            for path in ('reports','reports/1','template'):
                self.assertEqual(client.get('/treasury/excel/'+path).status_code,403)
            for path in ('sheets','preview','1/commit'):
                self.assertEqual(client.post('/treasury/excel/'+path,json={}).status_code,403)
            blocked.begin.assert_not_called()

@unittest.skipUnless(os.getenv('KIARAD_TEST_TREASURY_DB')=='1','Isolated PostgreSQL opt-in required')
class ExcelDatabaseTests(unittest.TestCase):
    def test_manual_report_preview_then_confirm_preserves_input_source_and_is_not_erp_write(self):
        data=excel.ManualReportInput(kind='checks',unit='TOMAN',title='گزارش دستی آزمایشی',source_note='اطلاعات ساختگی آزمون',headers=CHECK_HEADERS,
            rows=[['m01','شخص آزمایشی','دریافتنی','10','1405/07/28','باز','80']])
        result=excel.preview_manual_report(data,self.user)
        self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM financial_documents')).scalar(),0)
        batch=self.conn.execute(text('SELECT payload,source_note FROM treasury_excel_batches WHERE id=:id'),{'id':result['id']}).mappings().one()
        self.assertEqual(batch['payload']['input_mode'],'manual')
        self.assertIn('ورود دستی',batch['source_note'])
        excel.commit_report(result['id'],excel.ConfirmImport(confirm=True),self.user)
        self.assertEqual(self.conn.execute(text('SELECT amount FROM financial_documents')).scalar(),100)
    def setUp(self):
        import db
        self.conn=db.engine.connect();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        self.assertEqual(self.conn.exec_driver_sql('SHOW search_path').scalar(),'pg_temp')
        self.conn.execute(text('CREATE TEMP TABLE financial_documents(id SERIAL PRIMARY KEY,document_type TEXT,counterparty TEXT,amount NUMERIC,due_date DATE,status TEXT,reference_number TEXT,collection_probability NUMERIC,notes TEXT,created_at TIMESTAMPTZ)'))
        migration = Path(__file__).resolve().parents[1] / "migrations" / "0010_treasury_excel_storage.sql"
        raw = self.conn.connection.driver_connection
        with raw.cursor() as cursor:
            cursor.execute(migration.read_text(encoding="utf-8-sig"))
        strategy.ensure_schema(self.conn)
        @contextmanager
        def transaction():yield self.conn
        for p in (patch.object(excel,'engine',SimpleNamespace(begin=transaction)),):
            p.start();self.addCleanup(p.stop)
        self.user={'id':1,'role':'ceo'}

    def insert(self,kind,payload):
        return self.conn.execute(text("INSERT INTO treasury_excel_batches(kind,title,source_note,content_hash,payload,created_by) VALUES(:kind,'synthetic','synthetic source',:hash,CAST(:payload AS JSONB),1) RETURNING id"),{'kind':kind,'hash':str(self.conn.execute(text('SELECT count(*) FROM treasury_excel_batches')).scalar()),'payload':json.dumps(payload)}).scalar_one()

    def test_commit_checks_exactly_once_and_preserve_closed_status(self):
        payload=excel.parse_report(workbook(CHECK_HEADERS,[['c01','شخص آزمایشی','پرداختنی','100','1405/07/27','تسویه','100']]),'checks','IRR')
        ident=self.insert('checks',payload)
        excel.commit_report(ident,excel.ConfirmImport(confirm=True),self.user)
        self.assertEqual(self.conn.execute(text('SELECT status FROM financial_documents')).scalar(),'settled')
        with self.assertRaises(HTTPException):excel.commit_report(ident,excel.ConfirmImport(confirm=True),self.user)
        self.assertEqual(self.conn.execute(text('SELECT count(*) FROM financial_documents')).scalar(),1)

    def test_existing_check_blocks_entire_batch(self):
        self.conn.execute(text("INSERT INTO financial_documents(reference_number) VALUES('c1')"))
        payload=excel.parse_report(workbook(CHECK_HEADERS,[['c1','شخص آزمایشی','دریافتنی','100','1405/07/27','باز','100'],['c2','شخص آزمایشی','دریافتنی','100','1405/07/27','باز','100']]),'checks','IRR')
        ident=self.insert('checks',payload)
        with self.assertRaises(HTTPException):excel.commit_report(ident,excel.ConfirmImport(confirm=True),self.user)
        self.assertEqual(self.conn.execute(text('SELECT count(*) FROM financial_documents')).scalar(),1)

    def test_general_commit_is_archive_only(self):
        ident=self.insert('general',excel.parse_report(workbook(['نام'],[['آزمایش']]),'general','IRR'))
        excel.commit_report(ident,excel.ConfirmImport(confirm=True),self.user)
        self.assertEqual(self.conn.execute(text('SELECT count(*) FROM financial_documents')).scalar(),0)

    def test_pagination_and_export_retain_all_rows_without_financial_entries(self):
        ident=self.insert('general',excel.parse_report(workbook(['نام'],[[f'row-{i}'] for i in range(120)]),'general','IRR'))
        result=excel.report_detail(ident,offset=100,limit=100,_=self.user)
        self.assertEqual(result['rows'][0],['row-100'])
        self.assertEqual(len(result['rows']),20)
        exported=excel.export_report(ident,self.user)
        self.assertIn(b'row-119',exported.body)
        self.assertEqual(self.conn.execute(text('SELECT count(*) FROM financial_documents')).scalar(),0)

    def test_monthly_commit_creates_draft_only(self):
        payload=excel.parse_report(workbook(['ماه','نوع گزارش',*excel.AMOUNTS],[['1405/06','عملکرد',*([0]*9)]]),'monthly','IRR')
        payload['expected_revisions']={'actual:1405-06':0}
        ident=self.insert('monthly',payload)
        excel.commit_report(ident,excel.ConfirmImport(confirm=True),self.user)
        self.assertIsNone(self.conn.execute(text('SELECT approved_by FROM treasury_strategy_revisions')).scalar())
        self.assertEqual(self.conn.execute(text('SELECT count(*) FROM treasury_strategy_revisions')).scalar(),1)

    def test_balance_report_is_independent_and_uncommitted_not_usable(self):
        payload=excel.parse_report(workbook(BALANCE_HEADERS,[['b1','بانک آزمایشی','بانک','100','1405/07/27']]),'balances','IRR')
        ident=self.insert('balances',payload)
        self.assertIsNone(excel.excel_balance_summary(self.conn))
        excel.commit_report(ident,excel.ConfirmImport(confirm=True),self.user)
        self.assertEqual(excel.excel_balance_summary(self.conn)['balances'][0]['balance'],100)
