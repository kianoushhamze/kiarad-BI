"""Source authority and intake regressions; writes are confined to pg_temp."""
from contextlib import contextmanager,nullcontext
from datetime import datetime,timezone,timedelta
from io import BytesIO
from types import SimpleNamespace
import os,json,unittest
from unittest.mock import patch,MagicMock
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
import data_entry as entry
import integrations
import treasury_excel as financial


class EntryPureTests(unittest.TestCase):
    def test_numbers_units_dates_codes_and_unknown_values(self):
        result=entry.normalize_rows('products',[{'code':'۰۰۱','name':'آزمایشی','price':'۲۵','stock':'۰','price2':'۲۰'}],'TOMAN')[0]
        self.assertEqual(result,{'code':'001','name':'آزمایشی','price':'250','stock':'0','price2':'200'})
        bad=[{'code':12,'name':'آزمایشی','price':'2','stock':'1'},
             {'code':'a','name':'آزمایشی','price':'NaN','stock':'1'},
             {'code':'a','name':'آزمایشی','price':'2','stock':True},
             {'code':'a','name':'آزمایشی','price':'2','stock':'','ErpCode':'x'}]
        for row in bad:
            with self.subTest(row=row),self.assertRaises(HTTPException):entry.normalize_rows('products',[row],'IRR')
        with self.assertRaises(HTTPException):entry.normalize_rows('products',[result,result],'IRR')
        target=entry.normalize_rows('targets',[{'title':'هدف آزمایشی','target_amount':'1','start_date':'۱۴۰۵/۰۷/۰۱','end_date':'۱۴۰۵/۰۷/۳۰'}],'IRR')[0]
        self.assertEqual(target['start_date'],'2026-09-23')
        with self.assertRaises(HTTPException):entry.normalize_rows('targets',[{**target,'end_date':'2025-01-01'}],'IRR')

    def test_role_and_entity_guards(self):
        for entity,role in [('products','visitor'),('customers','salesperson'),('targets','finance'),('unknown','ceo')]:
            with self.subTest(entity=entity,role=role),self.assertRaises(HTTPException):entry.allowed(entity,{'role':role})

    def test_digikala_never_trusts_token_or_html_or_stale_receipt(self):
        client=MagicMock();response=client.get_profile.return_value;response.status_code=200
        with patch('digikala_api.DigikalaClient',return_value=client):
            response.json.return_value={'status':'ok','data':{'id':1}}
            self.assertEqual(integrations.probe_digikala()['status'],'verified')
            response.json.return_value={'status':'error','data':{'id':1},'error':'denied'}
            self.assertEqual(integrations.probe_digikala()['status'],'unverified_response')
            response.status_code=403
            self.assertEqual(integrations.probe_digikala()['status'],'authentication_failed')
        client.update_price.assert_not_called();client.update_stock.assert_not_called()
        with patch('digikala_api.DigikalaClient',side_effect=FileNotFoundError):self.assertEqual(integrations.probe_digikala()['status'],'credentials_missing')
        for seconds,expected in [(0,True),(601,False),(-120,False)]:
            result=integrations.channel_status('digikala',None,None,0,{'status':'verified','checked_at':datetime.now(timezone.utc)-timedelta(seconds=seconds)})
            self.assertEqual(result['connected'],expected);self.assertFalse(result['price_push_enabled']);self.assertFalse(result['sync_enabled'])

    def test_manual_finance_same_validation_as_excel_and_no_silent_zero(self):
        headers=financial.MANUAL_HEADERS['balances']
        result=financial.parse_report_rows(headers,[['b1','بانک آزمایشی','بانک','-5','۱۴۰۵/۰۷/۲۸']],'balances','TOMAN')
        self.assertEqual(result['normalized'][0]['balance'],-50)
        with self.assertRaises(HTTPException):financial.parse_report_rows(headers,[['b1','بانک آزمایشی','بانک','','۱۴۰۵/۰۷/۲۸']],'balances','IRR')
        with self.assertRaises(HTTPException):financial.parse_report_rows(headers,[['b1','بانک آزمایشی','بانک','1']],'balances','IRR')
        with self.assertRaises(HTTPException):financial.preview_manual_report(financial.ManualReportInput(kind='general',unit='IRR',title='آزمایش',source_note='گزارش آزمایشی',headers=['عنوان','مقدار'],rows=[['=1+1','x']]),{'id':1,'role':'ceo'})


