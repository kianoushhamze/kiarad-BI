"""Persistent mission and shift ingestion on an isolated, rolled-back PostgreSQL schema."""
import os,unittest
from contextlib import nullcontext,contextmanager
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from db import engine
import agent_center as agent
import live_tracking as tracking
import operations as ops
from operations import current_user
@unittest.skipUnless(os.getenv('KIARAD_TEST_AGENT_DB')=='1','Opt-in disposable PostgreSQL')
class AgentTrackingDBTests(unittest.TestCase):
 def setUp(self):
  self.conn=engine.connect();self.tx=self.conn.begin();self.addCleanup(self.conn.close);self.addCleanup(self.tx.rollback)
  self.conn.execute(text('CREATE SCHEMA agent_test_'+(schema:=uuid4().hex)))
  self.conn.execute(text('SET LOCAL search_path TO agent_test_'+schema))
  self.conn.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,full_name TEXT,role TEXT,salesperson_id INTEGER,is_active INTEGER,password_version INTEGER DEFAULT 0)'))
  self.conn.execute(text("INSERT INTO users(id,username,full_name,role,salesperson_id,is_active) VALUES(1,'chief','CEO','ceo',NULL,1),(2,'worker','Visitor','visitor',2,1),(3,'other','Other','visitor',3,1),(4,'chief2','Other CEO','ceo',NULL,1)"))
  self.conn.execute(text('CREATE TABLE role_permissions(role TEXT,module TEXT,can_read BOOLEAN,can_write BOOLEAN,can_delete BOOLEAN)'))
  self.conn.execute(text("INSERT INTO role_permissions VALUES ('visitor','map',TRUE,TRUE,FALSE),('salesperson','map',TRUE,TRUE,FALSE),('finance','map',FALSE,FALSE,FALSE)"))
  agent.ensure(self.conn);tracking.ensure(self.conn)
  for module in [agent,tracking,ops]:
   fake=self.enterContext(patch.object(module,'engine'));fake.begin.side_effect=self.atomic;fake.connect.side_effect=lambda:nullcontext(self.conn)
  self.user={'id':1,'role':'ceo'};app=FastAPI();app.include_router(agent.router);app.include_router(tracking.router);app.dependency_overrides[current_user]=lambda:self.user
  self.client=TestClient(app);self.addCleanup(self.client.close)
 @contextmanager
 def atomic(self):
  with self.conn.begin_nested():yield self.conn
 def create(self,op='notify_user',policy=None):
  r=self.client.post('/agent-center/missions',json={'title':'Test mission','objective':'Testing receipts','domains':['coordination'],'policy':policy or {},'steps':[{'key':'first','title':'Notify employee','operation':op,'payload':{'user_id':2,'message':'Test approved notification'}}]})
  self.assertEqual(r.status_code,201,r.text);return self.client.get('/agent-center/missions/'+r.json()['id']).json()
 def approve(self,m):return self.client.post('/agent-center/missions/'+m['id']+'/approve',json={'confirm':True,'expected_digest':m['plan_digest']})
 def test_plan_does_not_execute_until_approved(self):
  m=self.create();self.assertEqual(self.client.post('/agent-center/missions/'+m['id']+'/run').status_code,409)
  self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM agent_alerts')).scalar(),0)
 def test_modified_digest_cannot_be_approved(self):
  m=self.create();r=self.client.post('/agent-center/missions/'+m['id']+'/approve',json={'confirm':True,'expected_digest':'0'*64});self.assertEqual(r.status_code,409)
 def test_mission_owner_and_ceo_role_enforced(self):
  m=self.create();self.user={'id':4,'role':'ceo'};self.assertEqual(self.client.get('/agent-center/missions/'+m['id']).status_code,404)
  self.user={'id':2,'role':'visitor'};self.assertEqual(self.client.get('/agent-center/missions').status_code,403)
 def test_explicit_notification_review_and_receipt_idempotency(self):
  m=self.create();self.assertEqual(self.approve(m).status_code,200)
  r=self.client.post('/agent-center/missions/'+m['id']+'/run');self.assertNotEqual(r.json().get('state'),'applied')
  r=self.client.post('/agent-center/missions/'+m['id']+'/steps/first/approve',json={'confirm':True,'expected_digest':m['plan_digest']});self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['state'],'applied')
  self.client.post('/agent-center/missions/'+m['id']+'/run');self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM agent_alerts')).scalar(),1)
 def test_pause_blocks_next_step(self):
  m=self.create();self.approve(m);self.client.post('/agent-center/missions/'+m['id']+'/pause');self.assertEqual(self.client.post('/agent-center/missions/'+m['id']+'/run').status_code,409)
 def test_lessons_need_owned_feedback_and_can_be_revoked(self):
  m=self.create();r=self.client.post('/agent-center/missions/'+m['id']+'/feedback',json={'rating':4,'note':'Observed outcome'});fid=r.json()['feedback_id']
  self.user={'id':4,'role':'ceo'};body={'domain':'sales','text':'Approved lesson about recorded sales','source_feedback_id':fid};self.assertEqual(self.client.post('/agent-center/lessons',json=body).status_code,404)
  self.user={'id':1,'role':'ceo'};r=self.client.post('/agent-center/lessons',json=body);self.assertEqual(r.status_code,200,r.text);lid=r.json()['lesson_id'];self.assertEqual(self.client.post(f'/agent-center/lessons/{lid}/revoke').status_code,200);self.assertFalse(self.client.get('/agent-center/lessons').json()['items'][0]['active'])
 def start(self):
  self.user={'id':2,'role':'visitor','salesperson_id':2};r=self.client.post('/tracking/sessions',json={'device_id':'test-device-0001','platform':'android','consent_version':'work-shift-location-v1'});self.assertEqual(r.status_code,201,r.text);return r.json()['session_id']
 def sample(self,at=None):return {'event_id':str(uuid4()),'recorded_at':(at or datetime.now(timezone.utc)).isoformat(),'latitude':30.29,'longitude':57.06,'accuracy_m':5}
 def upload(self,sid,samples):return self.client.post('/tracking/locations',json={'session_id':sid,'device_id':'test-device-0001','samples':samples})
 def test_native_tracking_requires_explicit_map_write_grant(self):
  sid=self.start();self.conn.execute(text("UPDATE role_permissions SET can_write=FALSE WHERE role='visitor' AND module='map'"))
  self.assertEqual(self.upload(sid,[self.sample()]).status_code,403)
  self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM tracking_points')).scalar(),0)
  self.assertEqual(self.client.post('/tracking/heartbeat',json={'session_id':sid,'device_id':'test-device-0001','status':'tracking'}).status_code,403)
  self.assertEqual(self.client.post('/tracking/sessions/stop',json={'session_id':sid,'device_id':'test-device-0001'}).status_code,200)
 def test_native_tracking_live_and_history_require_map_read_grant(self):
  sid=self.start();self.user={'id':1,'role':'ceo'}
  self.assertEqual(self.client.get('/tracking/live').status_code,200)
  self.conn.execute(text("INSERT INTO tracking_points(session_id,event_id,user_id,recorded_at,latitude,longitude,accuracy_m) VALUES(:s,:e,2,NOW(),30,57,5)"),{'s':sid,'e':str(uuid4())})
  self.conn.execute(text("UPDATE role_permissions SET can_read=FALSE WHERE role='visitor' AND module='map'"))
  self.user={'id':2,'role':'visitor','salesperson_id':2}
  self.assertEqual(self.client.get('/tracking/live').status_code,403)
  self.assertEqual(self.client.get('/tracking/history?user_id=2').status_code,403)
 def test_duplicate_upload_has_one_stored_point(self):
  sid=self.start();sample=self.sample();self.assertEqual(self.upload(sid,[sample]).status_code,200);self.assertEqual(self.upload(sid,[sample]).status_code,200);self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM tracking_points')).scalar(),1)
 def test_wrong_account_cannot_upload_or_read_history(self):
  sid=self.start();self.user={'id':3,'role':'visitor','salesperson_id':3};self.assertEqual(self.upload(sid,[self.sample()]).status_code,404);self.assertEqual(self.client.get('/tracking/history?user_id=2').status_code,403)
 def test_future_and_out_of_shift_rejected_atomically(self):
  sid=self.start();self.assertEqual(self.upload(sid,[self.sample(),self.sample(datetime.now(timezone.utc)+timedelta(hours=1))]).status_code,422)
  self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM tracking_points')).scalar(),0)
 def test_old_backfill_cannot_replace_latest_fix(self):
  sid=self.start();self.conn.execute(text("UPDATE tracking_sessions SET started_at=NOW()-INTERVAL '2 hours' WHERE id=:id"),{'id':sid})
  now=self.sample();old=self.sample(datetime.now(timezone.utc)-timedelta(hours=1));self.upload(sid,[now]);self.upload(sid,[old]);live=self.client.get('/tracking/live').json()['items'][0];self.assertTrue(live['is_live']);self.assertEqual(live['recorded_at'],now['recorded_at'])
 def test_stopped_session_rejects_new_points(self):
  sid=self.start();self.client.post('/tracking/sessions/stop',json={'session_id':sid,'device_id':'test-device-0001'});self.assertEqual(self.upload(sid,[self.sample(datetime.now(timezone.utc)+timedelta(seconds=1))]).status_code,422)
 def test_one_active_device_per_employee(self):
  sid=self.start();r=self.client.post('/tracking/sessions',json={'device_id':'test-device-0002','platform':'ios','consent_version':'work-shift-location-v1'});self.assertEqual(r.status_code,409)
  r=self.client.post('/tracking/sessions',json={'device_id':'test-device-0001','platform':'android','consent_version':'work-shift-location-v1'});self.assertEqual(r.json()['session_id'],sid);self.assertTrue(r.json()['reused'])

 def test_business_receipt_replay_does_not_repeat_operation(self):
  m=self.create('create_task',{'mode':'bounded_auto'});self.approve(m)
  with patch('assistant_operations.prepare',return_value={'proposal_id':str(uuid4())}) as prepare,patch('assistant_operations.confirm_proposal',return_value={'status':'applied','receipt':{'id':91}}) as confirm:
   r=self.client.post('/agent-center/missions/'+m['id']+'/run');self.assertEqual(r.json()['state'],'applied',r.text)
   self.client.post('/agent-center/missions/'+m['id']+'/run');self.assertEqual(prepare.call_count,1);self.assertEqual(confirm.call_count,1)
 def test_unknown_business_outcome_stops_retries(self):
  m=self.create('create_task',{'mode':'bounded_auto'});self.approve(m)
  with patch('assistant_operations.prepare',return_value={'proposal_id':str(uuid4())}),patch('assistant_operations.confirm_proposal',side_effect=RuntimeError('unknown outcome')) as confirm:
   r=self.client.post('/agent-center/missions/'+m['id']+'/run');self.assertEqual(r.json()['state'],'review_required',r.text)
   self.client.post('/agent-center/missions/'+m['id']+'/run');self.assertEqual(confirm.call_count,1)
