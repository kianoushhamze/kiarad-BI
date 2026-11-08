from copy import deepcopy
from datetime import datetime,timezone
from datetime import date
import os,unittest
from sqlalchemy import text
from holoo_operational_sync import apply_snapshot,documents,ProjectionError
from test_inventory_intelligence import payload,invoice


class OperationalPureTests(unittest.TestCase):
    def test_iranian_month_bounds_include_leap_day_and_new_year(self):
        from iran_time import iran_month_bounds
        self.assertEqual(iran_month_bounds(date(2026,10,20)),(date(2026,9,23),date(2026,10,23)))
        self.assertEqual(iran_month_bounds(date(2025,3,20)),(date(2025,2,19),date(2025,3,21)))
    def sample(self):
        p=payload();r=p['sources']['sales']['rows'][0]
        r.update(CustomerErpCode='c1',SanadCode=5,SumDiscount=900)
        r['Detail'][0]['PersentDiscount']=10
        p['sources']['sales_returns']['rows']=[{**invoice('r','2026-10-20',2,100), 'CustomerErpCode':'c1','SanadCode':5}]
        return p
    def test_real_erp_key_allows_repeated_sanad_and_subtracts_discount_once(self):
        d=documents(self.sample(),{'customers':{'c1':1},'products':{'p1':1}},1)
        self.assertEqual([x['total_amount'] for x in d],['8100','-200'])
        self.assertEqual(d[1]['items'][0]['quantity'],'-2')
    def test_duplicate_erp_or_incomplete_feed_cannot_be_applied(self):
        p=self.sample();p['sources']['sales']['rows']*=2
        with self.assertRaises(ProjectionError):documents(p,{'customers':{'c1':1},'products':{'p1':1}},1)
        p=self.sample();p['sources']['sales_returns']['complete']=False
        with self.assertRaises(ProjectionError):documents(p,{'customers':{'c1':1},'products':{'p1':1}},1)
    def test_no_name_fallback_for_customer_or_product(self):
        for maps in ({'customers':{},'products':{'p1':1}},{'customers':{'c1':1},'products':{}}):
            with self.assertRaises(ProjectionError):documents(self.sample(),maps,1)
    def test_tax_excluded_and_toman_converted(self):
        p=self.sample();p['sources']['sales']['rows'][0]['SumLevy']=100
        d=documents(p,{'customers':{'c1':1},'products':{'p1':1}},10)
        self.assertEqual(d[0]['total_amount'],'81000')
        self.assertEqual(d[0]['tax_irr'],'1000')


