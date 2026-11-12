import os,unittest
from contextlib import contextmanager,nullcontext
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from db import engine
from operations import current_user
import agent_routines as mod
@unittest.skipUnless(os.getenv('KIARAD_TEST_ROUTINES_DB')=='1','Opt-in disposable PostgreSQL')
class RoutineDBTests(unittest.TestCase):
 def setUp(self):
  self.c=engine.connect();self.tx=self.c.begin();self.addCleanup(self.c.close);self.addCleanup(self.tx.rollback);schema='routine_test_'+uuid4().hex;self.c.execute(text('CREATE SCHEMA '+schema));self.c.execute(text('SET LOCAL search_path TO '+schema));self.c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,full_name TEXT,role TEXT,salesperson_id INTEGER,password_version INTEGER DEFAULT 0,is_active INTEGER)'));self.c.execute(text("INSERT INTO users(id,role,is_active) VALUES(1,'ceo',1),(2,'visitor',1),(3,'ceo',1)"));mod.ensure(self.c)
  e=self.enterContext(patch.object(mod,'engine'));e.begin.side_effect=self.atomic;e.connect.side_effect=lambda:nullcontext(self.c)
  self.user={'id':1,'role':'ceo'};app=FastAPI();app.include_router(mod.router);app.dependency_overrides[current_user]=lambda:self.user;self.client=TestClient(app);self.addCleanup(self.client.close)
 @contextmanager
 def atomic(self):
  with self.c.begin_nested():yield self.c
 def create(self):
  r=self.client.post('/agent-routines',json={'name':'Daily discovery','kind':'lead_discovery','recipe':{}});self.assertEqual(r.status_code,201,r.text);return r.json()
 def approve(self,r):return self.client.post('/agent-routines/'+r['id']+'/approve',json={'confirm':True,'expected_digest':r['digest']})
 def test_definition_idempotent_and_immutable(self):
  r=self.create();self.assertEqual(self.create()['id'],r['id']);other=self.client.post('/agent-routines',json={'name':'Daily discovery','kind':'lead_discovery','recipe':{'city':'کرمان'}});self.assertEqual(other.status_code,409)
 def test_draft_does_not_run(self):
  r=self.create()
  with patch.object(mod,'execute_recipe') as f:self.assertEqual(self.client.post('/agent-routines/'+r['id']+'/run').status_code,409);f.assert_not_called()
 def test_digest_is_required(self):
  r=self.create();self.assertEqual(self.client.post('/agent-routines/'+r['id']+'/approve',json={'confirm':True,'expected_digest':'0'*64}).status_code,409)
 def test_owner_binding_and_staff_rejection(self):
  r=self.create();self.user={'id':3,'role':'ceo'};self.assertEqual(self.client.post('/agent-routines/'+r['id']+'/pause').status_code,404);self.user={'id':2,'role':'visitor'};self.assertEqual(self.client.get('/agent-routines').status_code,403)
 def test_approved_run_has_durable_cycle_and_repeat_cooldown(self):
  r=self.create();self.approve(r)
  with patch.object(mod,'execute_recipe',return_value={'new_candidates':1}) as f:
   result=self.client.post('/agent-routines/'+r['id']+'/run');self.assertEqual(result.json()['state'],'completed',result.text);self.assertEqual(self.client.post('/agent-routines/'+r['id']+'/run').status_code,429);self.assertEqual(f.call_count,1)
  cycles=self.client.get('/agent-routines/'+r['id']+'/cycles').json()['items'];self.assertEqual(len(cycles),1);self.assertEqual(cycles[0]['result']['new_candidates'],1)
 def test_pause_prevents_run(self):
  r=self.create();self.approve(r);self.client.post('/agent-routines/'+r['id']+'/pause');self.assertEqual(self.client.post('/agent-routines/'+r['id']+'/run').status_code,409)
 def test_expired_owner_role_never_runs_recipe(self):
  r=self.create();self.approve(r);self.c.execute(text("UPDATE users SET role='visitor' WHERE id=1"))
  with patch.object(mod,'execute_recipe') as f:result=self.client.post('/agent-routines/'+r['id']+'/run');self.assertEqual(result.json()['state'],'failed');f.assert_not_called()
 def test_concurrent_lease_is_respected(self):
  r=self.create();self.approve(r);self.c.execute(text("UPDATE agent_routines SET lease_until=NOW()+INTERVAL '1 hour' WHERE id=:id"),{'id':r['id']});self.assertEqual(self.client.post('/agent-routines/'+r['id']+'/run').status_code,409)
 def test_unknown_non_read_cycle_requires_explicit_reconciliation(self):
  r=self.client.post('/agent-routines',json={'name':'Reviewed strategy','kind':'professional_plan','recipe':{'objective':'Prepare weekly strategy','domains':['sales']}}).json();self.approve(r)
  with patch.object(mod,'execute_recipe',side_effect=TimeoutError) as f:
   result=self.client.post('/agent-routines/'+r['id']+'/run');self.assertEqual(result.json()['state'],'review_required');self.assertEqual(self.approve(r).status_code,409);self.assertEqual(self.client.post('/agent-routines/'+r['id']+'/run').status_code,409);self.assertEqual(f.call_count,1)
  result=self.client.post('/agent-routines/'+r['id']+'/reconcile',json={'reviewed':True,'note':'Confirmed no external duplicate action; old result reviewed manually.'});self.assertEqual(result.json()['state'],'paused');self.assertFalse(result.json()['old_cycle_retried'])
 def test_due_time_is_not_bypassed_by_scheduler(self):
  r=self.create();self.approve(r)
  with patch.object(mod,'execute_recipe') as f:self.assertEqual(mod.run(r['id'],self.user)['state'],'not_due');f.assert_not_called()
