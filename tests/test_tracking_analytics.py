import unittest
from datetime import datetime,timedelta,timezone
from tracking_analytics import summarize
class TrackingAnalyticsTests(unittest.TestCase):
 def setUp(self):
  self.begin=datetime(2026,11,12,6,tzinfo=timezone.utc);self.end=self.begin+timedelta(hours=1)
  self.sessions=[dict(id='s1',started_at=self.begin,ended_at=None,expires_at=self.end)]
  self.base=dict(source='pharmacies',id=1,name='Test',latitude=30,longitude=57,visit_radius_m=150)
 def points(self,seconds,**overrides):return [dict(id=i,session_id='s1',recorded_at=self.begin+timedelta(seconds=n),latitude=30,longitude=57,accuracy_m=5,mocked=False,**overrides) for i,n in enumerate(seconds)]
 def run_report(self,p,b=None):return summarize(p,b or [self.base],self.sessions,begin=self.begin,end=self.end)
 def test_consecutive_points_support_stop_not_visit(self):
  r=self.run_report(self.points(range(0,361,30)));self.assertEqual(r['observed_interval_seconds'],360);self.assertEqual(len(r['stops']),1);self.assertEqual(r['unknown_seconds'],3240);self.assertTrue(r['unknown_is_not_idle'])
 def test_long_gap_is_not_credited(self):
  r=self.run_report(self.points([0,30,1800,1830]));self.assertEqual(r['observed_interval_seconds'],60);self.assertEqual(len(r['stops']),0);self.assertEqual(r['telemetry_gap_seconds'],1770)
 def test_bad_fix_breaks_interval_not_interpolated(self):
  p=self.points([0,30,60]);p[1]['accuracy_m']=300;r=self.run_report(p);self.assertEqual(r['observed_interval_seconds'],0);self.assertEqual(r['excluded_samples'],1)
 def test_mocked_fix_is_excluded(self):
  p=self.points([0,30]);p[1]['mocked']=True;self.assertEqual(self.run_report(p)['observed_interval_seconds'],0)
 def test_two_overlapping_bases_do_not_get_double_credit(self):
  r=self.run_report(self.points(range(0,361,30)),[self.base,{**self.base,'id':2}]);self.assertEqual(r['ambiguous_samples'],13);self.assertEqual(len(r['stops']),0);self.assertEqual(sum(b['observed_dwell_seconds'] for b in r['bases']),0)
 def test_accuracy_circle_must_be_contained(self):
  p=self.points([0,30]);p[0]['latitude']+=.0013;p[1]['latitude']+=.0013;p[0]['accuracy_m']=50;p[1]['accuracy_m']=50;r=self.run_report(p);self.assertEqual(r['bases'][0]['observed_dwell_seconds'],0)
 def test_session_boundaries_are_not_travel(self):
  p=self.points([0,30]);p[1]['session_id']='s2';self.assertEqual(self.run_report(p)['observed_interval_seconds'],0)
 def test_implausible_speed_is_flagged(self):
  p=self.points([0,30]);p[1]['latitude']=31;r=self.run_report(p);self.assertEqual(r['implausible_segments'],1);self.assertEqual(r['straight_line_travel_km'],0)
 def test_missing_coordinates_are_reported(self):
  r=self.run_report([], [{**self.base,'latitude':None}]);self.assertEqual(len(r['missing_coordinates']),1);self.assertEqual(r['coverage_ratio'],0)
 def test_no_session_is_unknown_not_a_workday(self):
  self.sessions=[];r=self.run_report([]);self.assertIsNone(r['coverage_ratio']);self.assertEqual(r['shift_window_seconds'],0)
