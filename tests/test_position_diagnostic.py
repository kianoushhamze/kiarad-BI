"""Position diagnostic validation only; no physical or operational location writes."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from fastapi import HTTPException
import compensation
from iran_time import IRAN_TIMEZONE


class PositionDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,18,18,0,tzinfo=IRAN_TIMEZONE)
        self.user = {'id':991,'role':'ceo'}
        for patcher in (patch.object(compensation,'iran_now',return_value=self.now),
                        patch.object(compensation,'get_connection',side_effect=AssertionError('No database writes')),
                        patch.dict(compensation._POSITION_CHECK_RESULTS,{},clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def data(self, **changes):
        return {'lat':30,'lng':57,'accuracy_m':20,'observed_at':self.now.isoformat(),**changes}

    def test_fresh_diagnostic_returns_times_and_precision_without_coordinates(self):
        result=compensation.check_device_position(self.data(),self.user)
        self.assertTrue(result['ok'])
        self.assertEqual(result['accuracy_m'],20)
        self.assertNotIn('lat',result)
        self.assertNotIn('lng',result)
        self.assertEqual(compensation.device_position_check_result(self.user),result)

    def test_another_user_cannot_read_diagnostic_result(self):
        compensation.check_device_position(self.data(),self.user)
        self.assertEqual(compensation.device_position_check_result({'id':992}),{'ok':False,'state':'not_tested'})

    def test_stale_future_and_naive_timestamps_are_rejected(self):
        for stamp in [(self.now-timedelta(minutes=3)).isoformat(),(self.now+timedelta(minutes=1)).isoformat(),
                      '2026-10-18T18:00:00','invalid',None]:
            with self.subTest(stamp=stamp),self.assertRaises(HTTPException) as error:
                compensation.check_device_position(self.data(observed_at=stamp),self.user)
            self.assertEqual(error.exception.status_code,422)
        self.assertFalse(compensation.device_position_check_result(self.user)['ok'])

    def test_nonfinite_out_of_bounds_and_missing_accuracy_are_rejected(self):
        for change in [{'lat':'NaN'},{'lng':181},{'lat':True},{'accuracy_m':None},{'accuracy_m':0}]:
            with self.subTest(change=change),self.assertRaises(HTTPException) as error:
                compensation.check_device_position(self.data(**change),self.user)
            self.assertEqual(error.exception.status_code,422)


if __name__=='__main__':
    unittest.main()
