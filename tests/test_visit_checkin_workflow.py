"""PostgreSQL temporary-table tests; rollback removes all fixture data.

Enable with KIARAD_TEST_VISIT_WORKFLOW_DB=1. Auth dependencies are overridden,
while scope, GPS validation, SQL, transactions and review rules run normally.
"""
import os
import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from db import get_connection
import compensation
from operations import current_user


class BorrowedConnection:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        return self.conn.cursor()

    def commit(self):
        pass  # Keep endpoint writes inside the outer test transaction.

    def close(self):
        pass


@unittest.skipUnless(os.getenv("KIARAD_TEST_VISIT_WORKFLOW_DB") == "1", "Opt-in PostgreSQL test")
class VisitCheckinWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.cur = self.conn.cursor()
        self.addCleanup(self.cur.close)
        statements = [
            "CREATE TEMP TABLE salespersons (id INTEGER PRIMARY KEY,name TEXT)",
            "CREATE TEMP TABLE users (id INTEGER PRIMARY KEY,full_name TEXT)",
            """CREATE TEMP TABLE base_checkins (id SERIAL PRIMARY KEY,salesperson_id INTEGER REFERENCES salespersons(id),
                base_source TEXT,base_id INTEGER,latitude DOUBLE PRECISION,longitude DOUBLE PRECISION,
                accuracy_m DOUBLE PRECISION,distance_m DOUBLE PRECISION,status VARCHAR(24),note TEXT,
                checked_in_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'))""",
            "CREATE TEMP TABLE payroll_approvals (salesperson_id INTEGER,payroll_month TEXT,status TEXT)",
            """CREATE TEMP TABLE salesperson_locations (salesperson_id INTEGER,latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,activity TEXT,accuracy DOUBLE PRECISION,battery_level INTEGER,recorded_at TIMESTAMP)""",
            """CREATE TEMP TABLE visit_route_assignments (id SERIAL PRIMARY KEY,user_id INTEGER,salesperson_id INTEGER,
                base_source TEXT,base_id INTEGER,visit_date DATE,stop_order INTEGER,note TEXT,assigned_at TIMESTAMP)""",
        ]
        for table in sorted(compensation.BASE_TABLES):
            statements.append(f"CREATE TEMP TABLE {table} (id INTEGER PRIMARY KEY,name TEXT,city TEXT,address TEXT,latitude DOUBLE PRECISION,longitude DOUBLE PRECISION,visit_radius_m INTEGER)")
        for statement in statements:
            self.cur.execute(statement)
        compensation._ensure_checkin_review_schema(self.cur, temporary=True)
        compensation._ensure_checkin_submission_schema(self.cur,temporary=True)
        compensation._ensure_checkin_review_schema(self.cur, temporary=True)
        self.cur.execute("INSERT INTO salespersons VALUES (10,'پرسنل اول'),(11,'پرسنل دوم')")
        self.cur.execute("INSERT INTO users VALUES (1,'مدیر آزمون'),(2,'پرسنل اول'),(3,'پرسنل دوم')")
        self.cur.execute("""INSERT INTO pharmacies VALUES
            (1,'مرجع','کرمان','نشانی',30,57,150),(2,'فاقد مرجع','کرمان','نشانی',NULL,NULL,150)""")
        self.user = {"id":2,"role":"visitor","salesperson_id":10}
        app = FastAPI()
        app.include_router(compensation.router)
        app.dependency_overrides[current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        patcher = patch.object(compensation,"get_connection",return_value=BorrowedConnection(self.conn))
        patcher.start()
        self.addCleanup(patcher.stop)

    def checkin(self, **changes):
        data = {"source":"pharmacies","base_id":1,"lat":30,"lng":57,"accuracy_m":0.7,"note":"نتیجهٔ ملاقات ثبت شد"}
        data.update(changes)
        return self.client.post("/api/compensation/base-checkins",json=data)

    def manager(self):
        self.user = {"id":1,"role":"ceo","salesperson_id":None}

    def test_precise_checkin_is_verified_and_employee_scope_is_enforced(self):
        response = self.checkin(salesperson_id=11)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["status"],"verified")
        self.assertEqual(response.json()["distance_m"],0)
        rows = self.client.get("/api/compensation/base-checkins?salesperson_id=11").json()["items"]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["salesperson_id"],10)
        self.assertIn("ملاقات",rows[0]["note"])
        self.user = {"id":3,"role":"salesperson","salesperson_id":11}
        self.assertEqual(self.client.get("/api/compensation/base-checkins?salesperson_id=10").json()["items"],[])
        self.manager()
        self.assertEqual(len(self.client.get("/api/compensation/base-checkins").json()["items"]),1)

    def test_lost_response_retry_returns_original_without_second_location_or_visit(self):
        key=str(uuid4())
        first=self.checkin(submission_key=key)
        self.assertEqual(first.status_code,200,first.text)
        second=self.checkin(submission_key=key)
        self.assertTrue(second.json()['already_saved'])
        self.assertEqual(first.json()['checkin_id'],second.json()['checkin_id'])
        for table in ('base_checkins','salesperson_locations','base_checkin_submissions'):
            self.cur.execute('SELECT COUNT(*) FROM '+table)
            self.assertEqual(self.cur.fetchone()[0],1)
        self.assertEqual(self.checkin(submission_key=key,note='گزارش تغییر داده شده').status_code,409)

    def test_invalid_submission_key_is_rejected_and_new_key_allows_distinct_visit(self):
        self.assertEqual(self.checkin(submission_key='invalid').status_code,422)
        self.assertEqual(self.checkin(submission_key=str(uuid4())).status_code,200)
        self.assertEqual(self.checkin(submission_key=str(uuid4())).status_code,200)
        self.cur.execute('SELECT COUNT(*) FROM base_checkins')
        self.assertEqual(self.cur.fetchone()[0],2)

    def test_inaccurate_missing_reference_and_outside_location_need_review(self):
        for data,expected in (({"accuracy_m":None},"pending_review"),({"accuracy_m":200},"pending_review"),
                              ({"base_id":2},"pending_review"),({"lat":31},"outside_radius")):
            response=self.checkin(**data)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()["status"],expected)

    def test_one_meter_acceptance_is_strict_and_does_not_rewrite_device_precision(self):
        self.assertEqual(compensation.MAX_AUTOMATIC_ACCURACY_M,1)
        for measured,expected in ((0.7,'verified'),(1,'verified'),(1.000001,'pending_review'),(20,'pending_review'),(107,'pending_review')):
            with self.subTest(measured=measured):
                result=self.checkin(accuracy_m=measured)
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.json()['status'],expected)
                self.cur.execute('SELECT accuracy_m FROM base_checkins WHERE id=%s',(result.json()['checkin_id'],))
                self.assertEqual(self.cur.fetchone()[0],measured)

    def test_manager_approval_preserves_original_measurements_and_rejects_repeat(self):
        checkin_id=self.checkin(lat=31).json()["checkin_id"]
        self.assertEqual(self.client.post(f"/api/compensation/base-checkins/{checkin_id}/review",json={"decision":"verified","note":"بررسی"}).status_code,403)
        self.manager()
        self.assertEqual(self.client.post(f"/api/compensation/base-checkins/{checkin_id}/review",json={"decision":"verified"}).status_code,422)
        response=self.client.post(f"/api/compensation/base-checkins/{checkin_id}/review",json={"decision":"verified","note":"مراجعه تلفنی تأیید شد"})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.post(f"/api/compensation/base-checkins/{checkin_id}/review",json={"decision":"rejected","note":"مجدد"}).status_code,409)
        row=self.client.get("/api/compensation/base-checkins?status=verified").json()["items"][0]
        self.assertEqual(row["original_status"],"outside_radius")
        self.assertEqual(row["reviewer_name"],"مدیر آزمون")
        self.assertGreater(row["distance_m"],150)
        self.cur.execute("SELECT COUNT(DISTINCT checked_in_at::date) FROM base_checkins WHERE salesperson_id=10 AND status='verified'")
        self.assertEqual(self.cur.fetchone()[0],1)

    def test_manager_rejection_does_not_count_as_verified_attendance(self):
        checkin_id=self.checkin(base_id=2).json()["checkin_id"]
        self.manager()
        result=self.client.post(f"/api/compensation/base-checkins/{checkin_id}/review",json={"decision":"rejected","note":"مدرک کافی نیست"})
        self.assertEqual(result.json()["status"],"rejected")
        self.cur.execute("SELECT COUNT(*) FROM base_checkins WHERE status='verified'")
        self.assertEqual(self.cur.fetchone()[0],0)

    def test_approved_payroll_prevents_retroactive_review_or_new_checkins(self):
        checkin_id=self.checkin(base_id=2).json()["checkin_id"]
        self.cur.execute("INSERT INTO payroll_approvals VALUES (10,TO_CHAR(NOW() AT TIME ZONE 'Asia/Tehran','YYYY-MM'),'approved')")
        self.assertEqual(self.checkin().status_code,409)
        self.manager()
        result=self.client.post(f"/api/compensation/base-checkins/{checkin_id}/review",json={"decision":"verified","note":"تأیید"})
        self.assertEqual(result.status_code,409)
        self.cur.execute("SELECT COUNT(*) FROM base_checkin_reviews")
        self.assertEqual(self.cur.fetchone()[0],0)

    def test_invalid_coordinates_accuracy_and_reports_are_rejected(self):
        for data in ({"lat":91},{"lng":181},{"lat":"NaN"},{"lng":"Infinity"},
                     {"accuracy_m":-1},{"accuracy_m":"NaN"},{"note":" "},{"note":"x"*2001}):
            self.assertEqual(self.checkin(**data).status_code,422)
        self.assertEqual(self.checkin(base_id=999).status_code,404)
        self.assertEqual(self.checkin(source="unknown").status_code,422)
        self.assertEqual(self.client.get("/api/compensation/base-checkins?status=unknown").status_code,422)
        self.assertEqual(self.client.get("/api/compensation/base-checkins?limit=201").status_code,422)

    def test_self_review_missing_record_and_auto_verified_review_are_denied(self):
        checkin_id=self.checkin(base_id=2).json()["checkin_id"]
        verified_id=self.checkin().json()["checkin_id"]
        self.user={"id":2,"role":"sales_manager","salesperson_id":10}
        self.assertEqual(self.client.post(f"/api/compensation/base-checkins/{checkin_id}/review",json={"decision":"verified","note":"خودم"}).status_code,403)
        self.manager()
        self.assertEqual(self.client.post("/api/compensation/base-checkins/999/review",json={"decision":"verified","note":"بررسی"}).status_code,404)
        self.assertEqual(self.client.post(f"/api/compensation/base-checkins/{verified_id}/review",json={"decision":"rejected","note":"بررسی"}).status_code,409)

    def test_route_keeps_valid_checkin_when_later_attempt_is_pending(self):
        valid_id=self.checkin().json()["checkin_id"]
        self.checkin(accuracy_m=None)
        self.cur.execute("""INSERT INTO visit_route_assignments
            (user_id,salesperson_id,base_source,base_id,visit_date,stop_order)
            VALUES (2,10,'pharmacies',1,(NOW() AT TIME ZONE 'Asia/Tehran')::date,1)""")
        result=self.client.get("/api/compensation/visit-routes").json()["items"]
        self.assertEqual(result[0]["checkin_id"],valid_id)
        self.assertEqual(result[0]["checkin_status"],"verified")


if __name__ == "__main__":
    unittest.main()
