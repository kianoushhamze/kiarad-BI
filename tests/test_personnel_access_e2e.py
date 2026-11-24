"""JWT, permission gate and SQL ownership checks on rollback-only TEMP tables.

Opt in with KIARAD_TEST_PERSONNEL_E2E_DB=1. No authentication dependency is
overridden, no production table is visible, and attachments use a temp folder.
"""
import os
import tempfile
import unittest
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import text

import api
import compensation
import operations as ops


@unittest.skipUnless(os.getenv("KIARAD_TEST_PERSONNEL_E2E_DB") == "1", "Opt-in temporary database test")
class PersonnelAccessE2ETests(unittest.TestCase):
    def setUp(self):
        self.conn = ops.engine.connect()
        self.addCleanup(self.conn.close)
        tx = self.conn.begin()
        self.addCleanup(tx.rollback)
        self.conn.execute(text("SET LOCAL search_path TO pg_temp"))
        self.conn.execute(text("SET LOCAL statement_timeout='10s'"))
        for statement in (
            "CREATE TEMP TABLE salespersons(id INTEGER PRIMARY KEY,name TEXT)",
            """CREATE TEMP TABLE users(id SERIAL PRIMARY KEY,username TEXT UNIQUE,full_name TEXT,
                role TEXT,salesperson_id INTEGER,is_active INTEGER,password_hash TEXT,
                password_version INTEGER DEFAULT 0,created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TEMP TABLE role_permissions(role TEXT,module TEXT,can_read BOOLEAN,
                can_write BOOLEAN,can_delete BOOLEAN)""",
            "CREATE TEMP TABLE customers(id INTEGER PRIMARY KEY,name TEXT)",
            "INSERT INTO customers VALUES (101,'مشتری اول'),(102,'مشتری دوم')",
            """CREATE TEMP TABLE customer_interactions(id SERIAL PRIMARY KEY,customer_name TEXT,
                visitor_name TEXT,interaction_type TEXT,product_discussed TEXT,notes TEXT,
                next_followup_date DATE,followup_time TEXT,status TEXT DEFAULT 'در انتظار تماس',
                created_at TIMESTAMP DEFAULT NOW())""",
            """CREATE TEMP TABLE chat_messages(id SERIAL PRIMARY KEY,sender TEXT,message TEXT,
                room TEXT DEFAULT 'general',created_at TIMESTAMP DEFAULT NOW(),attachment_key TEXT,
                attachment_name TEXT,attachment_type TEXT,attachment_size BIGINT)""",
            """CREATE TEMP TABLE daily_reports(id SERIAL PRIMARY KEY,salesperson_id INTEGER,
                report_date DATE,visits_count INTEGER,new_customers_count INTEGER,orders_count INTEGER,
                lost_orders_count INTEGER,reported_sales_amount NUMERIC,reported_collections_amount NUMERIC,
                loss_reasons TEXT,competitor_notes TEXT,demand_notes TEXT,issues TEXT,tomorrow_plan TEXT,
                notes TEXT,created_at TIMESTAMP)""",
            """CREATE TEMP TABLE salesperson_contracts(id INTEGER PRIMARY KEY,salesperson_id INTEGER,
                hourly_rate NUMERIC,min_monthly_hours NUMERIC,settlement_commission_percent NUMERIC,
                daily_mission_allowance NUMERIC,per_km_rate NUMERIC)""",
            """CREATE TEMP TABLE salesperson_targets(contract_id INTEGER,target_type TEXT,
                item_identifier TEXT,item_title TEXT,target_amount NUMERIC,target_quantity INTEGER,
                commission_percent NUMERIC)""",
            "INSERT INTO salespersons VALUES (10,'پرسنل اول'),(11,'پرسنل دوم'),(12,'پرسنل سوم')",
            "INSERT INTO salesperson_contracts VALUES(1,10,100,160,1,10,5)",
        ):
            self.conn.execute(text(statement))
        self.password = "temporary test credential"
        password_hash = ops.hash_password(self.password)
        self.conn.execute(text("""
            INSERT INTO users(username,full_name,role,salesperson_id,is_active,password_hash)
            VALUES ('chief','مدیر آزمون','ceo',NULL,1,:hash),
                   ('alice','نام مشترک','salesperson',10,1,:hash),
                   ('bob','نام مشترک','salesperson',11,1,:hash),
                   ('charlie','@alice','salesperson',12,1,:hash)
        """), {"hash": password_hash})
        api._ensure_crm_table(self.conn)

        @contextmanager
        def begin():
            with self.conn.begin_nested():
                yield self.conn

        borrowed = SimpleNamespace(begin=begin, connect=lambda: nullcontext(self.conn))
        borrowed_dbapi = SimpleNamespace(cursor=self.conn.connection.driver_connection.cursor,
                                        close=lambda: None, commit=lambda: None)
        self.secret = "isolated-personnel-test-signing-secret-123456"
        for patcher in (
            patch.object(api, "engine", borrowed),
            patch.object(ops, "engine", borrowed),
            patch.object(compensation, "get_connection", return_value=borrowed_dbapi),
            patch.object(ops, "JWT_SECRET", self.secret),
            patch.dict(os.environ, {"KIARAD_JWT_SECRET": self.secret, "KIARAD_API_KEY": "test-only-api-key"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        temp_dir = tempfile.TemporaryDirectory(prefix="kiarad-personnel-")
        self.addCleanup(temp_dir.cleanup)
        self.upload_dir = Path(temp_dir.name)
        uploads = patch.object(api, "_CHAT_UPLOAD_DIR", self.upload_dir)
        uploads.start()
        self.addCleanup(uploads.stop)
        self.client = TestClient(api.app)
        self.addCleanup(self.client.close)

    def login(self, username="alice", password=None):
        response = self.client.post("/auth/login", json={
            "username": username, "password": self.password if password is None else password,
        })
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertNotIn("password_hash", result["user"])
        return {"Authorization": "Bearer " + result["access_token"]}

    def row(self, user_id):
        return dict(self.conn.execute(text("SELECT * FROM users WHERE id=:id"), {"id": user_id}).mappings().one())

    def post_crm(self, headers, **extra):
        data = {"customer_name": "مشتری آزمایشی", "notes": "یادداشت موقت"}
        data.update(extra)
        return self.client.post("/crm/interactions", headers=headers, json=data)

    def test_login_identity_and_non_secret_account_metadata(self):
        for username, user_id, profile_id in (("alice", 2, 10), ("bob", 3, 11), ("charlie", 4, 12)):
            response = self.client.get("/auth/me", headers=self.login(username))
            self.assertEqual(response.status_code, 200)
            self.assertEqual((response.json()["id"], response.json()["salesperson_id"]), (user_id, profile_id))
            self.assertNotIn("password_hash", response.json())
        for path in ("/auth/me", "/users", "/chat/messages", "/crm/interactions", "/daily-reports"):
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_self_password_ignores_other_identity_and_revokes_old_session(self):
        headers = self.login()
        bob_before = self.row(3)
        wrong = self.client.post("/auth/password", headers=headers, json={
            "current_password": "incorrect", "new_password": "replacement temporary password",
        })
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 200)
        response = self.client.post("/auth/password", headers=headers, json={
            "current_password": self.password, "new_password": "replacement temporary password",
            "user_id": 3, "salesperson_id": 11, "role": "ceo",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], 2)
        self.assertEqual(response.json()["user"]["role"], "salesperson")
        self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 401)
        fresh = {"Authorization": "Bearer " + response.json()["access_token"]}
        self.assertEqual(self.client.get("/auth/me", headers=fresh).status_code, 200)
        self.assertEqual(self.row(3), bob_before)
        self.assertTrue(ops.verify_password("replacement temporary password", self.row(2)["password_hash"]))
        self.assertEqual(self.client.post("/auth/login", json={"username": "alice", "password": self.password}).status_code, 401)
        self.login(password="replacement temporary password")

    def test_staff_cannot_mutate_peers_or_elevate_signed_role_claim(self):
        user = self.row(2)
        now = datetime.now(timezone.utc)
        token = jwt.encode({"sub": "2", "role": "ceo", "pwd_ver": user["password_version"],
                            "iat": now, "exp": now + timedelta(minutes=5)}, self.secret, algorithm="HS256")
        before = [self.row(2), self.row(3)]
        for headers in (self.login(), {"Authorization": "Bearer " + token}):
            for method, path, payload in (
                ("POST", "/users", {"username": "intruder", "full_name": "حساب غیرمجاز", "role": "ceo", "password": self.password}),
                ("PATCH", "/users/3", {"role": "ceo", "is_active": 0}),
                ("POST", "/users/3/password", {"password": "unauthorized replacement"}),
                ("DELETE", "/users/3", None),
            ):
                self.assertEqual(self.client.request(method, path, headers=headers, json=payload).status_code, 403)
            self.assertEqual(self.client.get("/users", headers=headers).status_code, 403)
        self.assertEqual([self.row(2), self.row(3)], before)
        self.assertEqual(self.conn.execute(text("SELECT COUNT(*) FROM users")).scalar(), 4)

    def test_manager_reset_and_deactivation_invalidate_all_existing_sessions(self):
        chief = self.login("chief")
        old = self.login()
        reset = self.client.post("/users/2/password", headers=chief, json={"password": "manager reset temporary password"})
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(self.client.get("/auth/me", headers=old).status_code, 401)
        current = self.login(password="manager reset temporary password")
        self.assertEqual(self.client.patch("/users/2", headers=chief, json={"is_active": 0}).status_code, 200)
        self.assertEqual(self.client.get("/auth/me", headers=current).status_code, 401)
        self.assertEqual(self.client.post("/auth/login", json={"username": "alice", "password": "manager reset temporary password"}).status_code, 401)
        self.assertEqual(self.client.patch("/users/2", headers=chief, json={"is_active": 1}).status_code, 200)
        self.assertEqual(self.client.get("/auth/me", headers=current).status_code, 401)
        self.login(password="manager reset temporary password")

    def test_profile_reassignment_requires_fresh_login(self):
        chief, old = self.login("chief"), self.login()
        self.assertEqual(self.client.patch("/users/2", headers=chief, json={"salesperson_id": 12}).status_code, 200)
        self.assertEqual(self.client.get("/auth/me", headers=old).status_code, 401)
        response = self.client.get("/auth/me", headers=self.login())
        self.assertEqual(response.json()["salesperson_id"], 12)
        self.assertEqual(self.row(3)["salesperson_id"], 11)

    def test_crm_ownership_survives_duplicate_names_and_rename(self):
        alice, bob, charlie = self.login(), self.login("bob"), self.login("charlie")
        self.assertEqual(self.post_crm(alice, visitor_name="@bob", owner_user_id=3).status_code, 200)
        item = self.client.get("/crm/interactions", headers=alice).json()[0]
        self.assertEqual(self.client.get("/crm/interactions", headers=bob).json(), [])
        self.assertEqual(self.client.get("/crm/interactions", headers=charlie).json(), [])
        for other in (bob, charlie):
            self.assertEqual(self.client.patch(f"/crm/interactions/{item['id']}/status", headers=other,
                                              json={"status": "پیگیری شد"}).status_code, 403)
        self.conn.execute(text("UPDATE users SET full_name='نام تازه' WHERE id=2"))
        self.assertEqual([row["id"] for row in self.client.get("/crm/interactions", headers=alice).json()], [item["id"]])
        self.assertEqual(self.client.patch(f"/crm/interactions/{item['id']}/status", headers=alice,
                                          json={"status": "پیگیری شد"}).status_code, 200)
        self.assertEqual(self.conn.execute(text("SELECT owner_user_id FROM customer_interactions")).scalar(), 2)

    def test_customer_card_is_scoped_and_can_be_archived(self):
        alice, bob, chief = self.login(), self.login("bob"), self.login("chief")
        self.assertEqual(self.post_crm(alice, customer_id=101).status_code, 200)
        cards = self.client.get("/crm/interactions?customer_id=101", headers=alice).json()
        self.assertEqual([card["customer_name"] for card in cards], ["مشتری اول"])
        self.assertEqual(self.client.get("/crm/interactions?customer_id=102", headers=alice).json(), [])
        path = f"/crm/interactions/{cards[0]['id']}"
        self.assertEqual(self.client.patch(path, headers=bob, json={"notes": "ignored"}).status_code, 403)
        self.assertEqual(self.client.patch(path, headers=alice, json={"notes": "updated"}).status_code, 200)
        self.assertEqual(self.client.delete(path, headers=chief).status_code, 200)
        self.assertEqual(self.client.get("/crm/interactions?customer_id=101", headers=alice).json(), [])
        self.assertEqual(self.conn.execute(text("SELECT notes FROM customer_interactions")).scalar(), "updated")

    def test_legacy_crm_owner_migration_is_unambiguous_and_runs_once(self):
        self.conn.execute(text("ALTER TABLE customer_interactions DROP COLUMN owner_user_id"))
        self.conn.execute(text("""INSERT INTO customer_interactions(customer_name,visitor_name)
            VALUES ('موقت اول','@alice'),('موقت دوم','نام مشترک'),('موقت سوم','ناشناخته')"""))
        api._ensure_crm_table(self.conn)
        owners = self.conn.execute(text("SELECT owner_user_id FROM customer_interactions ORDER BY id")).scalars().all()
        self.assertEqual(owners, [2, None, None])
        self.conn.execute(text("UPDATE users SET full_name='ناشناخته' WHERE id=3"))
        api._ensure_crm_table(self.conn)
        self.assertEqual(self.conn.execute(text("SELECT owner_user_id FROM customer_interactions ORDER BY id")).scalars().all(), owners)
        self.assertEqual(len(self.client.get("/crm/interactions", headers=self.login()).json()), 1)
        self.assertEqual(self.client.get("/crm/interactions", headers=self.login("bob")).json(), [])
        self.assertEqual(len(self.client.get("/crm/interactions", headers=self.login("chief")).json()), 3)

    def test_manager_can_assign_crm_by_unique_username(self):
        chief = self.login("chief")
        self.assertEqual(self.post_crm(chief, visitor_name="نام مشترک").status_code, 422)
        self.assertEqual(self.post_crm(chief, visitor_name="@bob").status_code, 200)
        self.assertEqual(self.client.get("/crm/interactions", headers=self.login()).json(), [])
        self.assertEqual(len(self.client.get("/crm/interactions", headers=self.login("bob")).json()), 1)

    def test_daily_reports_cannot_be_assigned_to_peer_or_read_cross_user(self):
        for username, profile_id in (("alice", 10), ("bob", 11)):
            headers = self.login(username)
            response = self.client.post("/daily-reports", headers=headers, json={
                "report_date": "2020-01-01", "salesperson_id": 12, "visits_count": 1,
            })
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["salesperson_id"], profile_id)
        for username, profile_id in (("alice", 10), ("bob", 11)):
            rows = self.client.get("/daily-reports?salesperson_id=12", headers=self.login(username)).json()["reports"]
            self.assertEqual([row["salesperson_id"] for row in rows], [profile_id])
        all_reports = self.client.get("/daily-reports", headers=self.login("chief")).json()["reports"]
        self.assertEqual(len(all_reports), 2)

    def test_staff_reads_own_contract_but_cannot_read_peer_or_write_contracts(self):
        for username, own_id, peer_id in (("alice", 10, 11), ("bob", 11, 10)):
            headers = self.login(username)
            own = self.client.get(f"/api/compensation/contract/{own_id}", headers=headers)
            self.assertEqual(own.status_code, 200)
            self.assertEqual(own.json()["salesperson_id"], own_id)
            self.assertEqual(own.json()["configured"], username == "alice")
            self.assertEqual(self.client.get(f"/api/compensation/contract/{peer_id}", headers=headers).status_code, 403)
            for profile_id in (own_id, peer_id):
                response = self.client.post(f"/api/compensation/contract/{profile_id}", headers=headers,
                                            json={"hourly_rate": 100, "targets": []})
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.conn.execute(text("SELECT COUNT(*) FROM salesperson_contracts")).scalar(), 1)

    def test_shared_chat_uses_authenticated_sender_and_protected_attachments(self):
        alice, bob = self.login(), self.login("bob")
        first = self.client.post("/chat/send", headers=alice, json={
            "message": "پیام موقت", "sender": "مدیر جعلی", "user_id": 1,
        })
        self.assertEqual(first.status_code, 200)
        content = b"%PDF-1.4\nTemporary attachment\n%%EOF"
        second = self.client.post("/chat/send", headers=bob, data={"message": "پیوست موقت"},
                                  files={"file": ("../example.pdf", content, "application/pdf")})
        self.assertEqual(second.status_code, 200)
        messages = self.client.get("/chat/messages", headers=alice).json()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["sender"], "نام مشترک")
        self.assertNotIn("attachment_key", messages[1])
        path = f"/chat/attachments/{second.json()['id']}"
        self.assertEqual(self.client.get(path).status_code, 401)
        download = self.client.get(path, headers=alice)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, content)
        self.assertEqual(len(list(self.upload_dir.iterdir())), 1)
        self.conn.execute(text("INSERT INTO role_permissions VALUES ('salesperson','__configured__',FALSE,FALSE,FALSE)"))
        for forbidden in ("/chat/messages", path):
            self.assertEqual(self.client.get(forbidden, headers=alice).status_code, 403)
        self.assertEqual(self.client.post("/chat/send", headers=bob, json={"message": "نباید ذخیره شود"}).status_code, 403)
        self.assertEqual(self.conn.execute(text("SELECT COUNT(*) FROM chat_messages")).scalar(), 2)
        self.assertEqual(self.client.get("/auth/me", headers=alice).status_code, 200)

    def test_invalid_chat_attachment_and_room_do_not_create_rows_or_files(self):
        headers = self.login()
        for response in (
            self.client.post("/chat/send", headers=headers, json={"message": "متن", "room": "private"}),
            self.client.post("/chat/send", headers=headers, files={"file": ("fake.pdf", b"plain text", "application/pdf")}),
            self.client.post("/chat/send", headers=headers, files={"file": ("unsafe.exe", b"MZ", "application/octet-stream")}),
        ):
            self.assertIn(response.status_code, (400, 415))
        self.assertEqual(self.conn.execute(text("SELECT COUNT(*) FROM chat_messages")).scalar(), 0)
        self.assertEqual(list(self.upload_dir.iterdir()), [])

    def test_api_key_alone_cannot_change_any_account_password(self):
        before = self.row(2)
        response = self.client.post("/auth/password", headers={"X-API-Key": "test-only-api-key"}, json={
            "current_password": self.password, "new_password": "another temporary credential",
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.row(2), before)


if __name__ == "__main__":
    unittest.main()
