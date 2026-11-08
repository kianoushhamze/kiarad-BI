from contextlib import contextmanager
from datetime import date
import json,os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
import field_intelligence as intel
from test_inventory_intelligence import payload,POLICY,TODAY

class CoachPureTests(unittest.TestCase):
    def test_objection_advice_quotes_only_existing_reference(self):
        result=intel.recommendations([{'category':'objection','note':'قیمت خیلی گران است','evidence_id':'memory:1'}])
        self.assertEqual(result[0]['evidence_ids'],['memory:1'])
        self.assertIn('مصوب',result[0]['suggestion'])
    def test_no_evidence_is_explicit_and_not_a_customer_claim(self):
        self.assertEqual(intel.recommendations([])[0]['kind'],'missing_evidence')
    def test_model_unknown_reference_and_unstructured_output_rejected(self):
        for value in ({'advice':[{'text':'x','evidence_ids':['foreign:1']}]},{'advice':[{'text':'x','evidence_ids':[]}]},'invalid'):
            self.assertIsNone(intel.validate_explanation(value,{'memory:1'}))
        self.assertEqual(len(intel.validate_explanation({'advice':[{'text':'suggestion','evidence_ids':['memory:1']}]},{'memory:1'})),1)
    def test_staff_cannot_read_inventory_finance_cannot_read_coach(self):
        with self.assertRaises(HTTPException):intel.inventory_user({'role':'visitor'})
        with self.assertRaises(HTTPException):intel.coach_user({'role':'finance'})
    def test_sales_manager_financial_costs_removed(self):
        result={'items':[{'net_sales_irr':10,'estimated_gross_profit_irr':2,'capital_at_current_purchase_price_irr':100,'stock':3}]}
        visible=intel.redact_inventory(result,{'role':'sales_manager'})['items'][0]
        self.assertEqual(visible,{'stock':3})

