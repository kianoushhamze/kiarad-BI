"""آزمون مالکیت پیش‌فاکتور با جدول‌های موقت؛ تمام تغییرات برگشت داده می‌شوند.

با KIARAD_TEST_PROFORMA_OWNERSHIP_DB=1 فعال می‌شود. احراز هویت روتر با
کاربر آزمایشی جایگزین می‌شود؛ نگهبان نقش، مالکیت و دستورهای واقعی اجرا می‌شوند.
"""
import os
import unittest
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import proformas


@unittest.skipUnless(
    os.getenv("KIARAD_TEST_PROFORMA_OWNERSHIP_DB") == "1",
    "آزمون اختیاری با جدول‌های موقت پایگاه‌داده",
)
class ProformaOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.conn = proformas.engine.connect()
        self.addCleanup(self.conn.close)
        transaction = self.conn.begin()
        self.addCleanup(transaction.rollback)
        # هر جدول استفاده‌شده باید موقت باشد؛ جدول واقعی در مسیر جستجو نیست.
        self.conn.execute(text("SET LOCAL search_path TO pg_temp"))
        self.conn.execute(text("SET LOCAL statement_timeout TO '15000ms'"))
        self.conn.execute(text("SET LOCAL lock_timeout TO '3000ms'"))
        statements = [
            "CREATE TEMP TABLE customers (id INTEGER PRIMARY KEY,name TEXT,credit_limit NUMERIC)",
            "CREATE TEMP TABLE salespersons (id INTEGER PRIMARY KEY,name TEXT)",
            "CREATE TEMP TABLE products (id INTEGER PRIMARY KEY,name TEXT,price NUMERIC,stock NUMERIC,price2 NUMERIC)",
            "CREATE TEMP TABLE sales (customer_id INTEGER,total_amount NUMERIC)",
            "CREATE TEMP TABLE payments (customer_id INTEGER,amount NUMERIC)",
            """CREATE TEMP TABLE proforma_invoices (
                id SERIAL PRIMARY KEY,customer_id INTEGER,salesperson_id INTEGER,
                total_amount NUMERIC,status TEXT,credit_grade TEXT,notes TEXT,
                items_json JSONB,created_at TIMESTAMP)""",
            """CREATE TEMP TABLE inventory_reservations (
                id SERIAL PRIMARY KEY,product_id INTEGER,channel TEXT,
                external_order_id TEXT,quantity NUMERIC,status TEXT,created_at TIMESTAMP)""",
            """CREATE TEMP TABLE proforma_holoo_queue (
                id SERIAL PRIMARY KEY,proforma_id INTEGER UNIQUE,operation_key TEXT,
                status TEXT,attempt_count INTEGER,created_at TIMESTAMP,updated_at TIMESTAMP)""",
            "INSERT INTO customers VALUES (40,'مشتری آزمایشی',10000)",
            "INSERT INTO salespersons VALUES (10,'پرسنل اول'),(11,'پرسنل دوم')",
            "INSERT INTO products VALUES (1,'کالای آزمایشی',100,20,80)",
        ]
        for statement in statements:
            self.conn.execute(text(statement))

        @contextmanager
        def begin():
            with self.conn.begin_nested():
                yield self.conn

        fake_engine = SimpleNamespace(begin=begin, connect=lambda: nullcontext(self.conn))
        patcher = patch.object(proformas, "engine", fake_engine)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = {"id": 2, "role": "visitor", "salesperson_id": 10}
        app = FastAPI()
        app.include_router(proformas.router)
        app.dependency_overrides[proformas.current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def create(self, impersonated=11):
        return self.client.post(
            "/operations/proformas",
            json={
                "customer_id": 40,
                "salesperson_id": impersonated,
                "total_amount": 1,
                "items": [{"product_id": 1, "quantity": 2}],
            },
        )

    def test_staff_cannot_impersonate_or_access_another_staff_proforma(self):
        first = self.create()
        self.assertEqual(first.status_code, 200, first.text)
        first_id = first.json()["proforma_id"]
        stored = self.conn.execute(
            text("SELECT salesperson_id,total_amount FROM proforma_invoices WHERE id=:id"),
            {"id": first_id},
        ).one()
        self.assertEqual(tuple(stored), (10, 200))
        own_rows = self.client.get("/operations/proformas/my?salesperson_id=11").json()
        self.assertEqual([row["id"] for row in own_rows], [first_id])

        self.user = {"id": 3, "role": "salesperson", "salesperson_id": 11}
        self.assertEqual(
            self.client.get("/operations/proformas/my?salesperson_id=10").json(), []
        )
        self.assertEqual(
            self.client.post(f"/operations/proformas/{first_id}/cancel").status_code, 403
        )
        for action in ("approve", "reject", "queue"):
            with self.subTest(action=action):
                self.assertEqual(
                    self.client.post(f"/operations/proformas/{first_id}/{action}").status_code,
                    403,
                )
        self.assertEqual(
            self.conn.execute(
                text("SELECT status FROM proforma_invoices WHERE id=:id"), {"id": first_id}
            ).scalar(),
            "approved",
        )
        self.assertEqual(
            self.conn.execute(text("SELECT COUNT(*) FROM proforma_holoo_queue")).scalar(), 0
        )

        second = self.create(impersonated=10)
        self.assertEqual(second.status_code, 200, second.text)
        second_id = second.json()["proforma_id"]
        self.assertEqual(
            self.conn.execute(
                text("SELECT salesperson_id FROM proforma_invoices WHERE id=:id"),
                {"id": second_id},
            ).scalar(),
            11,
        )
        self.assertEqual(
            [row["id"] for row in self.client.get("/operations/proformas/my").json()],
            [second_id],
        )
        self.user = {"id": 1, "role": "ceo"}
        self.assertEqual(len(self.client.get("/operations/proformas/my").json()), 2)

        self.user = {"id": 2, "role": "visitor", "salesperson_id": 10}
        self.assertEqual(
            self.client.post(f"/operations/proformas/{first_id}/cancel").status_code, 200
        )
        self.assertEqual(
            self.conn.execute(
                text("SELECT COUNT(*) FROM inventory_reservations WHERE status='released'")
            ).scalar(),
            1,
        )

    def test_unlinked_staff_has_no_proformas_and_cannot_create(self):
        self.user = {"id": 4, "role": "visitor", "salesperson_id": None}
        self.assertEqual(self.create().status_code, 403)
        self.assertEqual(self.client.get("/operations/proformas/my").json(), [])
        self.assertEqual(
            self.conn.execute(text("SELECT COUNT(*) FROM proforma_invoices")).scalar(), 0
        )

    def test_price_two_is_calculated_on_server_and_recorded(self):
        response=self.client.post('/operations/proformas',json={'customer_id':40,'items':[{'product_id':1,'quantity':2,'price_level':2,'unit_price':1}]})
        self.assertEqual(response.status_code,200,response.text)
        row=self.conn.execute(text('SELECT total_amount,items_json FROM proforma_invoices')).mappings().one()
        self.assertEqual(row['total_amount'],160)
        self.assertEqual(row['items_json'][0]['price_level'],2)
        self.assertEqual(row['items_json'][0]['unit_price'],80)

    def test_unknown_second_price_does_not_fall_back_or_reserve_stock(self):
        self.conn.execute(text('UPDATE products SET price2=NULL'))
        response=self.client.post('/operations/proformas',json={'customer_id':40,'items':[{'product_id':1,'quantity':2,'price_level':2}]})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM inventory_reservations')).scalar(),0)

    def test_invalid_price_levels_rejected_before_writes(self):
        for value in (True,0,3,'2',1.0):
            with self.subTest(level=value):
                response=self.client.post('/operations/proformas',json={'customer_id':40,'items':[{'product_id':1,'quantity':2,'price_level':value}]})
                self.assertEqual(response.status_code,422)
        self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM proforma_invoices')).scalar(),0)

    def test_credit_endpoint_accounts_for_proforma_amount(self):
        """سقف اعتبار باید مانده بدهی + مبلغ همین پیش‌فاکتور را بسنجد، نه فقط مانده."""
        response = self.client.get("/operations/customers/40/credit", params={"proforma_amount": 9000})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["grade"], "green")
        self.assertEqual(body["projected_balance"], 9000.0)

        response = self.client.get("/operations/customers/40/credit", params={"proforma_amount": 10000})
        self.assertEqual(response.json()["grade"], "yellow")

        response = self.client.get("/operations/customers/40/credit", params={"proforma_amount": 11000})
        body = response.json()
        self.assertEqual(body["grade"], "red")
        self.assertIn("پیش‌فاکتور", body["message"])

        # بدون مبلغ پیش‌فاکتور فقط ماندهٔ فعلی سنجیده می‌شود (مانده صفر ← سبز).
        response = self.client.get("/operations/customers/40/credit")
        self.assertEqual(response.json()["grade"], "green")

        # ماندهٔ بدهی واقعی هم در محاسبه اعمال می‌شود.
        self.conn.execute(text("INSERT INTO sales (customer_id, total_amount) VALUES (40, 6000)"))
        self.conn.execute(text("INSERT INTO payments (customer_id, amount) VALUES (40, 1000)"))
        response = self.client.get("/operations/customers/40/credit", params={"proforma_amount": 4000})
        self.assertEqual(response.json()["grade"], "green")  # 5000 + 4000 = 9000
        response = self.client.get("/operations/customers/40/credit", params={"proforma_amount": 5000})
        self.assertEqual(response.json()["grade"], "yellow")  # 5000 + 5000 = 10000 → دقیقاً سقف
        self.conn.execute(text("INSERT INTO payments (customer_id, amount) VALUES (40, 1)"))
        response = self.client.get("/operations/customers/40/credit", params={"proforma_amount": 5000})
        self.assertEqual(response.json()["grade"], "green")  # 4999 + 5000 = 9999

        # مشتری بدون سقف اعتباری همیشه سبز است.
        self.conn.execute(text("UPDATE customers SET credit_limit = NULL WHERE id = 40"))
        response = self.client.get("/operations/customers/40/credit", params={"proforma_amount": 999999})
        self.assertEqual(response.json()["grade"], "green")


if __name__ == "__main__":
    unittest.main()
