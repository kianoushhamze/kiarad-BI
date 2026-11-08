import unittest
from unittest.mock import patch
import registry_source_jobs as jobs


class RefreshRecovery(unittest.TestCase):
    def test_failed_start_releases_job_lock(self):
        with patch.object(jobs,'write_status',side_effect=OSError('test')):
            with self.assertRaises(OSError):jobs.start()
        self.assertFalse(jobs.JOB_LOCK.locked())

    def test_stopped_process_is_not_reported_as_running(self):
        with patch.object(jobs.STATUS_FILE.__class__,'is_file',return_value=True),patch.object(jobs.STATUS_FILE.__class__,'read_text',return_value='{"status":"running","sources":[]}'):
            self.assertEqual(jobs.status()['status'],'interrupted')
