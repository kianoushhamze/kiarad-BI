"""One synthetic field day through HTTP handlers and real TEMP SQL, rolled back."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
import compensation
from payroll_periods import current_payroll_month,payroll_period
import test_payroll_service as fixtures


@unittest.skipUnless(os.getenv('KIARAD_TEST_PAYROLL_DB')=='1','Temporary database opt-in')
class FieldDayWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PayrollServiceDatabaseTests('test_schema_is_idempotent_and_every_relation_is_temporary')
        self.addCleanup(self.fixture.doCleanups);self.fixture.setUp()
        self.conn=self.fixture.conn;self.cur=self.fixture.cur
        self.fixture.month=current_payroll_month()
        _,self.fixture.start,self.fixture.end,_=payroll_period(self.fixture.month)
        self.month=self.fixture.month
        for column in ('start_lat','start_lng','end_lat','end_lng'):
            self.cur.execute(f'ALTER TABLE attendance_sessions ADD COLUMN {column} DOUBLE PRECISION')
        for definition in ('base_source TEXT','base_id INTEGER','latitude FLOAT','longitude FLOAT','accuracy_m FLOAT','distance_m FLOAT','note TEXT'):
            self.cur.execute('ALTER TABLE base_checkins ADD COLUMN '+definition)
        for table in compensation.BASE_TABLES:
            self.cur.execute(f'CREATE TEMP TABLE {table}(id INT PRIMARY KEY,name TEXT,latitude FLOAT,longitude FLOAT,visit_radius_m INT)')
        self.cur.execute("INSERT INTO pharmacies VALUES(1,'پایگاه ساختگی',30,57,150)")
        compensation._ensure_attendance_schema(self.cur,temporary=True)
        compensation._ensure_checkin_review_schema(self.cur,temporary=True)
        compensation._ensure_checkin_submission_schema(self.cur,temporary=True)
        borrowed=SimpleNamespace(cursor=self.conn.cursor,commit=lambda:None,rollback=lambda:None,close=lambda:None)
        patcher=patch.object(compensation,'get_connection',return_value=borrowed)
        patcher.start();self.addCleanup(patcher.stop)
        self.user={'id':2,'role':'visitor','salesperson_id':10}
        app=FastAPI();app.include_router(compensation.router)
        app.dependency_overrides[compensation.current_user]=lambda:self.user
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.position={'lat':30,'lng':57,'accuracy_m':20}

    def test_shift_visit_retry_review_close_and_approved_payroll(self):
        self.fixture.save(hourly_rate=100,daily_mission_allowance=50,sales_scope='personal',
                          commission_tier_basis='marginal',sales_tiers=[{'up_to_amount':None,'percent':5}])
        first=self.client.post('/api/compensation/attendance/start',json=self.position)
        self.assertEqual(first.status_code,200,first.text)
        repeated=self.client.post('/api/compensation/attendance/start',json=self.position)
        self.assertEqual(repeated.json()['status'],'already_active')
        body={**self.position,'source':'pharmacies','base_id':1,'note':'اعتراض قیمت و نتیجهٔ مذاکرهٔ ساختگی','submission_key':str(uuid4())}
        visit=self.client.post('/api/compensation/base-checkins',json=body)
        self.assertEqual(visit.status_code,200,visit.text)
        self.assertEqual(visit.json()['status'],'pending_review')
        self.assertTrue(self.client.post('/api/compensation/base-checkins',json=body).json()['already_saved'])
        review=f"/api/compensation/base-checkins/{visit.json()['checkin_id']}/review"
        self.assertEqual(self.client.post(review,json={'decision':'verified','note':'تأیید ساختگی'}).status_code,403)
        self.cur.execute("UPDATE attendance_sessions SET start_time=(NOW() AT TIME ZONE 'Asia/Tehran')-INTERVAL '2 hours'")
        stopped=self.client.post('/api/compensation/attendance/stop',json=self.position)
        self.assertEqual(stopped.status_code,200,stopped.text)
        self.assertEqual(stopped.json()['duration_hours'],2)
        self.user={'id':1,'role':'ceo','salesperson_id':None}
        self.assertEqual(self.client.post(review,json={'decision':'verified','note':'تأیید بازدید ساختگی توسط مدیر'}).status_code,200)
        self.fixture.fact(amount=1000);self.fixture.complete()
        result=self.client.get(f'/api/compensation/payroll/10?month={self.month}')
        self.assertEqual(result.status_code,200,result.text)
        calculation=result.json()
        self.assertEqual(calculation['base_pay'],200)
        self.assertEqual(calculation['verified_visit_allowance'],50)
        self.assertEqual(calculation['sales_commission'],50)
        approved=self.client.post(f'/api/compensation/payroll/10/approve?month={self.month}',json={'note':'پذیرش گردش ساختگی در جدول موقت'})
        self.assertEqual(approved.status_code,200,approved.text)
        self.assertEqual(approved.json()['approved_total'],300)
        self.cur.execute('SELECT COUNT(*) FROM base_checkins');self.assertEqual(self.cur.fetchone()[0],1)
        self.cur.execute('SELECT COUNT(*) FROM payroll_approval_history');self.assertEqual(self.cur.fetchone()[0],1)
        self.user={'id':2,'role':'visitor','salesperson_id':10}
        self.assertEqual(self.client.get(f'/api/compensation/payroll/11?month={self.month}').status_code,403)
        self.assertEqual(self.client.post('/api/compensation/base-checkins',json={**body,'submission_key':str(uuid4())}).status_code,409)

    def test_missing_contract_cannot_be_approved_as_zero(self):
        self.user={'id':1,'role':'ceo','salesperson_id':None}
        response=self.client.post(f'/api/compensation/payroll/10/approve?month={self.month}',json={})
        self.assertEqual(response.status_code,409,response.text)
        self.cur.execute('SELECT COUNT(*) FROM payroll_approval_history')
        self.assertEqual(self.cur.fetchone()[0],0)
