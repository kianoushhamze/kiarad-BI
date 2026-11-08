"""Read-only smoke checks of the active stack. Never logs credentials or amounts."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)

import requests
from sqlalchemy import text
from db import engine
from operations import create_token


def main():
    cases = []
    def record(name, passed, status=None):
        cases.append({"name": name, "passed": bool(passed), **({"status": status} if status is not None else {})})
    with engine.connect() as conn:
        users = [dict(row) for row in conn.execute(text("SELECT id, role, password_version FROM users WHERE is_active=1 ORDER BY id")).mappings()]
        before = {table: conn.execute(text("SELECT COUNT(*) FROM " + table)).scalar() for table in ("cash_accounts", "financial_documents", "fixed_expenses", "treasury_strategy_revisions", "holoo_financial_snapshots", "treasury_excel_batches")}
    session = requests.Session()
    session.trust_env = False
    session.max_redirects = 2
    backend = "http://127.0.0.1:8000"
    frontend = "http://127.0.0.1:3000"
    response = session.get(backend + "/health", timeout=20)
    record("backend-health", response.status_code == 200, response.status_code)
    record("anonymous-treasury-denied", session.get(backend + "/treasury/strategy/overview", timeout=20).status_code == 401)
    for user in users:
        headers = {"Authorization": "Bearer " + create_token(user)}
        allowed = user["role"] in {"ceo", "finance"}
        for name, origin, prefix in (("backend", backend, ""), ("frontend-proxy", frontend, "/api")):
            response = session.get(origin + prefix + "/treasury/strategy/overview", headers=headers, timeout=30)
            record(f"{name}-role-{user['role']}-user-{user['id']}", response.status_code == (200 if allowed else 403), response.status_code)
            if allowed and response.status_code == 200:
                payload = response.json()
                record(f"{name}-holoo-source-present-user-{user['id']}", payload.get("holoo_snapshot") is not None)
                record(f"{name}-13-weeks-user-{user['id']}", len(payload["projection"]["weeks"]) == 13)
                record(f"{name}-no-fake-profit-user-{user['id']}", all(r["actual"] is None for r in payload["growth"]["rows"]) if not payload["approved_actuals"] else True)
                record(f"{name}-budget-user-{user['id']}", int(payload["operating_plan"]["monthly_expense_irr"]) == 3000000000)
                record(f"{name}-no-false-health-user-{user['id']}", payload["operating_projection"]["health_confirmed"] is False)
                record(f"{name}-invoice-estimate-never-approved-user-{user['id']}", payload["purchase_estimate"]["approved_profit"] is False and payload["purchase_estimate"]["growth_attainment_available"] is False)
                record(f"{name}-all-7-months-user-{user['id']}", len(payload["purchase_estimate"]["months"]) == 7)
            for path in ("/treasury/excel/reports", "/treasury/strategy/holoo-refresh", "/treasury/excel/template"):
                report_response = session.get(origin + prefix + path, headers=headers, timeout=20)
                record(f"{name}-{path}-user-{user['id']}", report_response.status_code == (200 if allowed else 403), report_response.status_code)
        if allowed:
            response = session.post(frontend + "/api/treasury/strategy/cash-scenario", headers=headers, json={"collection_percent": 70, "collection_delay_days": 7, "extra_outflow": "0"}, timeout=20)
            record(f"readonly-scenario-user-{user['id']}", response.status_code == 200 and response.json().get("saved") is False, response.status_code)
            for path in ("/treasury/overview", "/treasury/forecast?days=60", "/treasury/checks/balance-sheet"):
                response = session.get(frontend + "/api" + path, headers=headers, timeout=20)
                record(f"existing-{path}", response.status_code == 200, response.status_code)
    response = session.get(frontend + "/treasury", timeout=20)
    record("treasury-page", response.status_code == 200, response.status_code)
    scripts = list(dict.fromkeys(re.findall(r'<script[^>]+src="([^"]+)"', response.text)))
    record("treasury-assets-present", bool(scripts))
    for i, path in enumerate(scripts):
        if not path.startswith("/_next/"):
            continue
        asset = session.get(frontend + path, timeout=20)
        record(f"asset-{i}", asset.status_code == 200, asset.status_code)
    public_page = session.get("https://kiarad.taile287ae.ts.net/treasury", timeout=30)
    record("private-https-treasury", public_page.status_code == 200, public_page.status_code)
    with engine.connect() as conn:
        after = {table: conn.execute(text("SELECT COUNT(*) FROM " + table)).scalar() for table in before}
    record("no-financial-rows-created-by-smoke-checks", before == after)
    result = {"checks": len(cases), "failures": sum(not case["passed"] for case in cases), "financial_writes": False, "holoo_requests": False, "browser_visual_review": "blocked_by_work_settings", "cases": cases}
    folder = ROOT / "audit-2026-10-19"
    folder.mkdir(exist_ok=True)
    (folder / "treasury-live.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "cases"}))
    for case in cases:
        if not case["passed"]:
            print(json.dumps(case))
    return int(bool(result["failures"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as error:
        print("READ_ONLY_CHECK_ERROR", type(error).__name__)
        raise SystemExit(1)
