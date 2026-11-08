"""Read-only checks for visit routes, voice customers, and payroll views."""
from pathlib import Path
import os
import unittest

from dotenv import load_dotenv
import requests
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

from db import engine  # noqa: E402
from operations import create_token  # noqa: E402

BASE_URL = os.getenv("KIARAD_TEST_API_URL", "http://127.0.0.1:8000").rstrip("/")


class NewWorkflowsReadSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, role, password_version, salesperson_id FROM users
                WHERE is_active::text IN ('1','true','t') AND role IN ('ceo','salesperson','visitor')
                ORDER BY CASE WHEN role='ceo' THEN 0 ELSE 1 END, id
            """)).mappings().all()
        cls.ceo = next((dict(row) for row in rows if row["role"] == "ceo"), None)
        cls.staff = next((dict(row) for row in rows if row["role"] in {"salesperson", "visitor"}), None)
        if not cls.ceo:
            raise unittest.SkipTest("An active CEO account is required")

    @staticmethod
    def headers(user):
        return {"Authorization": "Bearer " + create_token(user)}

    def test_ceo_can_read_new_workflow_sources(self):
        for path in ("/api/compensation/payroll-people", "/operations/voice-customers", "/notifications",
                     "/chat/messages?room=general", "/catalog-files"):
            with self.subTest(path=path):
                response = requests.get(BASE_URL + path, headers=self.headers(self.ceo), timeout=20)
                self.assertEqual(response.status_code, 200, f"{path}: {response.status_code} {response.text[:180]}")

    def test_anonymous_access_is_denied(self):
        for path in ("/api/compensation/payroll-people", "/operations/voice-customers", "/notifications"):
            with self.subTest(path=path):
                response = requests.get(BASE_URL + path, timeout=20)
                self.assertEqual(response.status_code, 401)

    def test_invalid_chat_and_catalog_payloads_are_rejected_without_writes(self):
        headers = self.headers(self.ceo)
        empty_chat = requests.post(BASE_URL + "/chat/send", headers=headers,
                                   json={"message": "", "room": "general"}, timeout=20)
        self.assertEqual(empty_chat.status_code, 400)
        missing_attachment = requests.get(BASE_URL + "/chat/attachments/2147483647",
                                          headers=headers, timeout=20)
        self.assertEqual(missing_attachment.status_code, 404)
        invalid_catalog = requests.post(
            BASE_URL + "/upload/catalog-file", headers=headers,
            data={"media_type": "pdf", "caption": ""},
            files={"file": ("fake.pdf", b"plain text", "application/pdf")}, timeout=20,
        )
        self.assertEqual(invalid_catalog.status_code, 400)

    def test_staff_reads_only_own_scope(self):
        if not self.staff or not self.staff.get("salesperson_id"):
            self.skipTest("An active linked salesperson or visitor account is required")
        headers = self.headers(self.staff)
        people = requests.get(BASE_URL + "/api/compensation/payroll-people", headers=headers, timeout=20)
        self.assertEqual(people.status_code, 200, people.text[:180])
        self.assertEqual([item["id"] for item in people.json()["items"]], [self.staff["salesperson_id"]])
        routes = requests.get(BASE_URL + f"/api/compensation/visit-routes?user_id={self.ceo['id']}", headers=headers, timeout=20)
        self.assertEqual(routes.status_code, 200, routes.text[:180])
        self.assertTrue(all(item["user_id"] == self.staff["id"] for item in routes.json()["items"]))


if __name__ == "__main__":
    unittest.main()
