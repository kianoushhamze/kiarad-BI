"""No real threads, ERP calls, or production changes."""
from copy import deepcopy
import os
import unittest
from unittest.mock import Mock, patch
import holoo_finance_jobs as jobs
import holoo_finance as finance


class AutomaticRefreshTests(unittest.TestCase):
    def setUp(self):
        self.auto=deepcopy(jobs._AUTO)
        self.state=deepcopy(jobs._STATE)
        self.thread=jobs._THREAD
        self.addCleanup(self.restore)

    def restore(self):
        jobs._AUTO.clear();jobs._AUTO.update(self.auto)
        jobs._STATE.clear();jobs._STATE.update(self.state)
        jobs._THREAD=self.thread

    def test_disabled_missing_url_and_test_mode_never_enable(self):
        for env in ({},{'HOLO_AUTO_REFRESH_ENABLED':'1'}, {'HOLO_AUTO_REFRESH_ENABLED':'1','HOLO_API_URL':'http://synthetic','KIARAD_TEST_ANY_DB':'1'}):
            with patch.dict(os.environ,env,clear=True):self.assertFalse(jobs.automatic_config()[0])

    def test_interval_is_bounded_and_invalid_value_has_safe_default(self):
        for raw,expected in [('1',300),('600',600),('999999',86400),('bad',300)]:
            with patch.dict(os.environ,{'HOLO_AUTO_REFRESH_ENABLED':'1','HOLO_API_URL':'http://synthetic','HOLO_AUTO_REFRESH_SECONDS':raw},clear=True):
                self.assertEqual(jobs.automatic_config(),(True,expected))

    def test_start_is_idempotent_and_disabled_does_not_create_thread(self):
        jobs._THREAD=None
        with patch.object(jobs,'automatic_config',return_value=(False,300)),patch.object(jobs,'Thread') as factory:
            jobs.start_automatic_refresh();factory.assert_not_called()
        with patch.object(jobs,'automatic_config',return_value=(True,300)),patch.object(jobs,'Thread') as factory:
            factory.return_value.is_alive.return_value=True
            jobs.start_automatic_refresh();jobs.start_automatic_refresh()
            factory.assert_called_once();factory.return_value.start.assert_called_once()
            self.assertTrue(jobs.automatic_refresh_status()['running'])

    def test_transient_failure_retries_and_stop_clears_next_attempt(self):
        stop=Mock();stop.is_set.side_effect=[False,False];stop.wait.side_effect=[False,True]
        with patch.object(jobs,'_STOP',stop),patch.object(jobs,'start_financial_refresh',side_effect=[RuntimeError('private'),{}]) as refresh:
            jobs._automatic_loop(300)
        self.assertEqual(refresh.call_count,2)
        self.assertEqual(stop.wait.call_args.args,(300,))
        self.assertFalse(jobs.automatic_refresh_status()['running'])
        self.assertIsNone(jobs.automatic_refresh_status()['next_attempt_at'])

    def test_unsuccessful_run_backs_off_before_the_next_attempt(self):
        jobs._STATE.update(status='partial',sources=[],snapshot_id=None)
        stop=Mock();stop.is_set.side_effect=[False,True];stop.wait.return_value=True
        with patch.object(jobs,'_STOP',stop),patch.object(jobs,'start_financial_refresh',return_value={}):
            jobs._automatic_loop(300)
        self.assertEqual(stop.wait.call_args.args,(900,))

    def test_completed_run_keeps_the_configured_interval(self):
        jobs._STATE.update(status='completed',sources=[],snapshot_id=None)
        stop=Mock();stop.is_set.side_effect=[False,True];stop.wait.return_value=True
        with patch.object(jobs,'_STOP',stop),patch.object(jobs,'start_financial_refresh',return_value={}):
            jobs._automatic_loop(300)
        self.assertEqual(stop.wait.call_args.args,(300,))

    def test_public_status_is_detached_and_contains_no_environment_secrets(self):
        jobs._AUTO.update(enabled=True,running=True)
        value=jobs.financial_refresh_status();value['automatic']['enabled']=False
        self.assertTrue(jobs.automatic_refresh_status()['enabled'])
        self.assertNotIn('HOLO_PASSWORD',repr(value))

    def test_cross_process_busy_never_calls_holoo_and_releases_local_lock(self):
        lease=Mock();lease.execution_options.return_value=lease
        lease.execute.return_value.scalar.return_value=False
        with patch.object(finance.engine,'connect',return_value=lease),patch.object(finance,'login_holoo') as login:
            with self.assertRaises(RuntimeError):finance.refresh_financial_snapshot()
            login.assert_not_called();lease.close.assert_called_once()
        self.assertFalse(finance.REFRESH_LOCK.locked())

    def test_login_failure_releases_database_and_process_lock(self):
        lease=Mock();lease.execution_options.return_value=lease
        lease.execute.return_value.scalar.return_value=True
        with patch.object(finance.engine,'connect',return_value=lease):
            with self.assertRaises(ValueError):finance.refresh_financial_snapshot(login=Mock(side_effect=ValueError('synthetic')))
        self.assertEqual(lease.execute.call_count,2)
        lease.close.assert_called_once()
        self.assertFalse(finance.REFRESH_LOCK.locked())
