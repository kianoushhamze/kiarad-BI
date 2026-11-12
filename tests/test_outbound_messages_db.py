import os,unittest
from contextlib import contextmanager,nullcontext
from datetime import datetime,timezone
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from db import engine
from operations import current_user
import outbound_messages as out
@unittest.skipUnless(os.getenv('KIARAD_TEST_OUTBOUND_DB')=='1','Opt-in disposable PostgreSQL')
class OutboundTests(unittest.TestCase):
 def setUp(self):
  self.c=engine.connect();self.tx=self.c.begin();self.addCleanup(self.c.close);self.addCleanup(self.tx.rollback);schema='outbound_test_'+uuid4().hex;self.c.execute(text('CREATE SCHEMA '+schema));self.c.execute(text('SET LOCAL search_path TO '+schema))
  self.c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY,role TEXT,is_active INTEGER)'));self.c.execute(text("INSERT INTO users VALUES(1,'ceo',1),(2,'visitor',1),(3,'ceo',1)"));self.c.execute(text('CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT)'));self.c.execute(text("INSERT INTO customers VALUES(1,'Synthetic')"));out.ensure(self.c)
  e=self.enterContext(patch.object(out,'engine'));e.begin.side_effect=self.atomic;e.connect.side_effect=lambda:nullcontext(self.c)
  self.user={'id':1,'role':'ceo'};app=FastAPI();app.include_router(out.router);app.dependency_overrides[current_user]=lambda:self.user;self.client=TestClient(app);self.addCleanup(self.client.close)
  self.enterContext(patch.object(out,'connected',return_value=True));self.enterContext(patch.object(out,'enabled',return_value=True));self.now=datetime.now(timezone.utc).replace(hour=10)
 @contextmanager
 def atomic(self):
  with self.c.begin_nested():yield self.c
 def contact(self,scope='transactional'):
  r=self.client.post('/outbound/contacts',json={'customer_id':1,'channel':'sms','destination':'09123456789','consent_scope':scope,'evidence':'Synthetic explicit contact authorization'});self.assertEqual(r.status_code,201,r.text);return r.json()['id']
 def preview(self,contact=None,purpose='service',key=None):
  body={'submission_key':key or str(uuid4()),'contact_id':contact or self.contact(),'purpose':purpose,'subject':'Test subject','body':'Test exact message'};r=self.client.post('/outbound/messages',json=body);self.assertEqual(r.status_code,201,r.text);return r.json(),body
 def approve(self,p):
  r=self.client.post('/outbound/messages/'+p['id']+'/approve',json={'confirm':True,'expected_digest':p['digest']});self.assertEqual(r.status_code,200,r.text)
 def test_no_send_before_review(self):
  p,_=self.preview()
  with patch.object(out,'deliver') as d:self.assertEqual(out.dispatch_one(now=self.now)['state'],'idle');d.assert_not_called()
 def test_wrong_digest_not_approved(self):
  p,_=self.preview();self.assertEqual(self.client.post('/outbound/messages/'+p['id']+'/approve',json={'confirm':True,'expected_digest':'0'*64}).status_code,409)
 def test_marketing_needs_marketing_consent(self):
  cid=self.contact();r=self.client.post('/outbound/messages',json={'submission_key':str(uuid4()),'contact_id':cid,'purpose':'marketing','body':'Hello promotion'});self.assertEqual(r.status_code,409)
 def test_retry_key_is_idempotent_and_body_immutable(self):
  p,b=self.preview();r=self.client.post('/outbound/messages',json=b);self.assertEqual(r.json()['id'],p['id']);b['body']='Different message';self.assertEqual(self.client.post('/outbound/messages',json=b).status_code,409)
 def test_staff_cannot_view_or_send(self):
  self.user={'id':2,'role':'visitor'};self.assertEqual(self.client.get('/outbound/messages').status_code,403);self.assertEqual(self.client.get('/outbound/contacts').status_code,403)
 def test_other_ceo_cannot_approve_message(self):
  p,_=self.preview();self.user={'id':3,'role':'ceo'};self.assertEqual(self.client.post('/outbound/messages/'+p['id']+'/approve',json={'confirm':True,'expected_digest':p['digest']}).status_code,404)
 def test_no_provider_is_explicit_not_connected(self):
  p,_=self.preview()
  with patch.object(out,'connected',return_value=False):self.assertEqual(self.client.post('/outbound/messages/'+p['id']+'/approve',json={'confirm':True,'expected_digest':p['digest']}).status_code,503)
 def test_revoke_cancels_queue(self):
  cid=self.contact();p,_=self.preview(cid);self.approve(p);self.client.post('/outbound/contacts/'+cid+'/revoke');self.assertEqual(self.client.get('/outbound/messages').json()['items'][0]['state'],'cancelled')
 def test_unknown_outcome_is_never_retried(self):
  p,_=self.preview();self.approve(p)
  # Test dispatch now is daytime; make fixture scheduled_at earlier than the chosen test time.
  self.c.execute(text("UPDATE outbound_messages SET scheduled_at=:at WHERE id=:id"),{'at':self.now,'id':p['id']})
  with patch.object(out,'deliver',side_effect=TimeoutError) as d:
   self.assertEqual(out.dispatch_one(now=self.now)['state'],'review_required');self.assertEqual(out.dispatch_one(now=self.now)['state'],'idle');self.assertEqual(d.call_count,1)
 def test_success_has_receipt_not_delivery_claim(self):
  p,_=self.preview();self.approve(p);self.c.execute(text('UPDATE outbound_messages SET scheduled_at=:at WHERE id=:id'),{'at':self.now,'id':p['id']})
  def send(payload,ident):
   self.assertEqual(self.c.execute(text('SELECT state FROM outbound_messages WHERE id=:id'),{'id':str(ident)}).scalar(),'sending');return {'provider_message_id':'123','accepted':True,'delivered':False}
  with patch.object(out,'deliver',side_effect=send) as d:
   r=out.dispatch_one(now=self.now);self.assertEqual(r['state'],'accepted');self.assertFalse(r['external_delivery_confirmed']);out.dispatch_one(now=self.now);self.assertEqual(d.call_count,1)
 def test_quiet_hours_and_disabled_worker(self):
  self.assertEqual(out.dispatch_one(now=self.now.replace(hour=20))['state'],'quiet_hours')
  with patch.object(out,'enabled',return_value=False):self.assertEqual(out.dispatch_one(now=self.now)['state'],'disabled')
 def test_deactivated_owner_cannot_send(self):
  p,_=self.preview();self.approve(p);self.c.execute(text('UPDATE users SET is_active=0 WHERE id=1'));self.c.execute(text('UPDATE outbound_messages SET scheduled_at=:at WHERE id=:id'),{'at':self.now,'id':p['id']})
  with patch.object(out,'deliver') as d:self.assertEqual(out.dispatch_one(now=self.now)['state'],'cancelled');d.assert_not_called()
 def test_contact_idempotency_and_revocation_not_silently_undone(self):
  cid=self.contact();self.assertEqual(self.contact(),cid);self.client.post('/outbound/contacts/'+cid+'/revoke');r=self.client.post('/outbound/contacts',json={'customer_id':1,'channel':'sms','destination':'09123456789','consent_scope':'transactional','evidence':'A different authorization note'});self.assertEqual(r.status_code,409)

 def balances(self,amount=100,days=0):
  self.c.execute(text('CREATE TABLE receivable_snapshots(id INTEGER PRIMARY KEY,snapshot_date DATE)'))
  self.c.execute(text('CREATE TABLE receivable_balances(snapshot_id INTEGER,customer_id INTEGER,balance NUMERIC)'))
  self.c.execute(text("INSERT INTO receivable_snapshots VALUES(1,:day)"),{'day':out.iran_today()-__import__('datetime').timedelta(days=days)})
  self.c.execute(text('INSERT INTO receivable_balances VALUES(1,1,:amount)'),{'amount':amount})
 def test_settlement_missing_report_blocks_preview(self):
  cid=self.contact();r=self.client.post('/outbound/messages',json={'submission_key':str(uuid4()),'contact_id':cid,'purpose':'settlement','body':'هماهنگی تسویه مشتری'});self.assertEqual(r.status_code,409)
 def test_paid_balance_blocks_settlement(self):
  self.balances(0)
  with self.assertRaises(out.HTTPException):out.settlement_evidence(self.c,1)
 def test_stale_balance_blocks_settlement(self):
  self.balances(days=8)
  with self.assertRaises(out.HTTPException):out.settlement_evidence(self.c,1)
 def test_changed_debt_cancels_previously_approved_send(self):
  self.balances();p,_=self.preview(purpose='settlement');self.approve(p)
  self.c.execute(text('UPDATE receivable_balances SET balance=0'));self.c.execute(text('UPDATE outbound_messages SET scheduled_at=:at WHERE id=:id'),{'at':self.now,'id':p['id']})
  with patch.object(out,'deliver') as d:self.assertEqual(out.dispatch_one(now=self.now)['state'],'cancelled');d.assert_not_called()
 def test_ambiguous_balance_is_not_summed_or_invented(self):
  self.balances();self.c.execute(text('INSERT INTO receivable_balances VALUES(1,1,50)'))
  with self.assertRaises(out.HTTPException):out.settlement_evidence(self.c,1)
 def test_receipt_refresh_reads_provider_without_sending(self):
  p,_=self.preview();self.c.execute(text("UPDATE outbound_messages SET state='accepted',receipt=CAST(:receipt AS JSONB) WHERE id=:id"),{'id':p['id'],'receipt':out.encoded({'provider_message_id':'123','accepted':True})})
  with patch.object(out,'provider_status',return_value={'provider_message_id':'123','accepted':True,'delivered':True}),patch.object(out,'deliver') as send:
   r=self.client.post('/outbound/messages/'+p['id']+'/refresh-receipt');self.assertEqual(r.json()['state'],'delivered');self.assertFalse(r.json()['message_resent']);send.assert_not_called()
 def test_unknown_not_sent_reconciliation_never_requeues(self):
  p,_=self.preview();self.c.execute(text("UPDATE outbound_messages SET state='review_required' WHERE id=:id"),{'id':p['id']})
  with patch.object(out,'deliver') as send:
   r=self.client.post('/outbound/messages/'+p['id']+'/reconcile',json={'reviewed':True,'outcome':'not_sent','evidence_note':'Reviewed provider logs and no matching request exists.'});self.assertEqual(r.json()['state'],'reconciled_not_sent');self.assertEqual(out.dispatch_one(now=self.now)['state'],'idle');send.assert_not_called()
 def test_reconcile_delivered_sms_requires_real_status_read(self):
  p,_=self.preview();self.c.execute(text("UPDATE outbound_messages SET state='review_required' WHERE id=:id"),{'id':p['id']})
  with patch.object(out,'provider_status',side_effect=out.HTTPException(503,'Unavailable')),patch.object(out,'deliver') as send:
   r=self.client.post('/outbound/messages/'+p['id']+'/reconcile',json={'reviewed':True,'outcome':'delivered','provider_message_id':'123','evidence_note':'Manual evidence association needs live provider verification.'});self.assertEqual(r.status_code,503);self.assertEqual(self.c.execute(text('SELECT state FROM outbound_messages WHERE id=:id'),{'id':p['id']}).scalar(),'review_required');send.assert_not_called()