@unittest.skipUnless(os.getenv('KIARAD_TEST_TREASURY_DB')=='1','Temporary PostgreSQL opt-in')
class IntelligenceDatabaseTests(unittest.TestCase):
    def setUp(self):
        import db
        self.conn=db.engine.connect();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        self.assertEqual(self.conn.exec_driver_sql('SHOW search_path').scalar(),'pg_temp')
        sqls=[
            'CREATE TEMP TABLE users(id INT PRIMARY KEY,salesperson_id INT,role TEXT,is_active INT)',
            "INSERT INTO users VALUES(1,NULL,'ceo',1),(2,10,'visitor',1),(3,11,'visitor',1)",
            'CREATE TEMP TABLE products(id INT PRIMARY KEY)',
            'INSERT INTO products VALUES(1)',
            'CREATE TEMP TABLE customers(id INT PRIMARY KEY)',
            'INSERT INTO customers VALUES(1)',
            'CREATE TEMP TABLE base_portfolio_assignments(base_source TEXT,base_id INT,salesperson_id INT,ended_at TIMESTAMP)',
            "INSERT INTO base_portfolio_assignments VALUES('pharmacies',20,10,NULL)",
            'CREATE TEMP TABLE base_checkins(id INT PRIMARY KEY,base_source TEXT,base_id INT,status TEXT,note TEXT,checked_in_at TIMESTAMP)',
            "INSERT INTO base_checkins VALUES(1,'pharmacies',20,'verified','بازدید آزمایشی','2026-10-19')",
            "CREATE TEMP TABLE tasks(id SERIAL PRIMARY KEY,title TEXT,description TEXT,priority TEXT,status TEXT,progress INT,assigned_to INT,created_by INT,customer_id INT,due_date TIMESTAMP,created_at TIMESTAMP,updated_at TIMESTAMP,review_status TEXT DEFAULT 'not_submitted')",
            'CREATE TEMP TABLE task_updates(id SERIAL PRIMARY KEY,task_id INT,user_id INT,progress INT,status TEXT,note TEXT,created_at TIMESTAMP)',
            'CREATE TEMP TABLE holoo_entity_mappings(entity_type TEXT,local_id INT,holoo_erp_code TEXT)',
            "INSERT INTO holoo_entity_mappings VALUES('product',1,'p1')",
            'CREATE TEMP TABLE holoo_financial_snapshots(id INT PRIMARY KEY,payload JSONB,captured_at TIMESTAMPTZ DEFAULT NOW())',
            "CREATE TEMP TABLE inventory_reservations(product_id INT,quantity NUMERIC,status TEXT)",
            'CREATE TEMP TABLE inventory_batches(product_id INT,batch_code TEXT,expiry_date DATE,quantity NUMERIC)',
        ]
        for source in intel.BASES:sqls.append(f'CREATE TEMP TABLE {source}(id INT PRIMARY KEY,name TEXT,city TEXT,type TEXT)')
        sqls.append("INSERT INTO pharmacies VALUES(20,'پایگاه آزمایشی','کرمان','داروخانه'),(21,'دیگر','کرمان','داروخانه')")
        for sql in sqls:self.conn.execute(text(sql))
        intel.ensure_schema(self.conn)
        self.conn.execute(text('INSERT INTO holoo_financial_snapshots(id,payload) VALUES(1,CAST(:p AS JSONB))'),{'p':json.dumps(payload())})
        @contextmanager
        def transaction():yield self.conn
        for p in (patch.object(intel,'engine',SimpleNamespace(begin=transaction,connect=transaction)),patch.object(intel,'iran_today',return_value=TODAY)):
            p.start();self.addCleanup(p.stop)
        self.user={'id':1,'role':'ceo'};self.staff={'id':2,'role':'visitor','salesperson_id':10}

    def memory(self,**changes):
        return intel.add_memory('pharmacies',20,intel.MemoryInput(submission_key=uuid4(),category='objection',note='قیمت کالا گران است',**changes),self.staff)
    def test_staff_base_scope_and_source_whitelist(self):
        self.assertEqual(len(intel.coach_bases('',self.staff)['items']),1)
        with self.assertRaises(HTTPException):intel.get_base_dossier('pharmacies',21,self.staff)
        with self.assertRaises(HTTPException):intel.get_base_dossier('users',1,self.user)
    def test_memory_append_idempotency_and_payload_conflict(self):
        model=intel.MemoryInput(submission_key=uuid4(),category='report',note='گزارش مراجعه آزمایشی')
        first=intel.add_memory('pharmacies',20,model,self.staff)
        self.assertTrue(intel.add_memory('pharmacies',20,model,self.staff)['already_saved'])
        with self.assertRaises(HTTPException):intel.add_memory('pharmacies',20,model.model_copy(update={'note':'متن متفاوت آزمایشی'}),self.staff)
        dossier=intel.get_base_dossier('pharmacies',20,self.staff)
        self.assertIn('memory:'+str(first['id']),[r['evidence_id'] for r in dossier['evidence']])
    def test_reassignment_revokes_previous_staff_read_and_write(self):
        self.memory();self.conn.execute(text('UPDATE base_portfolio_assignments SET salesperson_id=11'))
        with self.assertRaises(HTTPException):intel.get_base_dossier('pharmacies',20,self.staff)
        with self.assertRaises(HTTPException):self.memory()
    def test_profile_is_versioned_and_staff_cannot_change_link(self):
        model=intel.BaseProfile(customer_id=1,grade='A',source_note='تطبیق صریح آزمایشی')
        with self.assertRaises(HTTPException):intel.save_base_profile('pharmacies',20,model,self.staff)
        intel.save_base_profile('pharmacies',20,model,self.user)
        with self.assertRaises(HTTPException):intel.save_base_profile('pharmacies',20,model,self.user)
        self.assertEqual(intel.get_base_dossier('pharmacies',20,self.staff)['profile']['revision'],1)
    def test_action_requires_in_scope_evidence_and_manager_approval_creates_one_task(self):
        self.memory()
        model=intel.ActionInput(submission_key=uuid4(),title='پیگیری اعتراض ثبت شده',reason='رفع ابهام درباره قیمت و نیاز واقعی',due_date=TODAY,evidence_ids=['visit:1'])
        proposed=intel.propose_action('pharmacies',20,model,self.staff)
        self.assertEqual(self.conn.execute(text('SELECT count(*) FROM tasks')).scalar(),0)
        with self.assertRaises(HTTPException):intel.review_action(proposed['id'],intel.Decision(decision='approve',note='تأیید آزمایشی مدیر'),self.staff)
        done=intel.review_action(proposed['id'],intel.Decision(decision='approve',note='تأیید آزمایشی مدیر'),self.user)
        self.assertIsNotNone(done['task_id'])
        self.assertEqual(self.conn.execute(text('SELECT assigned_to FROM tasks')).scalar(),2)
        with self.assertRaises(HTTPException):intel.review_action(proposed['id'],intel.Decision(decision='approve',note='تأیید آزمایشی مدیر'),self.user)
        with self.assertRaises(HTTPException):intel.propose_action('pharmacies',20,model.model_copy(update={'submission_key':uuid4(),'evidence_ids':['memory:999']}),self.staff)
    def test_task_result_appears_in_same_base_history(self):
        model=intel.ActionInput(submission_key=uuid4(),title='پیگیری اعتراض پایگاه',reason='رسیدگی به نتیجه بازدید قبلی',due_date=TODAY,evidence_ids=['visit:1'])
        action=intel.propose_action('pharmacies',20,model,self.staff)
        done=intel.review_action(action['id'],intel.Decision(decision='approve',note='تأیید آزمایشی مدیر'),self.user)
        self.conn.execute(text("INSERT INTO task_updates(task_id,user_id,note) VALUES(:id,2,'نتیجهٔ واقعی آزمایشی')"),{'id':done['task_id']})
        self.assertEqual(intel.get_base_dossier('pharmacies',20,self.staff)['actions'][0]['latest_result'],'نتیجهٔ واقعی آزمایشی')
    def test_no_customer_link_does_not_guess_name_or_show_invoice_history(self):
        dossier=intel.get_base_dossier('pharmacies',20,self.staff)
        self.assertEqual(dossier['purchase_history'],[])
        self.assertTrue(dossier['warnings'])
    def test_policy_version_and_order_draft_recompute_and_stale_protection(self):
        policy=intel.InventoryPolicy(**{k:v for k,v in POLICY.items() if k!='revision'},source_note='سیاست تأمین واحد آزمایشی')
        intel.save_inventory_policy('p1',policy,self.user)
        with self.assertRaises(HTTPException):intel.save_inventory_policy('p1',policy,self.user)
        model=intel.OrderInput(submission_key=uuid4(),erp_code='p1',snapshot_id=1,policy_revision=1)
        draft=intel.draft_inventory_order(model,self.user)
        self.assertTrue(intel.draft_inventory_order(model,self.user)['already_saved'])
        self.assertFalse(draft['supplier_order_placed'])
        self.conn.execute(text("UPDATE holoo_financial_snapshots SET payload=jsonb_set(payload,'{to_date}','\"2026-10-19\"'::jsonb)"))
        with self.assertRaises(HTTPException):intel.review_inventory_order(draft['id'],intel.Decision(decision='approve',note='آزمون رد منبع کهنه'),self.user)
    def test_model_unavailable_keeps_rule_based_result_without_saving(self):
        self.memory()
        with patch('requests.sessions.Session.post',side_effect=intel.requests.ConnectionError()):
            result=intel.explain_base('pharmacies',20,self.staff)
        self.assertEqual(result['status'],'rules_only')
        self.assertFalse(result['saved'])

    def test_empty_reservations_prove_zero_but_unmapped_holds_do_not(self):
        self.conn.execute(text('DELETE FROM holoo_entity_mappings'))
        self.assertEqual(intel.load_inventory(self.conn,90)['items'][0]['reserved'],0)
        self.conn.execute(text("INSERT INTO inventory_reservations VALUES(1,2,'reserved')"))
        self.assertIsNone(intel.load_inventory(self.conn,90)['items'][0]['reserved'])

    def test_customer_cannot_link_to_two_active_base_profiles(self):
        model=intel.BaseProfile(customer_id=1,source_note='تطبیق صریح آزمایشی')
        intel.save_base_profile('pharmacies',20,model,self.user)
        with self.assertRaises(HTTPException):intel.save_base_profile('pharmacies',21,model,self.user)
        intel.save_base_profile('pharmacies',20,intel.BaseProfile(expected_revision=1,source_note='حذف پیوند پیشین آزمایشی'),self.user)
        self.assertEqual(intel.save_base_profile('pharmacies',21,model,self.user)['revision'],1)

    def test_only_active_previously_bought_product_can_be_suggested(self):
        self.conn.execute(text("INSERT INTO holoo_entity_mappings VALUES('customer',1,'c1')"))
        intel.save_base_profile('pharmacies',20,intel.BaseProfile(customer_id=1,source_note='تطبیق صریح آزمایشی'),self.user)
        p=payload();p['sources']['sales']['rows'][0]['CustomerErpCode']='c1'
        for active in (False,True):
            p['sources']['products']['rows'][0]['IsActive']=active
            self.conn.execute(text('UPDATE holoo_financial_snapshots SET payload=CAST(:p AS JSONB)'),{'p':json.dumps(p)})
            dossier=intel.get_base_dossier('pharmacies',20,self.staff)
            self.assertEqual(len(dossier['purchase_history']),1)
            self.assertEqual(len(dossier['product_suggestions']),1 if active else 0)

    def test_order_review_records_decision_only_and_cannot_repeat(self):
        policy=intel.InventoryPolicy(**{k:v for k,v in POLICY.items() if k!='revision'},source_note='سیاست تأمین واحد آزمایشی')
        intel.save_inventory_policy('p1',policy,self.user)
        for decision in ('approve','reject'):
            draft=intel.draft_inventory_order(intel.OrderInput(submission_key=uuid4(),erp_code='p1',snapshot_id=1,policy_revision=1),self.user)
            model=intel.Decision(decision=decision,note='تصمیم آزمایشی واحد مالی')
            result=intel.review_inventory_order(draft['id'],model,self.user)
            self.assertFalse(result['supplier_order_placed'])
            self.assertFalse(result['financial_entry_created'])
            self.assertEqual(result['status'],'reviewed' if decision=='approve' else 'rejected')
            with self.assertRaises(HTTPException):intel.review_inventory_order(draft['id'],model,self.user)
