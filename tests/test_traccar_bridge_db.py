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
import traccar_bridge as m
import live_tracking as tracking
@unittest.skipUnless(os.getenv('KIARAD_TEST_TRACCAR_DB')=='1','Opt-in disposable PostgreSQL')
class TraccarTests(unittest.TestCase):
 def setUp(self):
  self.c=engine.connect();self.tx=self.c.begin();self.addCleanup(self.c.close);self.addCleanup(self.tx.rollback);schema='traccar_'+uuid4().hex;self.c.execute(text('CREATE SCHEMA '+schema));self.c.execute(text('SET LOCAL search_path TO '+schema));self.c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,full_name TEXT,role TEXT,salesperson_id INTEGER,is_active INTEGER,password_version INTEGER)'));self.c.execute(text("INSERT INTO users VALUES(1,'chief','Chief','ceo',NULL,1,0),(2,'worker','Worker','visitor',2,1,0),(3,'other','Other','visitor',3,1,0)"));self.c.execute(text('CREATE TABLE role_permissions(role TEXT,module TEXT,can_read BOOLEAN,can_write BOOLEAN,can_delete BOOLEAN)'));m.ensure(self.c)
  for module in [m,tracking]:
   e=self.enterContext(patch.object(module,'engine'));e.begin.side_effect=self.atomic;e.connect.side_effect=lambda:nullcontext(self.c)
  self.enterContext(patch.dict(os.environ,{'KIARAD_TRACCAR_ENABLED':'1','KIARAD_TRACCAR_FORWARD_TOKEN':'synthetic-forward-token-0123456789012345','KIARAD_TRACCAR_CLIENT_URL':'https://gps.ci.invalid'}));self.user={'id':1,'role':'ceo'};app=FastAPI();app.include_router(m.router);app.include_router(tracking.router);app.dependency_overrides[current_user]=lambda:self.user;self.client=TestClient(app);self.addCleanup(self.client.close)
 @contextmanager
 def atomic(self):
  with self.c.begin_nested():yield self.c
 def bind(self):
  self.user={'id':1,'role':'ceo'};r=self.client.post('/tracking/traccar/devices',json={'user_id':2,'platform':'ios','label':'Synthetic phone'});self.assertEqual(r.status_code,201,r.text);return r.json()
 def start(self,b):
  self.user={'id':2,'role':'visitor','salesperson_id':2};r=self.client.post('/tracking/traccar/shift/start',json={'device_id':b['id'],'consent_version':'work-shift-location-v1'});self.assertEqual(r.status_code,201,r.text);return r.json()
 def point(self,b,at=None):return {'device':{'id':7,'uniqueId':b['identifier'],'name':'ignored'},'position':{'id':91,'deviceId':7,'fixTime':(at or datetime.now(timezone.utc)).isoformat(),'latitude':30.29,'longitude':57.06,'valid':True,'accuracy':5,'speed':10,'attributes':{'batteryLevel':70,'mock':False}}}
 def send(self,p,token=None):return self.client.post('/tracking/traccar/positions',json=p,headers={'X-Kiarad-Traccar-Token':token or os.environ['KIARAD_TRACCAR_FORWARD_TOKEN']})
 def count(self):return self.c.execute(text('SELECT COUNT(*) FROM tracking_points')).scalar()
 def test_device_inventory_requires_map_read_permission(self):
  b=self.bind();self.user={'id':2,'role':'visitor','salesperson_id':2}
  self.c.execute(text("INSERT INTO role_permissions(role,module,can_read,can_write,can_delete) VALUES('visitor','map',FALSE,TRUE,FALSE)"))
  r=self.client.get('/tracking/traccar/devices')
  self.assertEqual(r.status_code,403)
 def test_device_binding_requires_manager_map_write_permission(self):
  self.user={'id':1,'role':'sales_manager'}
  self.c.execute(text("INSERT INTO role_permissions(role,module,can_read,can_write,can_delete) VALUES('sales_manager','map',TRUE,FALSE,FALSE)"))
  r=self.client.post('/tracking/traccar/devices',json={'user_id':2,'platform':'android','label':'Synthetic phone'})
  self.assertEqual(r.status_code,403)
  self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM traccar_devices')).scalar(),0)
 def test_untrusted_and_disabled_forwarding_cannot_write(self):
  b=self.bind();self.start(b);self.assertEqual(self.send(self.point(b),'bad-token').status_code,401)
  with patch.dict(os.environ,{'KIARAD_TRACCAR_ENABLED':'0'}):self.assertEqual(self.send(self.point(b)).status_code,503)
  self.assertEqual(self.count(),0)
 def test_in_shift_point_reaches_existing_live_dashboard(self):
  b=self.bind();self.start(b);r=self.send(self.point(b));self.assertTrue(r.json()['accepted'],r.text);row=self.client.get('/tracking/live').json()['items'][0];self.assertTrue(row['is_live']);self.assertEqual(row['source'],'traccar');self.assertEqual(row['latitude'],30.29);row=self.c.execute(text('SELECT speed_mps,battery_level FROM tracking_points')).mappings().first();self.assertAlmostEqual(row['speed_mps'],5.14444444444);self.assertEqual(row['battery_level'],.7)
 def test_outside_shift_never_persisted(self):
  b=self.bind();r=self.send(self.point(b));self.assertEqual(r.json()['ignored'],'outside_consented_shift');self.assertEqual(self.count(),0)
 def test_duplicate_and_reset_traccar_position_id_are_idempotent(self):
  b=self.bind();self.start(b);p=self.point(b);self.send(p);p['position']['id']=1;r=self.send(p);self.assertTrue(r.json()['duplicate']);self.assertEqual(self.count(),1)
 def test_ended_shift_rejects_new_but_accepts_its_own_backfill(self):
  b=self.bind();s=self.start(b);now=datetime.now(timezone.utc);self.c.execute(text("UPDATE tracking_sessions SET started_at=:begin,ended_at=:end WHERE id=:id"),{'begin':now-timedelta(hours=1),'end':now-timedelta(minutes=10),'id':s['session_id']});r=self.send(self.point(b,now));self.assertFalse(r.json()['accepted']);self.assertTrue(self.send(self.point(b,now-timedelta(minutes=20))).json()['accepted']);self.assertEqual(self.count(),1)
 def test_backfill_does_not_replace_newer_live_fix(self):
  b=self.bind();s=self.start(b);self.c.execute(text("UPDATE tracking_sessions SET started_at=NOW()-INTERVAL '2 hours' WHERE id=:id"),{'id':s['session_id']});recent=self.point(b);self.send(recent);old=self.point(b,datetime.now(timezone.utc)-timedelta(hours=1));old['position']['latitude']=30.30;self.send(old);live=self.client.get('/tracking/live').json()['items'][0];self.assertEqual(live['latitude'],recent['position']['latitude']);self.assertTrue(live['is_live'])
 def test_revocation_ends_shift_and_blocks_buffered_points(self):
  b=self.bind();s=self.start(b);self.user={'id':1,'role':'ceo'};self.client.post('/tracking/traccar/devices/'+b['id']+'/revoke');self.assertFalse(self.send(self.point(b)).json()['accepted']);self.assertEqual(self.count(),0);self.assertIsNotNone(self.c.execute(text('SELECT ended_at FROM tracking_sessions WHERE id=:id'),{'id':s['session_id']}).scalar())
 def test_employee_cannot_bind_revoke_or_see_other_device(self):
  b=self.bind();self.user={'id':3,'role':'visitor','salesperson_id':3};self.assertEqual(self.client.get('/tracking/traccar/devices').json()['items'],[]);self.assertEqual(self.client.post('/tracking/traccar/devices/'+b['id']+'/revoke').status_code,403);self.assertEqual(self.client.post('/tracking/traccar/devices',json={'user_id':3,'platform':'android','label':'Another phone'}).status_code,403);self.assertEqual(self.client.post('/tracking/traccar/shift/start',json={'device_id':b['id'],'consent_version':'work-shift-location-v1'}).status_code,404)
 def test_only_one_active_binding_and_immutable_identifier(self):
  b=self.bind();r=self.client.post('/tracking/traccar/devices',json={'user_id':2,'platform':'android','label':'Second phone'});self.assertEqual(r.status_code,409);self.client.post('/tracking/traccar/devices/'+b['id']+'/revoke');new=self.bind();self.assertNotEqual(new['identifier'],b['identifier'])
 def test_one_active_shift_across_native_and_traccar(self):
  b=self.bind();self.user={'id':2,'role':'visitor','salesperson_id':2};r=self.client.post('/tracking/sessions',json={'device_id':'native-device-id','platform':'android','consent_version':'work-shift-location-v1'});self.assertEqual(r.status_code,201);r=self.client.post('/tracking/traccar/shift/start',json={'device_id':b['id'],'consent_version':'work-shift-location-v1'});self.assertEqual(r.status_code,409)
 def test_no_accuracy_is_conservative_not_precise(self):
  b=self.bind();self.start(b);p=self.point(b);p['position']['accuracy']=0;self.send(p);live=self.client.get('/tracking/live').json()['items'][0];self.assertEqual(live['accuracy_m'],50000);self.assertFalse(live['is_live'])
 def test_invalid_future_unmapped_and_mismatched_fixes_not_saved(self):
  b=self.bind();self.start(b)
  for change in ['invalid','future','unknown','mismatch']:
   p=self.point(b)
   if change=='invalid':p['position']['valid']=False
   if change=='future':p['position']['fixTime']=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
   if change=='unknown':p['device']['uniqueId']='not-a-bound-phone'
   if change=='mismatch':p['position']['deviceId']=99
   self.assertFalse(self.send(p).json()['accepted'])
  self.assertEqual(self.count(),0)
 def test_inactive_person_cannot_receive_locations(self):
  b=self.bind();self.start(b);self.c.execute(text('UPDATE users SET is_active=0 WHERE id=2'));self.assertFalse(self.send(self.point(b)).json()['accepted']);self.assertEqual(self.count(),0)
 def test_naive_timestamp_and_oversized_payload_rejected(self):
  b=self.bind();self.start(b);p=self.point(b);p['position']['fixTime']='2026-11-12T10:00:00';self.assertEqual(self.send(p).status_code,422);p=self.point(b);p['position']['attributes']['large']='x'*33000;self.assertEqual(self.send(p).status_code,413);self.assertEqual(self.count(),0)
 def test_retry_of_start_returns_same_session(self):
  b=self.bind();one=self.start(b);two=self.start(b);self.assertEqual(one['session_id'],two['session_id']);self.assertTrue(two['reused'])
 def test_backfill_burst_limit_is_retryable_not_silently_acknowledged(self):
  b=self.bind();s=self.start(b);self.c.execute(text("INSERT INTO tracking_points(session_id,event_id,user_id,recorded_at,latitude,longitude,accuracy_m) SELECT :session,md5('rate:'||g)::uuid,2,NOW(),30,57,5 FROM generate_series(1,1200) g"),{'session':s['session_id']});r=self.send(self.point(b));self.assertEqual(r.status_code,429);self.assertEqual(r.headers['retry-after'],'60');self.assertEqual(self.count(),1200)
 def test_mock_flag_from_forwarder_is_never_shown_as_live(self):
  b=self.bind();self.start(b);p=self.point(b);p['position']['attributes']['mock']='true';self.send(p);live=self.client.get('/tracking/live').json()['items'][0];self.assertFalse(live['is_live']);self.assertEqual(live['state'],'possible_mock')

 def test_revoked_map_permission_ends_shift_and_does_not_auto_resume(self):
  b=self.bind();s=self.start(b);self.c.execute(text("INSERT INTO role_permissions VALUES('visitor','__configured__',false,false,false)"));r=self.send(self.point(b));self.assertEqual(r.json()['ignored'],'tracking_permission_revoked');self.assertEqual(self.count(),0);self.assertIsNotNone(self.c.execute(text('SELECT ended_at FROM tracking_sessions WHERE id=:id'),{'id':s['session_id']}).scalar());self.c.execute(text('DELETE FROM role_permissions'));self.assertEqual(self.send(self.point(b)).json()['ignored'],'outside_consented_shift')
 def test_role_change_without_map_grant_blocks_receipt(self):
  b=self.bind();self.start(b);self.c.execute(text("UPDATE users SET role='finance' WHERE id=2"));self.assertEqual(self.send(self.point(b)).json()['ignored'],'tracking_permission_revoked');self.assertEqual(self.count(),0)
 def test_account_reassignment_or_password_revocation_ends_old_shift(self):
  b=self.bind();s=self.start(b);self.c.execute(text('UPDATE users SET password_version=1 WHERE id=2'));self.assertEqual(self.send(self.point(b)).json()['ignored'],'account_session_changed');self.assertEqual(self.count(),0);self.assertIsNotNone(self.c.execute(text('SELECT ended_at FROM tracking_sessions WHERE id=:id'),{'id':s['session_id']}).scalar())
 def test_role_editor_closes_shift_immediately_without_waiting_for_a_point(self):
  import operations
  b=self.bind();s=self.start(b);fake=self.enterContext(patch.object(operations,'engine'));fake.begin.side_effect=self.atomic
  operations.set_role_permissions('visitor',{'permissions':[]},{'id':1,'role':'ceo'})
  self.assertIsNotNone(self.c.execute(text('SELECT ended_at FROM tracking_sessions WHERE id=:id'),{'id':s['session_id']}).scalar())
  operations.set_role_permissions('visitor',{'modules':['map']},{'id':1,'role':'ceo'})
  self.assertEqual(self.send(self.point(b)).json()['ignored'],'outside_consented_shift')
 def test_fresh_consent_after_account_change_creates_new_bound_shift(self):
  b=self.bind();old=self.start(b);self.c.execute(text('UPDATE users SET password_version=1 WHERE id=2'));self.user['password_version']=1;r=self.client.post('/tracking/traccar/shift/start',json={'device_id':b['id'],'consent_version':'work-shift-location-v1'});self.assertEqual(r.status_code,201,r.text);self.assertNotEqual(r.json()['session_id'],old['session_id']);self.assertTrue(self.send(self.point(b)).json()['accepted'])
