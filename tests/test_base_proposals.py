import os
import unittest
from contextlib import contextmanager,nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
import base_proposals as proposals


class ProposalNormalizationTests(unittest.TestCase):
    def test_persian_variants_and_spaces_match(self):
        self.assertEqual(proposals.normalize('آرایشگاه کیمیا'),proposals.normalize('ارايشگاه\u200c كيميا'))

    def test_staff_cannot_bypass_review_via_legacy_crud_or_import(self):
        import crud_api
        app=FastAPI();app.include_router(crud_api.router)
        app.dependency_overrides[crud_api.current_user]=lambda:{'id':2,'role':'visitor','salesperson_id':10}
        client=TestClient(app);self.addCleanup(client.close)
        with patch.object(crud_api.engine,'begin') as begin:
            for table in proposals.BASE_TABLES:
                self.assertEqual(client.post(f'/crud/{table}',json={'name':'نباید ثبت شود'}).status_code,403)
                self.assertEqual(client.put(f'/crud/{table}/1',json={'name':'تغییر'}).status_code,403)
                self.assertEqual(client.delete(f'/crud/{table}/1').status_code,403)
                self.assertEqual(client.post(f'/import/excel/{table}',files={'file':('test.xlsx',b'bad','application/octet-stream')}).status_code,403)
            begin.assert_not_called()


@unittest.skipUnless(os.getenv('KIARAD_TEST_BASE_PROPOSALS_DB')=='1','Temporary PostgreSQL tables')
class ProposalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.conn=proposals.engine.connect();self.addCleanup(self.conn.close)
        tx=self.conn.begin();self.addCleanup(tx.rollback)
        statements=[
            'CREATE TEMP TABLE salespersons (id INTEGER PRIMARY KEY)',
            'CREATE TEMP TABLE users (id INTEGER PRIMARY KEY,full_name TEXT)',
            'INSERT INTO salespersons VALUES (10),(11)',
            "INSERT INTO users VALUES (1,'مدیر'),(2,'اول'),(3,'دوم')",
        ]
        for table in proposals.BASE_TABLES:
            statements.append(f'''CREATE TEMP TABLE {table} (id SERIAL PRIMARY KEY,name TEXT NOT NULL,city TEXT,
                address TEXT,phone TEXT,type TEXT,latitude DOUBLE PRECISION,longitude DOUBLE PRECISION,visit_radius_m INTEGER)''')
        for sql in statements:self.conn.execute(text(sql))
        proposals.ensure_proposals(self.conn,temporary=True)
        proposals.ensure_proposals(self.conn,temporary=True)
        @contextmanager
        def begin():
            with self.conn.begin_nested():yield self.conn
        patcher=patch.object(proposals,'engine',SimpleNamespace(begin=begin,connect=lambda:nullcontext(self.conn)))
        patcher.start();self.addCleanup(patcher.stop)
        self.user={'id':2,'role':'visitor','salesperson_id':10}
        app=FastAPI();app.include_router(proposals.router)
        app.dependency_overrides[proposals.current_user]=lambda:self.user
        self.client=TestClient(app);self.addCleanup(self.client.close)

    def submit(self,**changes):
        data={'submission_key':str(uuid4()),'name':'داروخانه آزمون','city':'کرمان','address':'نشانی پایگاه آزمون',
              'category':'pharmacy','latitude':30.2,'longitude':57.1,'accuracy_m':20,'note':'مراجعه و معرفی اولیه'}
        data.update(changes)
        return self.client.post('/api/compensation/base-proposals',json=data)

    def manager(self):self.user={'id':1,'role':'ceo'}

    def review(self,identity,decision='approved',note='بررسی و تأیید مشخصات'):
        return self.client.post(f'/api/compensation/base-proposals/{identity}/review',json={'decision':decision,'note':note})

    def count(self,table):return self.conn.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()

    def test_submission_retry_scope_and_no_premature_base(self):
        key=str(uuid4())
        result=self.submit(submission_key=key,salesperson_id=11)
        self.assertEqual(result.status_code,201,result.text)
        self.assertTrue(self.submit(submission_key=key).json()['replayed'])
        self.assertEqual(self.count('base_proposals'),1)
        self.assertEqual(self.count('kerman_bases_manual'),0)
        self.assertEqual(self.conn.execute(text('SELECT salesperson_id FROM base_proposals')).scalar(),10)
        self.assertEqual(self.submit(submission_key=key,note='محتوای متفاوت').status_code,409)
        self.user={'id':3,'role':'salesperson','salesperson_id':11}
        self.assertEqual(self.client.get('/api/compensation/base-proposals').json()['items'],[])

    def test_manager_approval_is_atomic_final_and_never_sends_holoo(self):
        identity=self.submit().json()['id']
        self.assertEqual(self.review(identity).status_code,403)
        self.manager()
        response=self.review(identity)
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['holoo_sent'])
        self.assertEqual(self.count('kerman_bases_manual'),1)
        row=self.conn.execute(text('SELECT * FROM base_proposals')).mappings().one()
        self.assertEqual((row['status'],row['reviewed_by'],row['holoo_status']),('approved',1,'awaiting_connector'))
        self.assertEqual(self.review(identity).status_code,409)
        self.assertEqual(self.count('kerman_bases_manual'),1)

    def test_reject_requires_reason_and_creates_no_base(self):
        identity=self.submit().json()['id'];self.manager()
        self.assertEqual(self.review(identity,'rejected','  ').status_code,422)
        self.assertEqual(self.review(identity,'rejected','مکان تأیید نشد').status_code,200)
        self.assertEqual(self.count('kerman_bases_manual'),0)

    def test_exact_duplicate_blocks_approval(self):
        identity=self.submit().json()['id']
        self.conn.execute(text("INSERT INTO pharmacies (name,city) VALUES ('داروخانه آزمون','کرمان')"))
        self.manager()
        row=self.client.get('/api/compensation/base-proposals').json()['items'][0]
        self.assertEqual(len(row['duplicate_candidates']),1)
        self.assertNotIn('payload_hash',row)
        self.assertEqual(self.review(identity).status_code,409)
        self.assertEqual(self.count('kerman_bases_manual'),0)

    def test_invalid_coordinates_blank_text_unlinked_and_imprecise_point(self):
        for changes in ({'latitude':91},{'longitude':181},{'accuracy_m':-1},{'name':'  '},{'category':'users'}):
            self.assertEqual(self.submit(**changes).status_code,422)
        self.user={'id':2,'role':'visitor','salesperson_id':None}
        self.assertEqual(self.submit().status_code,403)
        self.user={'id':2,'role':'visitor','salesperson_id':10}
        identity=self.submit(accuracy_m=200).json()['id'];self.manager()
        self.assertEqual(self.review(identity).status_code,422)
        self.assertEqual(self.count('kerman_bases_manual'),0)

    def test_missing_record_and_self_review_denied(self):
        identity=self.submit().json()['id']
        self.user={'id':2,'role':'ceo'}
        self.assertEqual(self.review(identity).status_code,403)
        self.manager();self.assertEqual(self.review(999).status_code,404)


if __name__=='__main__':unittest.main()
