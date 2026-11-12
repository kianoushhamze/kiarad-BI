import os,unittest
from contextlib import contextmanager,nullcontext
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from db import engine
from operations import current_user
import prospect_pipeline as mod
@unittest.skipUnless(os.getenv('KIARAD_TEST_PROSPECT_PIPELINE_DB')=='1','Opt-in disposable PostgreSQL')
class ProspectTests(unittest.TestCase):
 def setUp(self):
  self.c=engine.connect();self.tx=self.c.begin();self.addCleanup(self.c.close);self.addCleanup(self.tx.rollback);schema='prospect_test_'+uuid4().hex;self.c.execute(text('CREATE SCHEMA '+schema));self.c.execute(text('SET LOCAL search_path TO '+schema));self.c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY)'));self.c.execute(text('INSERT INTO users VALUES(1),(2)'))
  for source in mod.SOURCES:self.c.execute(text('CREATE TABLE '+source+'(id SERIAL PRIMARY KEY,name TEXT,city TEXT,address TEXT,phone TEXT,type TEXT,latitude DOUBLE PRECISION,longitude DOUBLE PRECISION,visit_radius_m INTEGER)'))
  mod.ensure(self.c);e=self.enterContext(patch.object(mod,'engine'));e.begin.side_effect=self.atomic;e.connect.side_effect=lambda:nullcontext(self.c)
  self.user={'id':1,'role':'ceo'};app=FastAPI();app.include_router(mod.router);app.dependency_overrides[current_user]=lambda:self.user;self.client=TestClient(app);self.addCleanup(self.client.close)
  self.item={'source_id':'node/1','source_url':'https://www.openstreetmap.org/node/1','name':'پایگاه آزمایش','city':'کرمان','address':'نشانی ساختگی آزمایشی','phone':'03400000000','category':'pharmacy','latitude':30.29,'longitude':57.06}
  self.report={'items':[self.item],'source':'OpenStreetMap','source_url':'https://overpass-api.de/api/interpreter','license_url':'https://www.openstreetmap.org/copyright','observed_at':'2026-11-12T00:00:00+00:00'}
  self.provider=self.enterContext(patch.object(mod,'discover',side_effect=lambda:self.report))
 @contextmanager
 def atomic(self):
  with self.c.begin_nested():yield self.c
 def discover(self,key=None):
  r=self.client.post('/prospects/discover',json={'submission_key':key or str(uuid4())});self.assertEqual(r.status_code,200,r.text);return r.json()
 def candidate(self):return self.client.get('/prospects').json()['items'][0]
 def review(self,c,**kw):
  fields={k:self.item[k] for k in ['name','city','address','phone','category','latitude','longitude']};body={'expected_revision':c['revision'],'decision':'approve','note':'Reviewed against business address and location','verified_fields':fields,'coordinates_confirmed':True,**kw};return self.client.post('/prospects/'+c['id']+'/review',json=body)
 def test_discovery_only_creates_candidates_and_replays(self):
  key=str(uuid4());r=self.discover(key);self.assertEqual(r['summary']['new_candidates'],1);self.discover(key);self.assertEqual(self.provider.call_count,1);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM kerman_bases_manual')).scalar(),0)
 def test_repeated_source_records_do_not_duplicate(self):
  self.report['items']=[self.item,self.item];self.discover();self.discover();self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM prospect_candidates')).scalar(),1)
 def test_review_requires_confirmed_coordinates(self):
  self.discover();c=self.candidate();r=self.client.post('/prospects/'+c['id']+'/review',json={'expected_revision':1,'decision':'approve','note':'Verified but missing coordinate confirmation'});self.assertEqual(r.status_code,422)
 def test_review_creates_one_base(self):
  self.discover();c=self.candidate();r=self.review(c);self.assertEqual(r.status_code,200,r.text);self.review(c);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM kerman_bases_manual')).scalar(),1)
 def test_source_change_is_revisioned_and_does_not_overwrite(self):
  self.discover();c=self.candidate();self.review(c);self.item['address']='نشانی جدید در منبع عمومی';self.discover();changed=self.candidate();self.assertEqual(changed['revision'],2);self.assertEqual(changed['review_status'],'changed_after_review');self.assertEqual(self.review(c).status_code,409);self.assertEqual(self.review(changed).status_code,409);self.assertEqual(self.review(changed,apply_base_update=True).status_code,200);self.assertEqual(self.c.execute(text('SELECT address FROM kerman_bases_manual')).scalar(),self.item['address'])
 def test_source_failure_is_not_successful_empty_discovery(self):
  with patch.object(mod,'discover',side_effect=TimeoutError):r=self.client.post('/prospects/discover',json={'submission_key':str(uuid4())});self.assertEqual(r.status_code,503)
  self.assertEqual(self.c.execute(text('SELECT state FROM prospect_runs')).scalar(),'failed')
 def test_staff_cannot_discover_or_review(self):
  self.user={'id':2,'role':'visitor'};self.assertEqual(self.client.get('/prospects').status_code,403);self.assertEqual(self.client.post('/prospects/discover',json={'submission_key':str(uuid4())}).status_code,403)
