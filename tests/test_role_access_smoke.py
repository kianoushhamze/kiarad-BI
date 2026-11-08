"""Read-only authorization smoke tests against the local Kiarad API.

Run with the project's Python environment while the backend is listening on
127.0.0.1:8000. No passwords or tokens are printed or stored.
"""

from pathlib import Path
from datetime import datetime, timedelta, timezone
import os
import unittest

from dotenv import load_dotenv
import jwt
import requests
from sqlalchemy import text
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

from db import engine  # noqa: E402
from operations import create_token, create_user, update_user, change_password, UserCreate  # noqa: E402


BASE_URL = os.getenv("KIARAD_TEST_API_URL", "http://127.0.0.1:8000").rstrip("/")


class RoleAccessSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT ON (role) id, role, password_version
                FROM users WHERE is_active = 1 AND role IN ('ceo', 'salesperson')
                ORDER BY role, id
            """)).mappings().all()
        cls.users = {row["role"]: dict(row) for row in rows}
        if set(cls.users) != {"ceo", "salesperson"}:
            raise unittest.SkipTest("Active CEO and salesperson accounts are required")

    def get(self, path, role=None):
        headers = {}
        if role:
            headers["Authorization"] = "Bearer " + create_token(self.users[role])
        return requests.get(BASE_URL + path, headers=headers, timeout=15)

    def assert_status(self, path, role, expected):
        response = self.get(path, role)
        self.assertEqual(response.status_code, expected, f"{role or 'anonymous'} {path}: {response.status_code}")
        return response

    def test_anonymous_requests_are_denied(self):
        for path in ("/auth/me", "/dashboard/full", "/roles"):
            with self.subTest(path=path):
                self.assert_status(path, None, 401)

    def test_ceo_can_read_management_routes(self):
        self.assert_status("/auth/me", "ceo", 200)
        dashboard = self.assert_status("/dashboard/full?range=month", "ceo", 200).json()
        self.assertEqual(dashboard["view_mode"], "manager")
        self.assert_status("/roles", "ceo", 200)
        self.assert_status("/users", "ceo", 200)
        self.assert_status("/salespersons", "ceo", 200)

    def test_salesperson_sees_personal_view_only(self):
        self.assert_status("/auth/me", "salesperson", 200)
        dashboard = self.assert_status("/dashboard/full?range=month", "salesperson", 200).json()
        self.assertEqual(dashboard["view_mode"], "salesperson")
        self.assert_status("/tasks", "salesperson", 200)
        for path in ("/roles", "/users", "/salespersons", "/treasury/overview", "/targets/company"):
            with self.subTest(path=path):
                self.assert_status(path, "salesperson", 403)

    def test_token_role_claim_cannot_elevate_salesperson(self):
        salesperson = self.users["salesperson"]
        now = datetime.now(timezone.utc)
        token = jwt.encode({
            "sub": str(salesperson["id"]),
            "role": "ceo",
            "pwd_ver": salesperson["password_version"],
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }, os.environ["KIARAD_JWT_SECRET"], algorithm="HS256")
        response = requests.get(BASE_URL + "/roles", headers={"Authorization": "Bearer " + token}, timeout=15)
        self.assertEqual(response.status_code, 403)

    def test_expired_token_is_denied(self):
        salesperson = self.users["salesperson"]
        now = datetime.now(timezone.utc)
        token = jwt.encode({
            "sub": str(salesperson["id"]),
            "role": "salesperson",
            "pwd_ver": salesperson["password_version"],
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }, os.environ["KIARAD_JWT_SECRET"], algorithm="HS256")
        response = requests.get(BASE_URL + "/auth/me", headers={"Authorization": "Bearer " + token}, timeout=15)
        self.assertEqual(response.status_code, 401)

    def test_unwanted_roles_and_main_ceo_changes_are_rejected_without_writes(self):
        ceo = self.users["ceo"]
        for role in ("sales_manager", "finance"):
            with self.subTest(role=role):
                data = UserCreate(username="unused_test", full_name="Unused Test", password="not-a-real-password", role=role)
                with self.assertRaises(HTTPException) as caught:
                    create_user(data, ceo)
                self.assertEqual(caught.exception.status_code, 422)
        for payload in ({"role": "salesperson"}, {"is_active": 0}):
            with self.subTest(payload=payload):
                with self.assertRaises(HTTPException) as caught:
                    update_user(1, payload, ceo)
                self.assertEqual(caught.exception.status_code, 403)
        with self.assertRaises(HTTPException) as caught:
            change_password(1, {"password": "short"}, ceo)
        self.assertEqual(caught.exception.status_code, 422)

        headers = {"Authorization": "Bearer " + create_token(ceo)}
        blocked_create = requests.post(BASE_URL + "/users", headers=headers, json={
            "username": "unused_test", "full_name": "Unused Test",
            "password": "not-a-real-password", "role": "finance",
        }, timeout=15)
        self.assertEqual(blocked_create.status_code, 422)
        blocked_update = requests.patch(BASE_URL + "/users/1", headers=headers,
                                        json={"is_active": 0}, timeout=15)
        self.assertEqual(blocked_update.status_code, 403)


if __name__ == "__main__":
    unittest.main()
