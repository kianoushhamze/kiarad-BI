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
import training_workflows as mod
@unittest.skipUnless(os.getenv('KIARAD_TEST_TRAINING_DB')=='1','Opt-in disposable PostgreSQL')
class TrainingTests(unittest.TestCase):
 def setUp(self):
  self.c=engine.connect();self.tx=self.c.begin();self.addCleanup(self.c.close);self.addCleanup(self.tx.rollback);schema='training_test_'+uuid4().hex;self.c.execute(text('CREATE SCHEMA '+schema));self.c.execute(text('SET LOCAL search_path TO '+schema));self.c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY,full_name TEXT,role TEXT,is_active INTEGER)'));self.c.execute(text("INSERT INTO users VALUES(1,'Teacher','ceo',1),(2,'Learner','visitor',1),(3,'Other','visitor',1)"));self.c.execute(text('CREATE TABLE customers(id INTEGER PRIMARY KEY)'));self.c.execute(text('CREATE TABLE agent_sources(id UUID PRIMARY KEY,owner_id INTEGER,kind TEXT,title TEXT,content TEXT)'));self.source=str(uuid4());self.c.execute(text("INSERT INTO agent_sources VALUES(:id,1,'training','Product guide','Read the approved label before describing any product.')"),{'id':self.source});mod.ensure(self.c)
  e=self.enterContext(patch.object(mod,'engine'));e.begin.side_effect=self.atomic;e.connect.side_effect=lambda:nullcontext(self.c)
  self.user={'id':1,'role':'ceo'};app=FastAPI();app.include_router(mod.router);app.dependency_overrides[current_user]=lambda:self.user;self.client=TestClient(app);self.addCleanup(self.client.close)
 @contextmanager
 def atomic(self):
  with self.c.begin_nested():yield self.c
 def body(self):return {'submission_key':str(uuid4()),'title':'Approved product training','objective':'Read label and describe only approved facts','lessons':[{'title':'Read product label','body':'Before explaining products, read the approved label carefully.','source_id':self.source,'source_quote':'Read the approved label before describing any product.'}],'questions':[{'prompt':'What should be read first?','choices':['Approved label','Unverified rumor'],'correct_index':0,'lesson_index':0,'explanation':'The approved label is the source of product claims.'}]}
 def create(self):
  b=self.body();r=self.client.post('/training/programmes',json=b);self.assertEqual(r.status_code,201,r.text);return r.json(),b
 def publish(self,p,ids=None):return self.client.post('/training/programmes/'+p['id']+'/publish',json={'confirm':True,'expected_digest':p['digest'],'user_ids':ids or [2],'due_date':(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()})
 def test_draft_has_no_employee_tasks(self):
  self.create();self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM tasks')).scalar(),0)
 def test_citations_and_source_ownership_enforced(self):
  b=self.body();b['lessons'][0]['source_quote']='Invented quotation';self.assertEqual(self.client.post('/training/programmes',json=b).status_code,422);self.user={'id':3,'role':'ceo'};self.assertEqual(self.client.post('/training/programmes',json=self.body()).status_code,404)
 def test_creation_is_idempotent(self):
  p,b=self.create();self.assertEqual(self.client.post('/training/programmes',json=b).json()['id'],p['id']);b['title']='Changed draft';self.assertEqual(self.client.post('/training/programmes',json=b).status_code,409)
 def test_publish_and_enrollments_are_idempotent(self):
  p,_=self.create();r=self.publish(p);self.assertEqual(r.status_code,200,r.text);self.publish(p);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM tasks')).scalar(),1);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM training_enrollments')).scalar(),1)
 def test_inactive_learner_rolls_back_all_assignments(self):
  p,_=self.create();self.c.execute(text('UPDATE users SET is_active=0 WHERE id=3'));self.assertEqual(self.publish(p,[2,3]).status_code,422);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM tasks')).scalar(),0)
 def test_learner_does_not_receive_answer_keys(self):
  p,_=self.create();self.publish(p);self.user={'id':2,'role':'visitor'};r=self.client.get('/training/programmes/'+p['id']);self.assertEqual(r.status_code,200,r.text);self.assertNotIn('correct_index',r.json()['programme']['questions'][0]);self.assertNotIn('explanation',r.json()['programme']['questions'][0]);self.user={'id':3,'role':'visitor'};self.assertEqual(self.client.get('/training/programmes/'+p['id']).status_code,403)
 def test_passing_quiz_submits_actual_task_for_review_atomically(self):
  p,_=self.create();self.publish(p);self.user={'id':2,'role':'visitor'};key=str(uuid4());r=self.client.post('/training/programmes/'+p['id']+'/attempts',json={'submission_key':key,'answers':[0]});self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['passed']);self.assertEqual(r.json()['task_sync'],'submitted_for_manager_review');self.assertFalse(r.json()['manager_approval_granted']);task=self.c.execute(text('SELECT progress,review_status FROM tasks')).mappings().one();self.assertEqual(task['progress'],100);self.assertEqual(task['review_status'],'pending');again=self.client.post('/training/programmes/'+p['id']+'/attempts',json={'submission_key':key,'answers':[0]});self.assertEqual(again.json()['attempt_id'],r.json()['attempt_id']);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM training_attempts')).scalar(),1)
 def test_failed_quiz_does_not_complete_task_and_is_bounded(self):
  p,_=self.create();self.publish(p);self.user={'id':2,'role':'visitor'}
  for _ in range(3):
   r=self.client.post('/training/programmes/'+p['id']+'/attempts',json={'submission_key':str(uuid4()),'answers':[1]});self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['passed'])
  self.assertEqual(self.client.post('/training/programmes/'+p['id']+'/attempts',json={'submission_key':str(uuid4()),'answers':[1]}).status_code,409);self.assertEqual(self.c.execute(text('SELECT progress FROM tasks')).scalar(),0)
 def test_student_cannot_publish_or_view_team_results(self):
  p,_=self.create();self.publish(p);self.user={'id':2,'role':'visitor'};self.assertEqual(self.publish(p).status_code,403);self.assertEqual(self.client.get('/training/programmes/'+p['id']+'/progress').status_code,403)
 def test_incomplete_answers_are_rejected_without_attempt_record(self):
  p,_=self.create();self.publish(p);self.user={'id':2,'role':'visitor'};r=self.client.post('/training/programmes/'+p['id']+'/attempts',json={'submission_key':str(uuid4()),'answers':[5]});self.assertEqual(r.status_code,422);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM training_attempts')).scalar(),0)
 def test_recurring_training_enrolls_new_role_once(self):
  import agent_routines as routines
  p,_=self.create();self.assertEqual(self.publish(p,[2]).status_code,200)
  mocked=self.enterContext(patch.object(routines,'engine'));mocked.connect.side_effect=lambda:nullcontext(self.c)
  recipe={'programme_id':p['id'],'roles':['visitor'],'due_days':7,'max_people_per_cycle':20};r={'kind':'training_enrollment','spec':{'recipe':recipe}}
  result=routines.execute_recipe(r,{'id':uuid4()},self.user);self.assertEqual(result['new_enrollments'],1);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM training_enrollments')).scalar(),2)
  again=routines.execute_recipe(r,{'id':uuid4()},self.user);self.assertEqual(again['new_enrollments'],0);self.assertEqual(self.c.execute(text('SELECT COUNT(*) FROM tasks')).scalar(),2)
