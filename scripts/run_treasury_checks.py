"""Run treasury checks with pg_temp-only connections and no external traffic."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    os.environ["KIARAD_TEST_TREASURY_DB"] = "1"
    os.environ["KIARAD_TEST_BASE_REGISTRY_DB"] = "1"
    os.environ["KIARAD_TEST_BASE_READINESS_DB"] = "1"
    import db
    from sqlalchemy import create_engine
    from run_compensation_checks import SafeResult
    old = db.engine
    isolated = create_engine(old.url, connect_args={"options": "-c search_path=pg_temp -c statement_timeout=15000 -c lock_timeout=3000", "connect_timeout": 5})
    db.engine = isolated
    report = {"temporary_tables_only": True, "holoo_writes": False, "external_http": False}
    try:
        with isolated.connect() as conn:
            assert conn.exec_driver_sql("SHOW search_path").scalar() == "pg_temp"
        blocked = AssertionError("External traffic disabled")
        with patch("requests.sessions.Session.request", side_effect=blocked), patch("httpx.HTTPTransport.handle_request", side_effect=blocked), patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=blocked):
            suite = unittest.defaultTestLoader.loadTestsFromNames(["test_treasury_finance", "test_treasury_strategy", "test_treasury_import_safety", "test_holoo_finance", "test_purchase_profit", "test_treasury_operating_plan", "test_holoo_finance_jobs", "test_holoo_automatic_refresh", "test_holoo_operational_sync", "test_treasury_excel", "test_inventory_intelligence", "test_field_intelligence", "test_base_registry", "test_customer_directory_search", "test_daily_proforma_export", "test_base_readiness", "test_public_registry_review", "test_public_directory_extract", "test_file_recovery"])
            result = SafeResult()
            suite.run(result)
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped), passed=result.wasSuccessful() and not result.skipped, cases=result.cases)
        if result.failures or result.errors:
            # Test data are explicitly synthetic; traceback helps repair only this suite.
            for _, trace in result.failures + result.errors:
                print(trace)
    except Exception as error:
        report.update(passed=False, runner_error_type=type(error).__name__)
    finally:
        db.engine = old
        isolated.dispose()
    output = ROOT / "audit-2026-10-19" / "treasury-tests.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
