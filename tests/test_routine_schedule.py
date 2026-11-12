import unittest
from datetime import datetime,timezone
from pydantic import ValidationError
from agent_routines import Schedule,Routine,next_time,auto_scope
class RoutineScheduleTests(unittest.TestCase):
 def test_daily_uses_tehran_time(self):
  value=next_time({'kind':'daily','local_time':'08:30'},datetime(2026,11,12,4,0,tzinfo=timezone.utc));self.assertEqual(value,datetime(2026,11,12,5,0,tzinfo=timezone.utc))
 def test_daily_after_time_moves_forward(self):
  value=next_time({'kind':'daily','local_time':'08:30'},datetime(2026,11,12,6,0,tzinfo=timezone.utc));self.assertEqual(value,datetime(2026,11,13,5,0,tzinfo=timezone.utc))
 def test_monthly_default_is_jalali(self):
  value=next_time({'kind':'monthly','month_day':1,'local_time':'08:30'},datetime(2026,11,20,12,tzinfo=timezone.utc));self.assertEqual(value,datetime(2026,11,22,5,tzinfo=timezone.utc))
 def test_gregorian_monthly_clamps_short_month(self):
  value=next_time({'kind':'monthly','calendar':'gregorian','month_day':31,'local_time':'08:30'},datetime(2027,2,1,12,tzinfo=timezone.utc));self.assertEqual(value,datetime(2027,2,28,5,tzinfo=timezone.utc))
 def test_discovery_frequency_capped(self):
  with self.assertRaises(ValidationError):Routine(name='Test',kind='lead_discovery',schedule={'kind':'interval','interval_hours':6},recipe={})
 def test_message_template_is_closed(self):
  for body in ['{customer_name.__class__}','{amount}','{customer_name!r}','{customer_name:100000000}']:
   with self.assertRaises(ValidationError):Routine(name='Test',kind='customer_messages',recipe={'contact_ids':['00000000-0000-0000-0000-000000000001'],'purpose':'service','body':body})
 def test_autoscope_rejects_finance_and_other_people(self):
  recipe={'allowed_user_ids':[2],'daily_action_limit':20}
  self.assertFalse(auto_scope({'steps':[{'operation':'enter_targets','payload':{}}]},recipe))
  self.assertFalse(auto_scope({'steps':[{'operation':'create_task','payload':{'assigned_to':3}}]},recipe))
  self.assertTrue(auto_scope({'steps':[{'operation':'create_task','payload':{'assigned_to':2}}]},recipe))
 def test_route_recipe_cannot_override_recurring_calendar(self):
  with self.assertRaises(ValidationError):Routine(name='Routes',kind='monthly_routes',recipe={'routing':{'month':'1405-09'}})
