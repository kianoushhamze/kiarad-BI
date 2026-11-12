import unittest
from datetime import date
from specialist_monitor import pace
class PaceTests(unittest.TestCase):
 def target(self):return {'start_date':date(2026,11,1),'end_date':date(2026,11,30),'target_amount':3000}
 def test_unfinished_today_not_counted(self):
  r=pace(self.target(),1000,date(2026,11,12));self.assertEqual(r['elapsed_days'],11);self.assertEqual(r['expected_percent'],'36.7')
 def test_missing_sales_remain_unknown(self):self.assertFalse(pace(self.target(),None,date(2026,11,12))['assessable'])
 def test_actual_zero_is_assessable_behind_without_discipline(self):
  r=pace(self.target(),0,date(2026,11,12));self.assertTrue(r['behind_pace']);self.assertFalse(r['disciplinary_finding'])
 def test_first_two_days_not_alerted(self):self.assertFalse(pace(self.target(),0,date(2026,11,3))['behind_pace'])
 def test_invalid_date_target_is_unknown(self):
  t=self.target();t['end_date']=date(2026,10,1);self.assertFalse(pace(t,0,date(2026,11,12))['assessable'])
 def test_overachievement_not_behind(self):self.assertFalse(pace(self.target(),4000,date(2026,12,1))['behind_pace'])