@unittest.skipUnless(os.getenv('KIARAD_TEST_TREASURY_DB')=='1','Temporary database opt-in required')
class EntryDatabaseTests(unittest.TestCase):
    def setUp(self):
        import db
        self.c=db.engine.connect();self.addCleanup(self.c.close);transaction=self.c.begin();self.addCleanup(transaction.rollback)
        self.assertEqual(self.c.exec_driver_sql('SHOW search_path').scalar(),'pg_temp')
        statements=[
         'CREATE TEMP TABLE products(id SERIAL PRIMARY KEY,code TEXT UNIQUE,name TEXT,price NUMERIC,price2 NUMERIC,stock NUMERIC,min_stock NUMERIC,is_active INT,category TEXT,updated_at TIMESTAMPTZ)',
         'CREATE TEMP TABLE customers(id SERIAL PRIMARY KEY,code TEXT UNIQUE,name TEXT,phone TEXT,city TEXT,credit_limit NUMERIC,created_at TIMESTAMPTZ)',
         'CREATE TEMP TABLE salespersons(id INT PRIMARY KEY,name TEXT)',
         'CREATE TEMP TABLE sales(id INT PRIMARY KEY,holoo_kind INT,holoo_erp_code TEXT,salesperson_id INT,date DATE DEFAULT CURRENT_DATE)',
         "INSERT INTO sales(id,holoo_kind,holoo_erp_code,salesperson_id) VALUES(10,2,'erp-10',NULL),(11,4,'erp-11',NULL),(12,2,'erp-owned',2)",
         'CREATE TEMP TABLE targets(id SERIAL PRIMARY KEY,title TEXT,salesperson_id INT,target_amount NUMERIC,bonus_reward NUMERIC,start_date DATE,end_date DATE,status TEXT,period_type TEXT,target_type TEXT,product_focus TEXT,month INT,year INT,created_at TIMESTAMPTZ)',
         'CREATE TEMP TABLE inventory_batches(id SERIAL PRIMARY KEY,product_id INT,batch_code TEXT,expiry_date DATE,quantity NUMERIC,note TEXT,created_by INT,UNIQUE(product_id,batch_code))',
         "INSERT INTO salespersons VALUES(1,'پرسنل آزمایشی')",
         "INSERT INTO products(code,name,price,stock) VALUES('001','کالای قبلی',100,20)",
        ]
        for statement in statements:self.c.execute(text(statement))
        entry.ensure_entry_storage(self.c)
        @contextmanager
        def begin():
            with self.c.begin_nested():yield self.c
        fake=SimpleNamespace(begin=begin,connect=lambda:nullcontext(self.c))
        patcher=patch.object(entry,'engine',fake);patcher.start();self.addCleanup(patcher.stop)
        app=FastAPI();app.include_router(entry.router)
        self.user={'id':1,'role':'ceo'};app.dependency_overrides[entry.current_user]=lambda:self.user
        self.client=TestClient(app);self.addCleanup(self.client.close)

    def preview(self,rows=None,entity='products'):
        return self.client.post(f'/data-entry/{entity}/manual/preview',json={'unit':'IRR','rows':rows or [{'code':'001','name':'کالای تغییرکرده','price':'90','stock':'5'}]})

    def commit(self,ident,entity='products'):
        return self.client.post(f'/data-entry/{entity}/{ident}/commit',json={'confirm':True})

    def test_preview_no_operational_writes_then_atomic_idempotent_commit(self):
        response=self.preview();self.assertEqual(response.status_code,200,response.text);ident=response.json()['id']
        self.assertEqual(self.c.execute(text('SELECT price FROM products')).scalar(),100)
        result=self.commit(ident);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.c.execute(text('SELECT price FROM products')).scalar(),90)
        self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM data_field_overrides')).scalar(),3)
        self.assertTrue(self.commit(ident).json()['already_committed'])
        self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM data_change_audit')).scalar(),1)

    def test_stale_preview_blocks_all_rows_and_can_be_refreshed(self):
        ident=self.preview().json()['id']
        self.c.execute(text('UPDATE products SET stock=9'))
        self.assertEqual(self.commit(ident).status_code,409)
        self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM data_field_overrides')).scalar(),0)
        self.assertEqual(self.preview().json()['id'],ident)
        self.assertEqual(self.commit(ident).status_code,200)

    def test_other_actor_and_staff_denied_without_changes(self):
        ident=self.preview().json()['id'];self.user={'id':2,'role':'ceo'}
        self.assertEqual(self.commit(ident).status_code,404)
        self.user={'id':3,'role':'visitor'}
        self.assertEqual(self.preview().status_code,403)
        self.assertEqual(self.commit(ident).status_code,403)
        self.assertEqual(self.c.execute(text('SELECT price FROM products')).scalar(),100)

    def test_new_customer_target_and_batch_keep_distinct_domains(self):
        cases=[('customers',{'code':'m1','name':'مشتری آزمایشی','credit_limit':'200','city':'کرمان'}),
               ('targets',{'title':'هدف آزمایشی','salesperson_id':'1','target_amount':'300','start_date':'1405/07/01','end_date':'1405/07/30'}),
               ('batches',{'product_code':'001','batch_code':'batch-1','quantity':'2','expiry_date':'1406/01/01'})]
        for entity,row in cases:
            response=self.preview([row],entity);self.assertEqual(response.status_code,200,response.text)
            result=self.commit(response.json()['id'],entity);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.c.execute(text('SELECT stock FROM products')).scalar(),20)
        self.assertEqual(self.c.execute(text('SELECT salesperson_id FROM targets')).scalar(),1)

    def test_excel_preview_preserves_text_codes_and_does_not_commit(self):
        import openpyxl
        book=openpyxl.Workbook();sheet=book.active
        sheet.append(['کد کالا','نام کالا','قیمت ۱','موجودی']);sheet.append(['001','آزمایشی',50,3])
        stream=BytesIO();book.save(stream)
        response=self.client.post('/data-entry/products/excel/preview',data={'unit':'TOMAN'},files={'file':('test.xlsx',stream.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['rows'][0]['values']['code'],'001')
        self.assertEqual(response.json()['rows'][0]['values']['price'],'500')
        self.assertEqual(self.c.execute(text('SELECT price FROM products')).scalar(),100)

    def test_blank_optional_fields_preserve_target_reward_status_and_batch_note(self):
        target={'title':'هدف آزمایشی','salesperson_id':'1','target_amount':'300','start_date':'1405/07/01','end_date':'1405/07/30','bonus_reward':'50','product_focus':'گروه آزمایشی'}
        batch={'product_code':'001','batch_code':'b1','quantity':'2','expiry_date':'1406/01/01','note':'یادداشت قبلی'}
        for entity,row in [('targets',target),('batches',batch)]:
            self.assertEqual(self.commit(self.preview([row],entity).json()['id'],entity).status_code,200)
        self.c.execute(text("UPDATE targets SET status='closed'"))
        target.pop('bonus_reward');target.pop('product_focus');target['target_amount']='400'
        batch.pop('note');batch['quantity']='3'
        for entity,row in [('targets',target),('batches',batch)]:
            self.assertEqual(self.commit(self.preview([row],entity).json()['id'],entity).status_code,200)
        saved=self.c.execute(text('SELECT bonus_reward,status,product_focus FROM targets')).mappings().one()
        self.assertEqual((saved['bonus_reward'],saved['status'],saved['product_focus']),(50,'closed','گروه آزمایشی'))
        self.assertEqual(self.c.execute(text('SELECT note FROM inventory_batches')).scalar(),'یادداشت قبلی')

    def test_assignment_preview_and_commit_preserve_identity_and_are_idempotent(self):
        rows=[{'holoo_kind':'2','holoo_erp_code':'erp-10','salesperson_id':'1'}]
        response=self.preview(rows,'sales-assignments');self.assertEqual(response.status_code,200,response.text)
        self.assertIsNone(self.c.execute(text('SELECT salesperson_id FROM sales WHERE id=10')).scalar())
        ident=response.json()['id']
        result=self.commit(ident,'sales-assignments');self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.c.execute(text('SELECT salesperson_id FROM sales WHERE id=10')).scalar(),1)
        self.assertTrue(self.commit(ident,'sales-assignments').json()['already_committed'])

    def test_assignment_rejects_missing_staff_document_duplicates_and_existing_other_owner(self):
        base={'holoo_kind':'2','holoo_erp_code':'erp-10','salesperson_id':'1'}
        for rows in ([{**base,'salesperson_id':'999'}],[{**base,'holoo_erp_code':'unknown'}],
                     [{**base,'holoo_erp_code':'erp-owned'}],[base,base],[{**base,'holoo_kind':'1'}]):
            self.assertIn(self.preview(rows,'sales-assignments').status_code,(409,422))
        self.assertIsNone(self.c.execute(text('SELECT salesperson_id FROM sales WHERE id=10')).scalar())

    def test_assignment_stale_preview_blocks_atomic_commit(self):
        rows=[{'holoo_kind':'2','holoo_erp_code':'erp-10','salesperson_id':'1'},
              {'holoo_kind':'4','holoo_erp_code':'erp-11','salesperson_id':'1'}]
        ident=self.preview(rows,'sales-assignments').json()['id']
        self.c.execute(text('UPDATE sales SET salesperson_id=2 WHERE id=11'))
        self.assertEqual(self.commit(ident,'sales-assignments').status_code,409)
        self.assertIsNone(self.c.execute(text('SELECT salesperson_id FROM sales WHERE id=10')).scalar())

    def test_assignment_excel_and_staff_access(self):
        import openpyxl
        book=openpyxl.Workbook();sheet=book.active
        sheet.append([f[1] for f in entry.SPECS['sales-assignments']['fields']])
        sheet.append(['2','erp-10','1'])
        stream=BytesIO();book.save(stream)
        result=self.client.post('/data-entry/sales-assignments/excel/preview',data={'unit':'IRR'},files={'file':('test.xlsx',stream.getvalue())})
        self.assertEqual(result.status_code,200,result.text)
        self.user={'id':9,'role':'salesperson','salesperson_id':1}
        self.assertEqual(self.commit(result.json()['id'],'sales-assignments').status_code,403)

    def test_assignment_template_splits_into_uploadable_pages_and_has_staff_reference(self):
        import openpyxl
        self.c.execute(text("INSERT INTO sales(id,holoo_kind,holoo_erp_code) SELECT n,2,'doc-'||n FROM generate_series(100,600) n"))
        result=self.client.get('/data-entry/sales-assignments/template')
        self.assertEqual(result.status_code,200,result.text if result.status_code!=200 else '')
        book=openpyxl.load_workbook(BytesIO(result.content))
        self.assertEqual(book.sheetnames,['اسناد 1','اسناد 2','راهنمای پرسنل'])
        self.assertEqual(book.worksheets[0].cell(2,1).value,'2')
        self.assertIsNone(book.worksheets[0].cell(2,3).value)
        self.assertEqual(sum(1 for row in book.worksheets[0].iter_rows(min_row=2,values_only=True) if row[1]),500)
        self.assertEqual(sum(1 for row in book.worksheets[1].iter_rows(min_row=2,values_only=True) if row[1]),3)
        book.close()
