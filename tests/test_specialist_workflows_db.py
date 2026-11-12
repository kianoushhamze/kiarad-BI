import os,unittest,hashlib
from contextlib import contextmanager,nullcontext
from datetime import date,timedelta,datetime,timezone
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from db import engine
from operations import current_user
import specialist_workflows as m
@unittest.skipUnless(os.getenv('KIARAD_TEST_SPECIALISTS_DB')=='1','Opt-in disposable PostgreSQL')
class SpecialistsTests(unittest.TestCase):
 def setUp(self):
  self.c=engine.connect();self.tx=self.c.begin();self.addCleanup(self.c.close);self.addCleanup(self.tx.rollback);self.c.execute(text('CREATE SCHEMA specialist_'+(key:=uuid4().hex)));self.c.execute(text('SET LOCAL search_path TO specialist_'+key));self.c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY,full_name TEXT,role TEXT,is_active INTEGER)'));self.c.execute(text("INSERT INTO users VALUES(1,'Chief','ceo',1),(2,'Worker','visitor',1),(3,'Other chief','ceo',1)"));self.c.execute(text('CREATE TABLE customers(id INTEGER PRIMARY KEY)'));self.c.execute(text('CREATE TABLE salespersons(id INTEGER PRIMARY KEY,name TEXT)'));self.c.execute(text("INSERT INTO salespersons VALUES(1,'Synthetic')"));self.c.execute(text('CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT,code TEXT,price NUMERIC,stock NUMERIC)'));self.c.execute(text("INSERT INTO products VALUES(1,'Product','P',1000,20)"));self.c.execute(text('CREATE TABLE sales(id INTEGER PRIMARY KEY,salesperson_id INTEGER,date TIMESTAMP)'));self.c.execute(text('CREATE TABLE sale_items(id INTEGER PRIMARY KEY,sale_id INTEGER,product_id INTEGER,quantity NUMERIC,price NUMERIC)'));self.c.execute(text('CREATE TABLE agent_sources(id UUID PRIMARY KEY,owner_id INTEGER,kind TEXT,title TEXT,content TEXT,source_date TEXT)'));m.ensure(self.c)
  e=self.enterContext(patch.object(m,'engine'));e.begin.side_effect=self.atomic;e.connect.side_effect=lambda:nullcontext(self.c);self.user={'id':1,'role':'ceo'};app=FastAPI();app.include_router(m.router);app.dependency_overrides[current_user]=lambda:self.user;self.client=TestClient(app);self.addCleanup(self.client.close)
 @contextmanager
 def atomic(self):
  with self.c.begin_nested():yield self.c
 def test_annual_query_is_person_product_specific(self):
  today=m.iran_today();self.c.execute(text('INSERT INTO sales VALUES(1,1,:day),(2,99,:day)'),{'day':today-timedelta(days=10)});self.c.execute(text('INSERT INTO sale_items VALUES(1,1,1,10,800),(2,2,1,999,800),(3,1,99,999,800)'));r=self.client.post('/specialists/target-scenarios',json={'salesperson_id':1,'product_id':1,'start_date':str(today+timedelta(days=1)),'end_date':str(today+timedelta(days=30))});self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['recorded_positive_units'],'10');self.assertFalse(r.json()['automatic_financial_write'])
 def test_other_manager_inflation_source_rejected(self):
  sid=uuid4();self.c.execute(text("INSERT INTO agent_sources VALUES(:id,3,'market_report','Private','not shared',:day)"),{'id':str(sid),'day':str(m.iran_today())});r=self.client.post('/specialists/target-scenarios',json={'salesperson_id':1,'product_id':1,'start_date':str(m.iran_today()),'end_date':str(m.iran_today()),'inflation_rate':'.4','inflation_source_id':str(sid)});self.assertEqual(r.status_code,422)
 def review(self):
  sid=uuid4();self.c.execute(text("INSERT INTO agent_sources VALUES(:id,1,'contract','Contract','The supplier must deliver by the confirmed due date.',NULL)"),{'id':str(sid)})
  with patch.object(m,'llm_json',return_value={'summary':'Reviewed clauses','obligations':[{'summary':'Track delivery','clause_quote':'The supplier must deliver','deadline_suggestion':'unconfirmed','risk_note':'Review actual date'}],'missing_data':[]}):r=self.client.post('/specialists/contract-review',json={'source_id':str(sid)})
  self.assertEqual(r.status_code,200,r.text);return r.json()
 def test_obligation_creates_one_real_task_and_no_notice(self):
  r=self.review();payload={'obligation_index':0,'assigned_to':2,'due_date':(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),'confirm':True,'expected_source_digest':r['source_digest']};a=self.client.post('/specialists/contract-review/'+r['id']+'/task',json=payload);self.assertEqual(a.status_code,200,a.text);b=self.client.post('/specialists/contract-review/'+r['id']+'/task',json=payload);self.assertEqual(a.json()['task_id'],b.json()['task_id']);self.assertTrue(b.json()['replayed']);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM tasks')).scalar(),1);self.assertFalse(a.json()['legal_notice_sent'])
 def test_other_ceo_cannot_create_contract_task(self):
  r=self.review();self.user={'id':3,'role':'ceo'};a=self.client.post('/specialists/contract-review/'+r['id']+'/task',json={'obligation_index':0,'assigned_to':2,'due_date':datetime.now(timezone.utc).isoformat(),'confirm':True,'expected_source_digest':r['source_digest']});self.assertEqual(a.status_code,404)
 def test_target_monitor_respects_person_dates_and_missing_rows(self):
  import specialist_monitor as monitor
  self.c.execute(text('ALTER TABLE users ADD COLUMN salesperson_id INTEGER'));self.c.execute(text('UPDATE users SET salesperson_id=1 WHERE id=2'));self.c.execute(text('ALTER TABLE sales ADD COLUMN total_amount NUMERIC'));self.c.execute(text('CREATE TABLE targets(id INTEGER PRIMARY KEY,title TEXT,target_amount NUMERIC,start_date DATE,end_date DATE,product_focus TEXT,target_type TEXT,salesperson_id INTEGER,status TEXT)'))
  today=m.iran_today();self.c.execute(text("INSERT INTO targets VALUES(1,'Actual period',3000,:begin,:end,'','ماهانه',1,'active'),(2,'Unknown product',3000,:begin,:end,'not-a-product','ماهانه',1,'active')"),{'begin':today-timedelta(days=10),'end':today+timedelta(days=20)})
  self.c.execute(text('INSERT INTO sales(id,salesperson_id,date,total_amount) VALUES(1,1,:day,100),(2,2,:day,99999),(3,1,:old,88888),(4,1,:today,77777)'),{'day':today-timedelta(days=1),'old':today-timedelta(days=50),'today':today})
  e=self.enterContext(patch.object(monitor,'engine'));e.connect.side_effect=lambda:nullcontext(self.c)
  with patch('visit_coverage.coverage',return_value={'items':[]}):result=monitor.signals([2],self.user)['items'][0]
  actual={t['id']:t for t in result['targets']};self.assertEqual(actual[1]['actual_irr'],'100');self.assertTrue(actual[1]['behind_pace']);self.assertFalse(actual[2]['assessable']);self.assertEqual(result['coverage']['assigned_bases'],0);self.assertFalse(actual[1]['disciplinary_finding'])
