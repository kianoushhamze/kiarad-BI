"""Synthetic refresh state checks; no threads, network or ERP mutation."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
import holoo_finance_jobs as jobs


class FinanceRefreshJobTests(unittest.TestCase):
    def setUp(self):
        projection=patch.object(jobs,'sync_operational_snapshot',return_value={'status':'completed'})
        projection.start();self.addCleanup(projection.stop)
        self.old = deepcopy(jobs._STATE)
        jobs._STATE.clear()
        jobs._STATE.update(status="idle", sources=[], snapshot_id=None)
        self.addCleanup(self.restore)

    def restore(self):
        jobs._STATE.clear()
        jobs._STATE.update(self.old)

    def test_only_one_job_can_be_queued(self):
        with patch.object(jobs._POOL, "submit") as submit:
            self.assertEqual(jobs.start_financial_refresh()["status"], "running")
            self.assertTrue(jobs.start_financial_refresh()["already_running"])
            submit.assert_called_once()

    def test_stale_running_job_is_discarded_and_restarted(self):
        with patch.object(jobs._POOL, "submit") as submit:
            jobs._STATE.clear()
            jobs._STATE.update(status="running", started_at="2020-01-01T00:00:00+00:00", sources=[], snapshot_id=None)
            result = jobs.start_financial_refresh()
            self.assertEqual(result["status"], "running")
            self.assertTrue(result.get("stale_run_discarded"))
            submit.assert_called_once()

    def test_running_job_inside_the_window_is_not_restarted(self):
        from datetime import datetime, timezone
        with patch.object(jobs._POOL, "submit") as submit:
            jobs._STATE.clear()
            jobs._STATE.update(status="running", started_at=datetime.now(timezone.utc).isoformat(), sources=[], snapshot_id=None)
            self.assertTrue(jobs.start_financial_refresh()["already_running"])
            submit.assert_not_called()

    def test_status_is_detached(self):
        jobs._STATE["sources"].append({"kind": "banks", "count": 1})
        result = jobs.financial_refresh_status()
        result["sources"][0]["count"] = 999
        self.assertEqual(jobs._STATE["sources"][0]["count"], 1)

    def test_complete_job_exposes_only_safe_source_counts(self):
        def refresh(progress):
            progress("banks", {"ok": True, "complete": True, "rows": [{"private": "never expose"}]})
            return {"id": 9, "currency_verified": True, "sources": [{"ok": True, "complete": True}]}
        with patch.object(jobs, "refresh_financial_snapshot", side_effect=refresh):
            jobs._run_refresh()
        result = jobs.financial_refresh_status()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["snapshot_id"], 9)
        self.assertNotIn("private", repr(result))

    def test_partial_currency_or_source_is_not_complete(self):
        for value in ({"id": 7, "currency_verified": False, "sources": []}, {"id": 8, "currency_verified": True, "sources": [{"ok": True, "complete": False}]}):
            with patch.object(jobs, "refresh_financial_snapshot", return_value=value):
                jobs._run_refresh()
            self.assertEqual(jobs.financial_refresh_status()["status"], "partial")

    def test_failed_job_never_exposes_upstream_exception(self):
        with patch.object(jobs, "refresh_financial_snapshot", side_effect=RuntimeError("private-token-DO-NOT-EXPOSE")):
            jobs._run_refresh()
        self.assertEqual(jobs.financial_refresh_status()["status"], "failed")
        self.assertNotIn("private-token", repr(jobs.financial_refresh_status()))

    def test_submit_failure_releases_running_state(self):
        with patch.object(jobs._POOL, "submit", side_effect=RuntimeError("private")):
            self.assertEqual(jobs.start_financial_refresh()["status"], "failed")

    def test_operational_failure_never_claims_complete_sync(self):
        with patch.object(jobs,'refresh_financial_snapshot',return_value={'id':8,'currency_verified':True,'sources':[{'ok':True,'complete':True}]}),patch.object(jobs,'sync_operational_snapshot',side_effect=RuntimeError('private')):
            jobs._run_refresh()
        result=jobs.financial_refresh_status()
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['operational']['status'],'failed')
        self.assertNotIn('private',repr(result))

