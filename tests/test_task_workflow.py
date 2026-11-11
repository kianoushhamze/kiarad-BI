"""Task lifecycle with real SQL in PostgreSQL an isolated schema; always rolled back.

Run with KIARAD_TEST_TASK_WORKFLOW_DB=1. No real accounts or tasks are created.
Authentication is dependency-overridden; ownership and manager checks run normally.
"""
import os
import unittest
from contextlib import nullcontext
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import operations
from db import engine


@unittest.skipUnless(os.getenv("KIARAD_TEST_TASK_WORKFLOW_DB") == "1", "Opt-in local PostgreSQL test")
class TaskWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.conn = engine.connect()
        self.tx = self.conn.begin()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.tx.rollback)
        schema = "task_test_" + uuid4().hex
        self.conn.execute(text(f"CREATE SCHEMA {schema}"))
        self.conn.execute(text(f"SET LOCAL search_path TO {schema}"))
        for statement in (
            "CREATE TABLE users (id INTEGER PRIMARY KEY,username TEXT,full_name TEXT,role TEXT,salesperson_id INTEGER,is_active INTEGER)",
            "CREATE TABLE customers (id INTEGER PRIMARY KEY,name TEXT)",
            """CREATE TABLE tasks (id SERIAL PRIMARY KEY,title TEXT,description TEXT,priority TEXT,
                status TEXT,progress INTEGER,assigned_to INTEGER REFERENCES users(id),created_by INTEGER,
                customer_id INTEGER,due_date TIMESTAMP,created_at TIMESTAMP,updated_at TIMESTAMP)""",
            """CREATE TABLE task_updates (id SERIAL PRIMARY KEY,task_id INTEGER REFERENCES tasks(id),
                user_id INTEGER REFERENCES users(id),progress INTEGER,status VARCHAR(20),note TEXT,created_at TIMESTAMP)""",
        ):
            self.conn.execute(text(statement))
        operations._ensure_task_workflow(self.conn)
        operations._ensure_task_workflow(self.conn)  # Repeat migration must preserve existing structures.
        self.conn.execute(text("""INSERT INTO users VALUES
            (1,'manager','مدیر آزمون','ceo',NULL,1),
            (2,'worker','پرسنل آزمون','visitor',NULL,1),
            (3,'other','پرسنل دیگر','salesperson',NULL,1),
            (4,'inactive','غیرفعال','visitor',NULL,0)"""))
        self.user = {"id": 1, "role": "ceo"}
        app = FastAPI()
        app.include_router(operations.router)
        app.dependency_overrides[operations.current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.patcher = patch.object(operations, "engine")
        fake_engine = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        fake_engine.connect.side_effect = lambda: nullcontext(self.conn)
        fake_engine.begin.side_effect = lambda: nullcontext(self.conn)

    def create(self):
        response = self.client.post("/tasks", json={"title": "پیگیری آزمایشی", "assigned_to": 2})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_full_report_return_resubmit_approve_and_history(self):
        task_id = self.create()
        operations._ensure_task_workflow(self.conn)
        self.user = {"id": 2, "role": "visitor"}
        self.assertEqual(len(self.client.get("/tasks").json()["tasks"]), 1)
        start = self.client.patch(f"/tasks/{task_id}/progress", json={"status":"in_progress","progress":25,"note":"تماس انجام شد"})
        self.assertEqual(start.status_code, 200, start.text)
        completed = self.client.patch(f"/tasks/{task_id}/progress", json={"status":"completed","progress":100,"note":"مشتری پیگیری و نتیجه ثبت شد"})
        self.assertEqual(completed.json()["review_status"], "pending")
        self.assertEqual(self.client.patch(f"/tasks/{task_id}/progress", json={"status":"in_progress","progress":25}).status_code, 409)
        self.assertEqual(self.client.post(f"/tasks/{task_id}/review",json={"decision":"approved"}).status_code,403)
        self.user = {"id":1,"role":"ceo"}
        self.assertEqual(self.client.post(f"/tasks/{task_id}/review",json={"decision":"changes_requested"}).status_code,422)
        returned = self.client.post(f"/tasks/{task_id}/review",json={"decision":"changes_requested","note":"زمان مراجعهٔ بعدی مشخص شود"})
        self.assertEqual(returned.json()["review_status"], "changes_requested")
        self.assertEqual(returned.json()["status"], "in_progress")
        self.user = {"id":2,"role":"visitor"}
        resubmitted = self.client.patch(f"/tasks/{task_id}/progress", json={"status":"completed","progress":100,"note":"زمان مراجعه ثبت شد"})
        self.assertEqual(resubmitted.json()["review_status"], "pending")
        self.user = {"id":1,"role":"ceo"}
        approved = self.client.post(f"/tasks/{task_id}/review",json={"decision":"approved","note":"بررسی شد"})
        self.assertEqual(approved.json()["review_status"], "approved")
        self.assertEqual(approved.json()["reviewed_by"], 1)
        self.assertEqual(self.client.post(f"/tasks/{task_id}/review",json={"decision":"approved"}).status_code,409)
        history = self.client.get(f"/tasks/{task_id}/updates").json()["items"]
        self.assertEqual([item["status"] for item in history], ["new","in_progress","completed","changes_requested","completed","approved"])
        self.assertIn("مراجعه", history[-2]["note"])
        self.user = {"id":2,"role":"visitor"}
        self.assertEqual(self.client.patch(f"/tasks/{task_id}/progress",json={"status":"blocked","progress":75,"note":"تغییر"}).status_code,409)

    def test_other_employee_cannot_read_update_or_create(self):
        task_id = self.create()
        self.user = {"id":3,"role":"salesperson"}
        self.assertEqual(self.client.get("/tasks").json()["tasks"], [])
        self.assertEqual(self.client.get(f"/tasks/{task_id}/updates").status_code,403)
        self.assertEqual(self.client.patch(f"/tasks/{task_id}/progress",json={"status":"in_progress","progress":25}).status_code,403)
        self.assertEqual(self.client.post("/tasks",json={"title":"کار دیگر","assigned_to":2}).status_code,403)
        self.assertEqual(self.client.get("/tasks/assignees").status_code,403)

    def test_report_validation_and_missing_records(self):
        task_id = self.create()
        self.user = {"id":2,"role":"visitor"}
        for data in ({"status":"completed","progress":100,"note":" "},
                     {"status":"completed","progress":75,"note":"انجام شد"},
                     {"status":"in_progress","progress":100},
                     {"status":"blocked","progress":25},
                     {"status":"approved","progress":100,"note":"تلاش"}):
            self.assertEqual(self.client.patch(f"/tasks/{task_id}/progress",json=data).status_code,422)
        self.assertEqual(self.client.get("/tasks/999/updates").status_code,404)
        self.assertEqual(self.client.patch("/tasks/999/progress",json={"status":"in_progress","progress":25}).status_code,404)
        self.user = {"id":1,"role":"ceo"}
        self.assertEqual(self.client.post(f"/tasks/{task_id}/review",json={"decision":"approved"}).status_code,409)
        self.assertEqual(self.client.post("/tasks/999/review",json={"decision":"approved"}).status_code,404)

    def test_active_assignees_and_manager_self_review(self):
        self.assertEqual([p["id"] for p in self.client.get("/tasks/assignees").json()["users"]], [2,3])
        self.assertEqual(self.client.post("/tasks",json={"title":"کار غیرفعال","assigned_to":4}).status_code,404)
        self.assertEqual(self.client.post("/tasks",json={"title":"  ","assigned_to":2}).status_code,422)
        task_id = self.create()
        self.conn.execute(text("UPDATE tasks SET assigned_to=1,status='completed',review_status='pending' WHERE id=:id"),{"id":task_id})
        self.assertEqual(self.client.post(f"/tasks/{task_id}/review",json={"decision":"approved"}).status_code,403)

    def test_boolean_active_column_is_supported(self):
        self.conn.execute(text("ALTER TABLE users ALTER COLUMN is_active TYPE BOOLEAN USING is_active=1"))
        task_id = self.create()
        self.assertGreater(task_id,0)
        self.assertEqual(len(self.client.get("/tasks/assignees").json()["users"]),2)

    def test_manager_receives_review_notification(self):
        task_id = self.create()
        self.conn.execute(text("UPDATE tasks SET status='completed',review_status='pending' WHERE id=:id"),{"id":task_id})
        with patch.object(operations, "_table_exists", side_effect=lambda conn,name: name=="tasks"):
            items = operations._notification_items(self.conn,{"id":1,"role":"ceo"})
            self.assertTrue(any(item["key"]=="tasks:review" for item in items))
            items = operations._notification_items(self.conn,{"id":2,"role":"visitor"})
            self.assertFalse(any(item["key"]=="tasks:review" for item in items))


if __name__ == "__main__":
    unittest.main()

