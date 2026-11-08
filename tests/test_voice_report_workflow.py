import os
import unittest
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
import voice_reports as voice


class SpeechTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(voice.router)
        app.dependency_overrides[voice.current_user] = lambda: {"id": 2, "role": "visitor", "salesperson_id": 10}
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_invalid_and_oversized_audio(self):
        with patch.object(voice, "get_whisper") as model:
            self.assertEqual(self.client.post('/operations/transcribe-audio', json={'audio_base64': '%%%'}).status_code, 400)
            with patch.object(voice, 'MAX_AUDIO_BYTES', 16):
                self.assertEqual(self.client.post('/operations/transcribe-audio', files={'file': ('a.mp4', b'a'*17, 'audio/mp4')}).status_code, 413)
            model.assert_not_called()

    def test_transcription_and_cleanup(self):
        paths = []
        def transcribe(path, **kwargs):
            self.assertTrue(os.path.exists(path))
            paths.append(path)
            return iter([SimpleNamespace(text='امروز کاتالوگ خواست')]), None
        with patch.object(voice, 'get_whisper', return_value=SimpleNamespace(transcribe=transcribe)):
            response = self.client.post('/operations/transcribe-audio', files={'file': ('a.mp4', b'audio', 'audio/mp4')})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('کاتالوگ', response.json()['raw_text'])
        self.assertEqual(response.json()['reported_sales_amount'], 0)
        self.assertTrue(all(not os.path.exists(path) for path in paths))

    def test_missing_model_and_silence(self):
        with patch.object(voice, 'get_whisper', return_value=None):
            self.assertEqual(self.client.post('/operations/transcribe-audio', content=b'audio').status_code, 503)
        model = SimpleNamespace(transcribe=lambda *args, **kwargs: (iter([]), None))
        with patch.object(voice, 'get_whisper', return_value=model):
            self.assertEqual(self.client.post('/operations/transcribe-audio', content=b'audio').status_code, 422)