@unittest.skipUnless(os.getenv('KIARAD_TEST_TREASURY_DB')=='1','Temporary tables only')
class OperationalDatabaseTests(unittest.TestCase):
    def test_manual_product_and_customer_fields_survive_next_holoo_snapshot(self):
        from data_sources import save_manual_fields
        self.apply()
        save_manual_fields(self.c,'products',1,{'price':321,'stock':7},1)
        save_manual_fields(self.c,'customers',1,{'name':'نام دستی'},1)
        self.next();self.p['sources']['products']['rows'][0]['SellPrice']=999
        self.apply()
        self.assertEqual(tuple(self.c.execute(text('SELECT price,stock FROM products WHERE id=1')).one()),(321,7))
        self.assertEqual(self.c.execute(text('SELECT name FROM customers WHERE id=1')).scalar(),'نام دستی')
        self.assertEqual(self.p['sources']['products']['rows'][0]['SellPrice'],999)

    def test_restore_to_fresh_source_preserves_local_threshold_and_clears_only_source_fields(self):
        from data_sources import save_manual_fields,restore_holoo_fields
        from holoo_operational_sync import encode
        self.apply();save_manual_fields(self.c,'products',1,{'price':321,'min_stock':27},1)
        self.c.execute(text('CREATE TEMP TABLE holoo_financial_snapshots(id SERIAL,captured_at TIMESTAMPTZ,payload JSONB)'))
        self.c.execute(text('INSERT INTO holoo_financial_snapshots(captured_at,payload) VALUES(NOW(),CAST(:p AS JSONB))'),{'p':encode(self.p)})
        result=restore_holoo_fields(self.c,'products',1,1)
        self.assertEqual(result['status'],'restored')
        self.assertEqual(tuple(self.c.execute(text('SELECT price,min_stock FROM products WHERE id=1')).one()),(100,27))
        self.assertEqual(self.c.execute(text("SELECT field FROM data_field_overrides WHERE entity='products'")).scalar(),'min_stock')

    def test_stale_source_never_discards_manual_authority(self):
        from data_sources import save_manual_fields,restore_holoo_fields
        from holoo_operational_sync import encode
        from fastapi import HTTPException
        self.apply();save_manual_fields(self.c,'products',1,{'price':321},1)
        self.c.execute(text('CREATE TEMP TABLE holoo_financial_snapshots(id SERIAL,captured_at TIMESTAMPTZ,payload JSONB)'))
        self.c.execute(text("INSERT INTO holoo_financial_snapshots(captured_at,payload) VALUES(NOW()-INTERVAL '1 day',CAST(:p AS JSONB))"),{'p':encode(self.p)})
        with self.assertRaises(HTTPException):restore_holoo_fields(self.c,'products',1,1)
        self.assertEqual(self.c.execute(text('SELECT price FROM products')).scalar(),321)
    def setUp(self):
        import db
        self.c=db.engine.connect();self.addCleanup(self.c.close);self.addCleanup(self.c.rollback)
        self.assertEqual(self.c.exec_driver_sql('SHOW search_path').scalar(),'pg_temp')
        # A live refresh holds the same database advisory lock while it projects;
        # wait for it instead of failing this isolated group on a 5s lock timeout.
        self.c.execute(text("SET LOCAL lock_timeout='20s'"))
        for sql in (
            'CREATE TEMP TABLE customers(id SERIAL PRIMARY KEY,code TEXT UNIQUE,name TEXT,phone TEXT,city TEXT,credit_limit FLOAT,created_at TIMESTAMP)',
            'CREATE TEMP TABLE products(id SERIAL PRIMARY KEY,code TEXT UNIQUE,name TEXT,category TEXT,price FLOAT,stock FLOAT,min_stock FLOAT,is_active INT,updated_at TIMESTAMP)',
            'CREATE TEMP TABLE sales(id SERIAL PRIMARY KEY,customer_id INT,salesperson_id INT,date TIMESTAMP,total_amount FLOAT,holoo_sanad BIGINT)',
            'CREATE TEMP TABLE sale_items(id SERIAL PRIMARY KEY,sale_id INT REFERENCES sales(id),product_id INT,quantity FLOAT,price FLOAT)',
            'CREATE TEMP TABLE receivable_snapshots(id SERIAL PRIMARY KEY,source_file TEXT,import_hash TEXT UNIQUE,report_from_text TEXT,report_to_text TEXT,snapshot_date DATE,total_amount FLOAT,row_count INT,imported_by INT NOT NULL,created_at TIMESTAMP NOT NULL)',
            'CREATE TEMP TABLE receivable_balances(id SERIAL PRIMARY KEY,snapshot_id INT,counterparty TEXT,normalized_counterparty TEXT,balance FLOAT,share_percent FLOAT,customer_id INT,created_at TIMESTAMP NOT NULL)',
            "INSERT INTO customers(code,name,phone,city,credit_limit) VALUES('c1','قدیمی','خصوصی','کرمان',500)",
            "INSERT INTO products(code,name,category,min_stock) VALUES('001','قدیمی','دسته محلی',12)",
            "INSERT INTO sales(customer_id,salesperson_id,date,total_amount,holoo_sanad) VALUES(1,NULL,'2026-10-19',9000,5)",
        ):self.c.execute(text(sql))
        self.p=OperationalPureTests().sample()
        self.p['sources']['customers']={'ok':True,'complete':True,'rows':[{'ErpCode':'c1','Code':'c1','Name':'مشتری واقعی','Mandeh':500}]}
        self.p['sources']['products']['rows'][0]['SellPrice']=100
        self.snap={'id':1,'payload':self.p,'captured_at':datetime.now(timezone.utc)}
    def apply(self):return apply_snapshot(self.c,self.snap)
    def next(self):self.snap={**self.snap,'id':self.snap['id']+1,'payload':deepcopy(self.p)};self.p=self.snap['payload']
    def test_legacy_archived_and_signed_lines_reconcile(self):
        result=self.apply()
        self.assertEqual((result['sales'],result['returns'],result['archived_legacy']),(1,1,1))
        self.assertAlmostEqual(self.c.execute(text('SELECT SUM(total_amount) FROM sales')).scalar(),7900)
        self.assertAlmostEqual(self.c.execute(text('SELECT SUM(quantity*price) FROM sale_items')).scalar(),7900)
        self.assertEqual(self.c.execute(text('SELECT count(*) FROM sales WHERE salesperson_id IS NOT NULL')).scalar(),0)
        self.assertEqual(self.c.execute(text('SELECT count(*) FROM holoo_operational_audit')).scalar(),1)
    def test_same_snapshot_and_next_unchanged_snapshot_are_idempotent(self):
        self.apply();self.assertTrue(self.apply()['already_applied'])
        self.next();result=self.apply()
        self.assertEqual(result['unchanged'],2)
        self.assertEqual(self.c.execute(text('SELECT count(*) FROM sales')).scalar(),2)
        self.assertEqual(self.c.execute(text('SELECT count(*) FROM sale_items')).scalar(),2)
    def test_non_erp_fields_and_manual_sales_are_preserved(self):
        self.c.execute(text("INSERT INTO sales(customer_id,salesperson_id,date,total_amount) VALUES(1,9,'2026-10-19',11)"))
        self.apply()
        r=self.c.execute(text('SELECT phone,city,credit_limit FROM customers WHERE id=1')).one()
        self.assertEqual(tuple(r),('خصوصی','کرمان',500))
        self.assertEqual(self.c.execute(text('SELECT min_stock FROM products WHERE id=1')).scalar(),12)
        self.assertEqual(self.c.execute(text('SELECT total_amount FROM sales WHERE salesperson_id=9')).scalar(),11)
    def test_attribution_is_preserved_only_for_same_invoice_identity(self):
        self.c.execute(text('UPDATE sales SET salesperson_id=9'))
        self.apply();self.next();self.p['sources']['sales']['rows'][0]['SumDiscount']=0;self.p['sources']['sales']['rows'][0]['Detail'][0]['PersentDiscount']=0
        self.apply()
        r=self.c.execute(text('SELECT salesperson_id,total_amount FROM sales WHERE holoo_kind=2')).one()
        self.assertEqual(tuple(r),(9,9000))
    def test_ambiguous_attributed_legacy_is_not_guessed(self):
        self.c.execute(text('UPDATE sales SET salesperson_id=9'))
        other=deepcopy(self.p['sources']['sales']['rows'][0]);other['ErpCode']='another'
        self.p['sources']['sales']['rows'].append(other)
        with self.assertRaises(ProjectionError):self.apply()
    def test_source_removal_is_archived_and_reappearance_is_not_duplicated(self):
        self.apply();self.c.execute(text('UPDATE sales SET salesperson_id=9 WHERE holoo_kind=2'))
        self.next();original=self.p['sources']['sales']['rows'];self.p['sources']['sales']['rows']=[]
        result=self.apply();self.assertEqual(result['removed_from_mirror'],1)
        self.assertEqual(self.c.execute(text('SELECT count(*) FROM sales')).scalar(),1)
        self.next();self.p['sources']['sales']['rows']=original;self.apply()
        self.assertEqual(self.c.execute(text('SELECT count(*) FROM sales')).scalar(),2)
        self.assertEqual(self.c.execute(text('SELECT salesperson_id FROM sales WHERE holoo_kind=2')).scalar(),9)
    def test_stale_or_bad_currency_is_rejected(self):
        self.snap['captured_at']=datetime(2025,1,1,tzinfo=timezone.utc)
        with self.assertRaises(ProjectionError):self.apply()
    def test_receivable_system_import_is_not_human_approval(self):
        self.apply()
        row=self.c.execute(text('SELECT imported_by,total_amount FROM receivable_snapshots')).one()
        self.assertEqual(tuple(row),(None,500))
