import os
import unittest
from contextlib import contextmanager,nullcontext
from datetime import date,timedelta
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import text
from fastapi import FastAPI
from fastapi.testclient import TestClient
import visit_coverage as visits


class CoverageBoundaryTests(unittest.TestCase):
    def test_fifteen_days_due_today_and_unknown_history(self):
        today=date(2026,10,17)
        result=visits.classify_visit(today-timedelta(days=15),None,today)
        self.assertEqual(result['status'],'due_today')
        self.assertIsNone(result['days_since_verified_visit'])
        self.assertEqual(result['days_overdue'],0)

    def test_overdue_and_recent_verified_visit(self):
        today=date(2026,10,17)
        self.assertEqual(visits.classify_visit(today-timedelta(days=30),None,today)['days_overdue'],15)
        self.assertEqual(visits.classify_visit(today-timedelta(days=30),today-timedelta(days=2),today)['status'],'on_schedule')


@unittest.skipUnless(os.getenv('KIARAD_TEST_VISIT_COVERAGE_DB')=='1','Temporary PostgreSQL tables')
class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.conn=visits.engine.connect()
        self.addCleanup(self.conn.close)
        tx=self.conn.begin()
        self.addCleanup(tx.rollback)
        statements=[
            'CREATE TEMP TABLE salespersons (id INTEGER PRIMARY KEY,name TEXT)',
            'CREATE TEMP TABLE users (id INTEGER PRIMARY KEY)',
            "INSERT INTO salespersons VALUES (10,'اول'),(11,'دوم')",
            'INSERT INTO users VALUES (1),(2),(3)',
            '''CREATE TEMP TABLE base_checkins (id SERIAL PRIMARY KEY,salesperson_id INTEGER,base_source TEXT,
                base_id INTEGER,status TEXT,checked_in_at TIMESTAMP)''',
        ]
        for name in ('pharmacies','cosmetics_shops','kerman_bases_manual'):
            statements.append(f'CREATE TEMP TABLE {name} (id INTEGER PRIMARY KEY,name TEXT,city TEXT)')
        statements.append("INSERT INTO pharmacies VALUES (20,'پایگاه','کرمان')")
        for sql in statements:self.conn.execute(text(sql))
        visits.ensure_portfolios(self.conn,temporary=True)
        visits.ensure_portfolios(self.conn,temporary=True)
        @contextmanager
        def begin():
            with self.conn.begin_nested():yield self.conn
        patcher=patch.object(visits,'engine',SimpleNamespace(begin=begin,connect=lambda:nullcontext(self.conn)))
        patcher.start();self.addCleanup(patcher.stop)
        self.user={'id':1,'role':'ceo'}
        app=FastAPI();app.include_router(visits.router)
        app.dependency_overrides[visits.current_user]=lambda:self.user
        self.client=TestClient(app);self.addCleanup(self.client.close)

    def assign(self,person=10,**changes):
        data={'salesperson_id':person,'source':'pharmacies','base_id':20};data.update(changes)
        return self.client.post('/api/compensation/base-portfolios',json=data)

    def test_repeat_assignment_and_reassignment_keep_history(self):
        first=self.assign();self.assertEqual(first.status_code,200,first.text)
        self.assertTrue(self.assign().json()['unchanged'])
        self.assertEqual(self.assign(11).status_code,200)
        rows=self.conn.execute(text('SELECT * FROM base_portfolio_assignments ORDER BY id')).mappings().all()
        self.assertEqual(len(rows),2);self.assertIsNotNone(rows[0]['ended_at']);self.assertIsNone(rows[1]['ended_at'])

    def test_staff_cannot_assign_or_override_other_person_scope(self):
        self.assign()
        self.user={'id':2,'role':'visitor','salesperson_id':11}
        self.assertEqual(self.assign().status_code,403)
        self.assertEqual(self.client.get('/api/compensation/visit-coverage?salesperson_id=10').json()['items'],[])
        self.user={'id':3,'role':'salesperson','salesperson_id':10}
        self.assertEqual(len(self.client.get('/api/compensation/visit-coverage?salesperson_id=11').json()['items']),1)

    def test_only_verified_visits_after_assignment_reset_due_date(self):
        self.assign()
        self.conn.execute(text("UPDATE base_portfolio_assignments SET assigned_at=(NOW() AT TIME ZONE 'Asia/Tehran')-INTERVAL '20 days'"))
        for status,days in [('verified',25),('rejected',1),('pending_review',1)]:
            self.conn.execute(text("""INSERT INTO base_checkins (salesperson_id,base_source,base_id,status,checked_in_at)
                VALUES (10,'pharmacies',20,:status,(NOW() AT TIME ZONE 'Asia/Tehran')-:days*INTERVAL '1 day')"""),{'status':status,'days':days})
        item=self.client.get('/api/compensation/visit-coverage').json()['items'][0]
        self.assertEqual(item['status'],'overdue');self.assertIsNone(item['last_verified_visit'])
        self.conn.execute(text("""INSERT INTO base_checkins (salesperson_id,base_source,base_id,status,checked_in_at)
            VALUES (10,'pharmacies',20,'verified',(NOW() AT TIME ZONE 'Asia/Tehran')-INTERVAL '1 day')"""))
        item=self.client.get('/api/compensation/visit-coverage').json()['items'][0]
        self.assertEqual(item['status'],'on_schedule');self.assertEqual(item['verified_visits_15_days'],1)

    def test_missing_base_profile_and_invalid_source_rejected(self):
        for data,code in [({'person':999},404),({'base_id':999},404),({'source':'users'},422)]:
            person=data.pop('person',10)
            self.assertEqual(self.assign(person,**data).status_code,code)


if __name__=='__main__':unittest.main()
