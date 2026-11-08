"""Unit tests for scheduled assistant automations (no database, no real LLM)."""
import unittest
from datetime import datetime
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError

import assistant_automations as aa
from assistant_automations import AutomationCreate, compute_next_run, describe_schedule
from iran_time import IRAN_TIMEZONE


CEO = {"id": 1, "role": "ceo", "username": "admin", "full_name": "مدیر"}
SALES = {"id": 2, "role": "salesperson", "username": "field", "full_name": "ویزیتور"}


class ScheduleTests(unittest.TestCase):
    def test_interval_next_run(self):
        data = AutomationCreate(name="گزارش دوره‌ای", prompt="خلاصهٔ فروش امروز را بده", interval_hours=6)
        now = datetime(2026, 11, 6, 10, 0, tzinfo=IRAN_TIMEZONE)
        self.assertEqual(compute_next_run(data, now), datetime(2026, 11, 6, 16, 0, tzinfo=IRAN_TIMEZONE))
        self.assertEqual(describe_schedule(data), "هر 6 ساعت")

    def test_daily_picks_allowed_weekday_only(self):
        # 2026-11-06 is a Friday; weekdays=[شنبه] -> next Saturday 08:30 Tehran.
        data = AutomationCreate(name="گزارش صبح", prompt="گزارش صبحگاهی بده", schedule_type="daily",
                                daily_time="08:30", weekdays=[5])
        now = datetime(2026, 11, 6, 10, 0, tzinfo=IRAN_TIMEZONE)
        nxt = compute_next_run(data, now)
        self.assertEqual((nxt.hour, nxt.minute), (8, 30))
        self.assertEqual(nxt.weekday(), 5)
        self.assertGreater(nxt, now)

    def test_daily_defaults_to_every_day(self):
        data = AutomationCreate(name="گزارش شب", prompt="خلاصهٔ روز بده", schedule_type="daily", daily_time="21:00")
        now = datetime(2026, 11, 6, 22, 0, tzinfo=IRAN_TIMEZONE)
        self.assertEqual(compute_next_run(data, now), datetime(2026, 11, 7, 21, 0, tzinfo=IRAN_TIMEZONE))

    def test_schedule_validation(self):
        with self.assertRaises(HTTPException):
            aa._validate_schedule(AutomationCreate(name="بدون ساعت", prompt="گزارش بده", schedule_type="interval"))
        with self.assertRaises(HTTPException):
            aa._validate_schedule(AutomationCreate(name="بدون زمان", prompt="گزارش بده", schedule_type="daily"))
        with self.assertRaises(ValidationError):
            AutomationCreate(name="نام", prompt="گزارش بده", interval_hours=200)
        with self.assertRaises(ValidationError):
            AutomationCreate(name="نام", prompt="گزارش بده", schedule_type="daily", daily_time="25:00")
        with self.assertRaises(ValidationError):
            AutomationCreate(name="نام", prompt="گزارش بده", schedule_type="daily", daily_time="08:00", weekdays=[9])


class AccessTests(unittest.TestCase):
    def test_only_ceo_manages_automations(self):
        for actor in (SALES, None, {}):
            with self.assertRaises(HTTPException) as caught:
                aa._ceo(actor)
            self.assertEqual(caught.exception.status_code, 403)
        aa._ceo(CEO)  # must not raise

    def test_scheduler_disabled_in_test_env(self):
        with patch.dict("os.environ", {"KIARAD_TEST_AUTOMATIONS_DB": "1"}):
            self.assertTrue(aa._testing_env())
            self.assertEqual(aa.start_automations_scheduler(), {"enabled": False})

    def test_scheduler_respects_disable_flag(self):
        with patch.dict("os.environ", {"KIARAD_AUTOMATIONS_DISABLED": "1"}):
            self.assertEqual(aa.start_automations_scheduler(), {"enabled": False})


class FakeResult:
    def __init__(self, row=None, scalar=0):
        self._row = row
        self._scalar = scalar
    def scalar(self):
        return self._scalar
    def mappings(self):
        return self
    def first(self):
        return self._row
    def all(self):
        return []


class FakeConn:
    def __init__(self, row=None):
        self._row = row
    def execute(self, *a, **k):
        return FakeResult(row=self._row, scalar=5)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


ROW = {"id": 1, "owner_user_id": 1, "name": "گزارش", "prompt": "خلاصهٔ فروش بده",
       "schedule_type": "interval", "interval_hours": 6, "daily_time": None, "weekdays": None,
       "next_run_at": None, "enabled": True}


class RunnerTests(unittest.TestCase):
    """The runner must only ever read tools and create proposals — never execute writes."""

    def _patch_storage(self):
        return patch.object(aa, "engine")

    def test_run_records_plain_answer(self):
        with self._patch_storage() as fake_engine, \
             patch("assistant_engine.build_live_context", return_value={}), \
             patch("assistant_engine.call_gpt", return_value="فروش امروز ۱۲ سفارش بود."):
            fake_engine.connect.return_value = FakeConn(ROW)
            fake_engine.begin.return_value = FakeConn()
            with patch.object(aa, "ensure"), patch.object(aa, "text", side_effect=lambda q: q):
                result = aa.run_automation(1, dict(CEO))
        self.assertEqual(result["status"], "completed")
        self.assertIn("فروش امروز", result["summary"])
        self.assertEqual(result["proposals"], [])

    def test_run_captures_proposal_without_executing(self):
        llm = {"answer": "پیشنهاد آماده شد.", "mode": "operation_preview",
               "action": {"label": "بررسی و تأیید", "href": "/assistant-actions?id=abc"}}
        with self._patch_storage() as fake_engine, \
             patch("assistant_engine.build_live_context", return_value={}), \
             patch("assistant_engine.call_gpt", return_value=llm):
            fake_engine.connect.return_value = FakeConn(ROW)
            fake_engine.begin.return_value = FakeConn()
            with patch.object(aa, "ensure"), patch.object(aa, "text", side_effect=lambda q: q):
                result = aa.run_automation(1, dict(CEO))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["proposals"]), 1)
        self.assertEqual(result["proposals"][0]["href"], "/assistant-actions?id=abc")

    def test_llm_failure_is_explicit_not_zero(self):
        with self._patch_storage() as fake_engine, \
             patch("assistant_engine.build_live_context", return_value={}), \
             patch("assistant_engine.call_gpt", return_value=None):
            fake_engine.connect.return_value = FakeConn(ROW)
            fake_engine.begin.return_value = FakeConn()
            with patch.object(aa, "ensure"), patch.object(aa, "text", side_effect=lambda q: q):
                result = aa.run_automation(1, dict(CEO))
        self.assertEqual(result["status"], "no_answer")
        self.assertIn("نامعلوم", result["summary"])

    def test_scheduler_path_uses_proposal_runner(self):
        """_run_due must go through run_automation (proposal-only), never a command executor."""
        called = {}
        with patch.object(aa, "run_automation", side_effect=lambda i, u, trigger="scheduled": called.update(id=i, trigger=trigger) or {}), \
             patch.object(aa, "conn_owner", return_value=dict(CEO)):
            with self._patch_storage() as fake_engine:
                fake_engine.begin.return_value = FakeConn(ROW)
                with patch.object(aa, "ensure"), patch.object(aa, "text", side_effect=lambda q: q):
                    aa._run_due(1)
        self.assertEqual(called, {"id": 1, "trigger": "scheduled"})


if __name__ == "__main__":
    unittest.main()
