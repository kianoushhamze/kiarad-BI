"""Proposal -> approved local base -> assigned staff route, using TEMP SQL only.

Opt in with KIARAD_TEST_BASE_ROUTE_DB=1. All module SQL shares one isolated
transaction and pg_temp search path. Holoo/network writes are forbidden.
Authentication is dependency-overridden; actual role and ownership checks run.
"""

from contextlib import contextmanager, nullcontext
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import base_proposals as proposals
import compensation


@unittest.skipUnless(os.getenv("KIARAD_TEST_BASE_ROUTE_DB") == "1", "Opt-in temporary database test")
class BaseRouteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.conn = proposals.engine.connect()
        self.addCleanup(self.conn.close)
        transaction = self.conn.begin()
        self.addCleanup(transaction.rollback)
        self.conn.execute(text("SET LOCAL search_path TO pg_temp"))
        self.conn.execute(text("SET LOCAL statement_timeout='10s'"))
        self.conn.execute(text("SET LOCAL lock_timeout='3s'"))
        statements = [
            "CREATE TEMP TABLE salespersons(id INTEGER PRIMARY KEY,name TEXT)",
            """CREATE TEMP TABLE users(id INTEGER PRIMARY KEY,full_name TEXT,
                salesperson_id INTEGER REFERENCES salespersons(id),is_active BOOLEAN)""",
            "INSERT INTO salespersons VALUES(10,'پرسنل موقت اول'),(11,'پرسنل موقت دوم')",
            "INSERT INTO users VALUES(1,'مدیر موقت',NULL,TRUE),(2,'پرسنل اول',10,TRUE),(3,'پرسنل دوم',11,TRUE),(4,'غیرفعال',10,FALSE)",
            """CREATE TEMP TABLE visit_route_assignments(id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),salesperson_id INTEGER REFERENCES salespersons(id),
                base_source TEXT,base_id INTEGER,visit_date DATE,stop_order INTEGER,note TEXT,
                assigned_by INTEGER REFERENCES users(id),assigned_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id,base_source,base_id,visit_date))""",
            """CREATE TEMP TABLE base_checkins(id SERIAL PRIMARY KEY,salesperson_id INTEGER,
                base_source TEXT,base_id INTEGER,checked_in_at TIMESTAMP,status TEXT,distance_m NUMERIC)""",
        ]
        for table in proposals.BASE_TABLES:
            statements.append(f"""CREATE TEMP TABLE {table}(id SERIAL PRIMARY KEY,name TEXT NOT NULL,
                city TEXT,address TEXT,phone TEXT,type TEXT,latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,visit_radius_m INTEGER)""")
        for statement in statements:
            self.conn.execute(text(statement))
        proposals.ensure_proposals(self.conn, temporary=True)

        @contextmanager
        def begin():
            with self.conn.begin_nested():
                yield self.conn

        borrowed_engine = SimpleNamespace(begin=begin, connect=lambda: nullcontext(self.conn))
        raw_connection = self.conn.connection.driver_connection
        borrowed_dbapi = SimpleNamespace(cursor=raw_connection.cursor, commit=lambda: None,
                                         rollback=lambda: None, close=lambda: None)
        for patcher in (
            patch.object(proposals, "engine", borrowed_engine),
            patch.object(compensation, "get_connection", return_value=borrowed_dbapi),
            patch("requests.sessions.Session.request", side_effect=AssertionError("No external service calls allowed")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.staff()
        app = FastAPI()
        app.include_router(proposals.router)
        app.include_router(compensation.router)
        app.dependency_overrides[proposals.current_user] = lambda: self.user
        app.dependency_overrides[compensation.current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.visit_date = "2026-10-18"

    def staff(self, second=False):
        self.user = {"id": 3 if second else 2, "role": "salesperson", "salesperson_id": 11 if second else 10}

    def manager(self):
        self.user = {"id": 1, "role": "ceo", "salesperson_id": None}

    def submit(self, **changes):
        payload = {"submission_key": str(uuid4()), "name": "پایگاه آزمایشی زنجیره مسیر",
                   "city": "کرمان", "address": "نشانی آزمایشی بدون ثبت واقعی",
                   "category": "pharmacy", "latitude": 30.2, "longitude": 57.1,
                   "accuracy_m": 20, "note": "مراجعه و معرفی آزمایشی در جدول موقت"}
        payload.update(changes)
        return self.client.post("/api/compensation/base-proposals", json=payload)

    def review(self, proposal_id, decision="approved"):
        return self.client.post(f"/api/compensation/base-proposals/{proposal_id}/review",
                                json={"decision": decision, "note": "بررسی مستقل مشخصات پایگاه آزمایشی"})

    def assign(self, base_id, **changes):
        payload = {"user_id": 2, "source": "kerman_bases_manual", "base_id": base_id,
                   "visit_date": self.visit_date, "stop_order": 1, "note": "مسیر آزمایشی شخص اول"}
        payload.update(changes)
        return self.client.post("/api/compensation/visit-routes", json=payload)

    def count(self, table):
        self.assertIn(table, {"base_proposals", "kerman_bases_manual", "visit_route_assignments"})
        return self.conn.execute(text("SELECT COUNT(*) FROM " + table)).scalar()

    def approved_base(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.text)
        proposal_id = response.json()["id"]
        self.manager()
        approved = self.review(proposal_id)
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertFalse(approved.json()["holoo_sent"])
        return proposal_id, approved.json()["base_id"]

    def test_staff_proposal_manager_approval_base_list_and_private_assigned_route(self):
        submitted = self.submit(salesperson_id=11)
        self.assertEqual(submitted.status_code, 201, submitted.text)
        self.assertFalse(submitted.json()["holoo_sent"])
        proposal_id = submitted.json()["id"]
        self.assertEqual(self.client.get("/api/compensation/bases").json()["items"], [])
        self.assertEqual(self.count("kerman_bases_manual"), 0)
        self.manager()
        approved = self.review(proposal_id)
        self.assertEqual(approved.status_code, 200, approved.text)
        base_id = approved.json()["base_id"]
        self.assertFalse(approved.json()["holoo_sent"])
        self.staff()
        bases = self.client.get("/api/compensation/bases").json()["items"]
        self.assertEqual(len(bases), 1)
        self.assertEqual((bases[0]["source"], bases[0]["id"]), ("kerman_bases_manual", base_id))
        self.assertTrue(bases[0]["location_configured"])
        self.manager()
        assigned = self.assign(base_id)
        self.assertEqual(assigned.status_code, 200, assigned.text)
        route_id = assigned.json()["id"]
        self.staff()
        own = self.client.get(f"/api/compensation/visit-routes?visit_date={self.visit_date}&user_id=3")
        self.assertEqual(own.status_code, 200, own.text)
        route = own.json()["items"][0]
        self.assertEqual((route["id"], route["user_id"], route["salesperson_id"], route["base_id"]),
                         (route_id, 2, 10, base_id))
        self.assertEqual(route["base_name"], bases[0]["name"])
        self.assertEqual(route["address"], bases[0]["address"])
        self.staff(second=True)
        self.assertEqual(self.client.get(f"/api/compensation/visit-routes?user_id=2&visit_date={self.visit_date}").json()["items"], [])
        self.assertEqual(self.client.get("/api/compensation/base-proposals").json()["items"], [])
        self.manager()
        self.assertEqual(len(self.client.get("/api/compensation/visit-routes?user_id=2").json()["items"]), 1)
        self.assertEqual(self.client.get("/api/compensation/visit-routes?user_id=3").json()["items"], [])
        row = self.conn.execute(text("SELECT salesperson_id,status,holoo_status FROM base_proposals WHERE id=:id"), {"id": proposal_id}).one()
        self.assertEqual(tuple(row), (10, "approved", "awaiting_connector"))
        self.assertTrue(all(row[0] == "t" for row in self.conn.execute(text("SELECT relpersistence FROM pg_class WHERE relnamespace=pg_my_temp_schema() AND relkind='r'"))))

    def test_retries_duplicates_and_route_update_are_safe_and_staff_cannot_escalate(self):
        key = str(uuid4())
        first = self.submit(submission_key=key)
        self.assertEqual(first.status_code, 201, first.text)
        replayed = self.submit(submission_key=key)
        self.assertTrue(replayed.json()["replayed"])
        self.assertEqual(replayed.json()["id"], first.json()["id"])
        self.assertEqual(self.submit(submission_key=key, note="گزارش متفاوت با کلید قبلی").status_code, 409)
        self.assertEqual(self.review(first.json()["id"]).status_code, 403)
        self.assertEqual(self.assign(1).status_code, 403)
        self.manager()
        approved = self.review(first.json()["id"])
        self.assertEqual(approved.status_code, 200, approved.text)
        base_id = approved.json()["base_id"]
        self.assertEqual(self.review(first.json()["id"]).status_code, 409)
        initial = self.assign(base_id)
        updated = self.assign(base_id, stop_order=3, note="ترتیب جدید همان ایستگاه")
        self.assertEqual((initial.status_code, updated.status_code), (200, 200))
        self.assertEqual(initial.json()["id"], updated.json()["id"])
        self.assertEqual(self.count("visit_route_assignments"), 1)
        self.staff(second=True)
        self.assertEqual(self.client.delete(f"/api/compensation/visit-routes/{initial.json()['id']}").status_code, 403)
        duplicate = self.submit()
        self.assertEqual(duplicate.status_code, 201, duplicate.text)
        self.manager()
        self.assertEqual(self.review(duplicate.json()["id"]).status_code, 409)
        self.assertEqual(self.count("kerman_bases_manual"), 1)
        self.staff()
        route = self.client.get("/api/compensation/visit-routes").json()["items"][0]
        self.assertEqual((route["stop_order"], route["note"]), (3, "ترتیب جدید همان ایستگاه"))

    def test_rejected_proposal_has_no_routeable_base_and_invalid_target_is_rejected(self):
        pending = self.submit().json()["id"]
        self.manager()
        rejected = self.review(pending, "rejected")
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertIsNone(rejected.json()["base_id"])
        self.assertFalse(rejected.json()["holoo_sent"])
        self.assertEqual(self.count("kerman_bases_manual"), 0)
        self.assertEqual(self.assign(999).status_code, 404)
        self.staff()
        _, base_id = self.approved_base()
        self.assertEqual(self.assign(base_id, user_id=4).status_code, 422)
        self.assertEqual(self.assign(base_id, user_id=1).status_code, 422)
        self.assertEqual(self.assign(base_id, source="users").status_code, 422)
        self.assertEqual(self.count("visit_route_assignments"), 0)


if __name__ == "__main__":
    unittest.main()
