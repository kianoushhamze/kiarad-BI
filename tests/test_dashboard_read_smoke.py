"""Read-only smoke coverage for dashboard data sources.

Requires a running local API and an existing active CEO. It does not create
accounts, submit forms, or print credentials.
"""

from pathlib import Path
import os
import unittest

from dotenv import load_dotenv
import requests
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

from db import engine  # noqa: E402
from iran_time import iran_month_bounds, iran_today
from operations import create_token  # noqa: E402


BASE_URL = os.getenv("KIARAD_TEST_API_URL", "http://127.0.0.1:8000").rstrip("/")

READ_PATHS = (
    "/auth/me",
    "/auth/permissions",
    "/dashboard/full?range=month",
    "/users",
    "/salespersons",
    "/roles",
    "/roles/all-modules",
    "/tasks",
    "/daily-reports",
    "/targets/person-targets",
    "/visitors/overview",
    "/operations/visitors/kpis",
    "/operations/customers-list",
    "/operations/products-list",
    "/operations/proformas/my",
    "/treasury/overview",
    "/treasury/forecast?days=60",
    "/treasury/debtors",
    "/catalog/products",
    "/crm/interactions",
    "/campaigns",
    "/directory/customers",
    "/chat/messages?room=general",
    "/assistant/history?limit=50",
    "/assistant/advisory/team",
)


class DashboardReadSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with engine.connect() as conn:
            ceo = conn.execute(text(
                "SELECT id, role, password_version FROM users "
                "WHERE role = 'ceo' AND is_active = 1 ORDER BY id LIMIT 1"
            )).mappings().first()
        if not ceo:
            raise unittest.SkipTest("An active CEO account is required")
        cls.headers = {"Authorization": "Bearer " + create_token(dict(ceo))}

    def test_dashboard_read_sources(self):
        for path in READ_PATHS:
            with self.subTest(path=path):
                response = requests.get(BASE_URL + path, headers=self.headers, timeout=20)
                self.assertEqual(response.status_code, 200, f"{path}: {response.status_code} {response.text[:180]}")
                self.assertTrue(response.headers.get("content-type", "").startswith("application/json"), path)

    def test_headline_metrics_reconcile_to_source_rows(self):
        dashboard = requests.get(BASE_URL + "/dashboard/full?range=month",
                                 headers=self.headers, timeout=20).json()
        with engine.connect() as conn:
            month_start,_=iran_month_bounds()
            from datetime import timedelta
            tomorrow=iran_today()+timedelta(days=1)
            month_sales, invoice_count = conn.execute(text("""
                SELECT COALESCE(SUM(total_amount), 0), COUNT(*) FROM sales
                WHERE date >= :begin AND date < :finish
            """),{"begin":month_start,"finish":tomorrow}).first()
            product_count, inventory_value = conn.execute(text("""
                SELECT COUNT(*), COALESCE(SUM(price * stock), 0)
                FROM products WHERE is_active = 1
            """)).first()
            latest = conn.execute(text("""
                SELECT id, snapshot_date FROM receivable_snapshots
                ORDER BY snapshot_date DESC, id DESC LIMIT 1
            """)).mappings().first()
            debt = conn.execute(text("""
                SELECT COALESCE(SUM(balance), 0) FROM receivable_balances
                WHERE snapshot_id = :snapshot_id
            """), {"snapshot_id": latest["id"]}).scalar() if latest else None
            latest_sale_date = conn.execute(text("SELECT MAX(date)::date FROM sales")).scalar()

        kpi = dashboard["ceo_kpi"]
        inventory = dashboard["inventory"]
        self.assertAlmostEqual(kpi["total_sales"], float(month_sales), places=2)
        self.assertEqual(kpi["invoice_count"], invoice_count)
        self.assertEqual(kpi["sales_source_date"], str(latest_sale_date) if latest_sale_date else None)
        self.assertEqual(inventory["product_count"], product_count)
        self.assertAlmostEqual(inventory["inventory_value"], float(inventory_value), places=2)
        if latest:
            self.assertAlmostEqual(kpi["total_debt"], float(debt), places=2)
            self.assertEqual(kpi["debt_snapshot_date"], str(latest["snapshot_date"]))

        for staff in dashboard["staff"]["staff"]:
            if staff["target"] is None:
                self.assertIsNone(staff["achievement_percent"])


if __name__ == "__main__":
    unittest.main()
