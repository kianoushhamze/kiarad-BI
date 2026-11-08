r"""اجرای تکرارپذیر آزمون‌های دسترسی پرسنل روی جدول‌های موقت.

اجرا از ریشهٔ پروژه:
    .venv/Scripts/python.exe -B scripts/run_personnel_access_tests.py

چرخهٔ شروع برنامه اجرا نمی‌شود. هیچ درخواست بیرونی یا عملیات هلو مجاز نیست.
گزارش فقط شناسهٔ آزمون، وضعیت و نام نوع خطا را ذخیره می‌کند.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "audit-2026-10-18" / "personnel-tests-final.json"
EXPECTED_TESTS = 85
TEST_MODULES = (
    "test_task_workflow",
    "test_visit_checkin_workflow",
    "test_visit_routes",
    "test_visit_module_access",
    "test_visit_coverage",
    "test_base_proposals",
    "test_voice_report_workflow",
    "test_personnel_session_safety",
    "test_proforma_cancellation",
    "test_proforma_ownership",
    "test_personnel_access_e2e",
    "test_crm_schema",
    "test_chat_attachment_validation",
)
OPT_IN_FLAGS = (
    "KIARAD_TEST_TASK_WORKFLOW_DB",
    "KIARAD_TEST_VISIT_WORKFLOW_DB",
    "KIARAD_TEST_VOICE_WORKFLOW_DB",
    "KIARAD_TEST_VISIT_COVERAGE_DB",
    "KIARAD_TEST_BASE_PROPOSALS_DB",
    "KIARAD_TEST_PERSONNEL_DB",
    "KIARAD_TEST_PROFORMA_OWNERSHIP_DB",
    "KIARAD_TEST_PERSONNEL_E2E_DB",
)


class SafeResult(unittest.TestResult):
    """متن استثنا، توکن، گذرواژه و دستور دارای پارامتر را گزارش نمی‌کند."""

    def __init__(self):
        super().__init__()
        self.cases = []
        self._current = None

    def startTest(self, test):
        super().startTest(test)
        self._started = time.perf_counter()
        self._current = {"id": test.id(), "status": "running"}

    def addSuccess(self, test):
        super().addSuccess(test)
        self._current["status"] = "passed"

    def addError(self, test, err):
        super().addError(test, err)
        self._current.update(status="error", error_type=err[0].__name__)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._current.update(status="failed", error_type=err[0].__name__)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._current["status"] = "skipped"

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._current.update(
                status="failed" if issubclass(err[0], test.failureException) else "error",
                error_type=err[0].__name__,
            )

    def stopTest(self, test):
        self._current["duration_seconds"] = round(time.perf_counter() - self._started, 4)
        self.cases.append(self._current)
        print(self._current["status"].upper(), test.id(), flush=True)
        super().stopTest(test)


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    for flag in OPT_IN_FLAGS:
        os.environ[flag] = "1"

    report = {
        "started_at": datetime.now().astimezone().isoformat(),
        "runner": "unittest",
        "expected_tests": EXPECTED_TESTS,
        "modules": list(TEST_MODULES),
        "isolation": {
            "database_search_path": "pg_temp",
            "statement_timeout_ms": 15000,
            "lock_timeout_ms": 3000,
            "connect_timeout_seconds": 5,
            "temporary_tables_rolled_back": True,
            "external_http_blocked": True,
            "application_startup_executed": False,
            "holoo_operations_executed": False,
        },
        "cases": [],
    }
    old_engine = isolated_engine = None
    original_tempdir = tempfile.tempdir
    succeeded = False
    try:
        # تنظیمات محلی خوانده می‌شود؛ هیچ مقدار تنظیماتی چاپ یا ذخیره نمی‌شود.
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
        import db
        from sqlalchemy import create_engine

        old_engine = db.engine
        isolated_engine = create_engine(
            old_engine.url,
            connect_args={
                "options": "-c search_path=pg_temp -c statement_timeout=15000 -c lock_timeout=3000",
                "connect_timeout": 5,
            },
            pool_pre_ping=True,
        )
        db.engine = isolated_engine
        db.get_connection = lambda: isolated_engine.raw_connection()
        db.SessionLocal.configure(bind=isolated_engine)
        with isolated_engine.connect() as connection:
            assert connection.exec_driver_sql("SHOW search_path").scalar() == "pg_temp"

        with tempfile.TemporaryDirectory(prefix="qa-personnel-", dir=ROOT) as folder:
            tempfile.tempdir = folder
            blocked = AssertionError("External HTTP is disabled for isolated tests")
            with (
                patch("requests.sessions.Session.request", side_effect=blocked),
                patch("httpx.HTTPTransport.handle_request", side_effect=blocked),
                patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=blocked),
            ):
                suite = unittest.defaultTestLoader.loadTestsFromNames(TEST_MODULES)
                loaded = suite.countTestCases()
                report["loaded_tests"] = loaded
                if loaded != EXPECTED_TESTS:
                    raise RuntimeError("Unexpected test count")
                result = SafeResult()
                suite.run(result)
            report.update(
                tests=result.testsRun,
                failures=len(result.failures),
                errors=len(result.errors),
                skipped=len(result.skipped),
                cases=result.cases,
            )
            succeeded = (
                result.wasSuccessful()
                and result.testsRun == EXPECTED_TESTS
                and not result.skipped
            )
    except Exception as error:
        report["runner_error_type"] = type(error).__name__
        print("RUNNER_ERROR", type(error).__name__, flush=True)
    finally:
        tempfile.tempdir = original_tempdir
        if isolated_engine is not None:
            isolated_engine.dispose()
        if old_engine is not None:
            old_engine.dispose()

    report["passed"] = succeeded
    report["finished_at"] = datetime.now().astimezone().isoformat()
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "SUMMARY",
        report.get("tests", 0),
        "tests;",
        report.get("failures", 0),
        "failures;",
        report.get("errors", 0),
        "errors;",
        report.get("skipped", 0),
        "skipped;",
        "PASS" if succeeded else "FAIL",
        flush=True,
    )
    print("REPORT", REPORT_PATH.relative_to(ROOT).as_posix(), flush=True)
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