@unittest.skipUnless(os.getenv('KIARAD_TEST_VOICE_WORKFLOW_DB') == '1', 'Opt-in PostgreSQL test')
class ReportTests(unittest.TestCase):
    def setUp(self):
        self.conn = voice.engine.connect()
        self.addCleanup(self.conn.close)
        transaction = self.conn.begin()
        self.addCleanup(transaction.rollback)
        statements = [
            'CREATE TEMP TABLE salespersons (id INTEGER PRIMARY KEY,name TEXT)',
            'CREATE TEMP TABLE users (id INTEGER PRIMARY KEY,full_name TEXT,role TEXT,salesperson_id INTEGER,is_active INTEGER)',
            'CREATE TEMP TABLE customers (id INTEGER PRIMARY KEY,name TEXT,city TEXT)',
            '''CREATE TEMP TABLE daily_reports (id SERIAL PRIMARY KEY,salesperson_id INTEGER,customer_id INTEGER,report_date DATE,
                visits_count INTEGER NOT NULL,new_customers_count INTEGER NOT NULL,orders_count INTEGER NOT NULL,lost_orders_count INTEGER NOT NULL,
                reported_sales_amount NUMERIC,reported_collections_amount NUMERIC,notes TEXT,tomorrow_plan TEXT,created_at TIMESTAMP,
                UNIQUE(salesperson_id,report_date))''',
            '''CREATE TEMP TABLE tasks (id SERIAL PRIMARY KEY,title VARCHAR(200),description TEXT,priority TEXT,status TEXT,progress INTEGER,
                assigned_to INTEGER REFERENCES users(id),created_by INTEGER,customer_id INTEGER,created_at TIMESTAMP,updated_at TIMESTAMP)''',
            'CREATE TEMP TABLE task_updates (id SERIAL PRIMARY KEY,task_id INTEGER,user_id INTEGER,progress INTEGER,status TEXT,note TEXT,created_at TIMESTAMP)',
            "INSERT INTO salespersons VALUES (10,'اول'),(11,'دوم')",
            "INSERT INTO users VALUES (1,'مدیر','ceo',NULL,1),(2,'اول','visitor',10,1),(3,'دوم','salesperson',11,1)",
            "INSERT INTO customers VALUES (40,'داروخانه اول','کرمان'),(41,'داروخانه دوم','کرمان')",
        ]
        for sql in statements:
            self.conn.execute(text(sql))
        voice._ensure_voice_entries(self.conn, temporary=True)
        voice._ensure_voice_entries(self.conn, temporary=True)
        @contextmanager
        def begin():
            with self.conn.begin_nested():
                yield self.conn
        engine = SimpleNamespace(begin=begin, connect=lambda: nullcontext(self.conn))
        for patcher in (patch.object(voice, 'engine', engine), patch.object(voice, 'role_has_module_permission', return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.user = {'id':2, 'role':'visitor', 'salesperson_id':10}
        app = FastAPI()
        app.include_router(voice.router)
        app.dependency_overrides[voice.current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def submit(self, **changes):
        body = dict(submission_key=str(uuid4()), raw_text='متن کامل ملاقات', summary='خلاصه ملاقات', customer_id=40, visits_count=1)
        body.update(changes)
        return self.client.post('/operations/submit-daily-report', json=body)

    def count(self, table):
        return self.conn.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()

    def test_retry_scope_and_followup(self):
        key = str(uuid4())
        body = dict(submission_key=key, salesperson_id=11, assigned_user_id=3, followup_task='ارسال کاتالوگ')
        first = self.submit(**body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(self.submit(**body).json()['replayed'])
        for table in ('voice_report_entries', 'daily_reports', 'tasks', 'task_updates'):
            self.assertEqual(self.count(table), 1)
        self.assertEqual(self.conn.execute(text('SELECT assigned_to FROM tasks')).scalar(), 2)
        self.assertEqual(self.conn.execute(text('SELECT salesperson_id FROM daily_reports')).scalar(), 10)
        self.assertEqual(self.submit(**{**body, 'summary':'تغییر متن'}).status_code, 409)

    def test_daily_rollup_and_history_scope(self):
        self.assertEqual(self.submit(reported_sales_amount=100).status_code, 200)
        response = self.submit(customer_id=41, visits_count=2, orders_count=1, reported_sales_amount=300)
        self.assertEqual(response.status_code, 200, response.text)
        row = self.conn.execute(text('SELECT * FROM daily_reports')).mappings().one()
        self.assertEqual((row['visits_count'],row['orders_count'],row['reported_sales_amount'],row['customer_id']), (3,1,400,None))
        self.assertEqual(len(self.client.get('/operations/voice-reports').json()['items']), 2)
        self.user = {'id':3,'role':'salesperson','salesperson_id':11}
        self.assertEqual(self.client.get('/operations/voice-reports').json()['items'], [])
        self.user = {'id':1,'role':'ceo'}
        self.assertEqual(len(self.client.get('/operations/voice-reports').json()['items']), 2)

    def test_manager_requires_target_and_atomic_assignment(self):
        self.user = {'id':1,'role':'ceo'}
        self.assertEqual(self.submit().status_code, 403)
        self.assertEqual(self.submit(salesperson_id=10, assigned_user_id=3, followup_task='پیگیری').status_code, 409)
        self.assertEqual(self.count('daily_reports'), 0)
        self.assertEqual(self.submit(salesperson_id=10, assigned_user_id=2, followup_task='پیگیری').status_code, 200)

    def test_validation_and_permission(self):
        for changes in ({'visits_count':-1},{'reported_sales_amount':-1},{'summary':' '},{'raw_text':' '},{'followup_task':'x'*201}):
            self.assertEqual(self.submit(**changes).status_code, 422)
        self.assertEqual(self.submit(customer_id=999).status_code, 404)
        with patch.object(voice, 'role_has_module_permission', return_value=False):
            self.assertEqual(self.submit(followup_task='پیگیری').status_code, 403)
            self.assertEqual(self.submit().status_code, 200)


if __name__ == '__main__':
    unittest.main()
