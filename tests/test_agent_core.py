"""Deterministic policy and routing regressions; no external model calls."""
import unittest
from datetime import date,datetime,timedelta,timezone
from pydantic import ValidationError
from agent_center import Mission,automatic,resolve_refs,digest
from agent_route_planner import RoutePolicy,build_routes
from live_tracking import Sample,freshness
class AgentCoreTests(unittest.TestCase):
 def test_unknown_operation_and_forward_dependency_rejected(self):
  for steps in [[dict(key='a',title='Test',operation='run_sql')],[dict(key='a',title='Test',operation='analyze_domain',depends_on=['b'])]]:
   with self.assertRaises(ValidationError):Mission(title='Test',objective='Testing',domains=['sales'],steps=steps)
 def test_domains_are_allowlisted(self):
  with self.assertRaises(ValidationError):Mission(title='Test',objective='Testing',domains=['root'],steps=[dict(key='a',title='Test',operation='analyze_domain')])
 def test_financial_writes_never_automatic(self):
  for op in ['enter_targets','treasury_create_payment','save_contract','payroll_run']:
   self.assertFalse(automatic({'operation':op,'payload':{}},{'mode':'bounded_auto','allow_route_publication':True}))
 def test_notification_policy_is_explicit(self):
  self.assertFalse(automatic({'operation':'notify_user'}, {'mode':'bounded_auto','notify_employees':False}))
 def test_publication_requires_receipt_reference(self):
  policy={'mode':'bounded_auto','allow_route_publication':True}
  self.assertFalse(automatic({'operation':'monthly_plan_review','payload':{'body':{'decision':'approved'},'path_params':{'ident':42}}},policy))
 def test_reference_must_be_declared(self):
  self.assertEqual(resolve_refs({'$ref':'created.id'},{'created':{'id':17}},['created']),17)
  with self.assertRaises(Exception):resolve_refs({'$ref':'created.id'},{'created':{'id':17}},[])
 def test_digest_order_independent_but_content_sensitive(self):
  self.assertEqual(digest({'a':1,'b':2}),digest({'b':2,'a':1}))
  self.assertNotEqual(digest({'a':1}),digest({'a':2}))
 def test_backfill_is_stale_and_bad_accuracy_never_live(self):
  now=datetime.now(timezone.utc)
  self.assertFalse(freshness({'recorded_at':now-timedelta(hours=1),'accuracy_m':5},now)['is_live'])
  self.assertFalse(freshness({'recorded_at':now,'accuracy_m':200},now)['is_live'])
  self.assertFalse(freshness({'recorded_at':now,'accuracy_m':5,'mocked':True},now)['is_live'])
  self.assertTrue(freshness({'recorded_at':now,'accuracy_m':5},now)['is_live'])
 def test_naive_and_nonfinite_samples_rejected(self):
  from uuid import uuid4
  for stamp,lat in [(datetime.now(),30),(datetime.now(timezone.utc),float('nan'))]:
   with self.assertRaises(ValidationError):Sample(event_id=uuid4(),recorded_at=stamp,latitude=lat,longitude=57,accuracy_m=4)
 def policy(self,**kw):
  return RoutePolicy(user_ids=[2],month='1405-09',dates=[date(2026,11,23),date(2026,12,7)],depot_latitude=30.29,depot_longitude=57.06,**kw)
 def test_two_cycles_and_unique_daily_stops(self):
  bases=[dict(source='pharmacies',id=i,name=str(i),latitude=30.29+i*.0001,longitude=57.06) for i in range(1,11)]
  result=build_routes(bases,self.policy(),today=date(2026,11,12))
  self.assertTrue(result['feasible'])
  self.assertEqual(result['scheduled_visits'],20)
  for route in result['routes']:
   self.assertLessEqual(len(route['stops']),10)
   self.assertEqual(len({s['base_id'] for s in route['stops']}),len(route['stops']))
 def test_missing_coordinates_blocks_complete_coverage(self):
  result=build_routes([dict(source='pharmacies',id=1,name='Missing',latitude=None,longitude=None)],self.policy(),today=date(2026,11,12))
  self.assertFalse(result['feasible'])
 def test_capacity_not_invented(self):
  bases=[dict(source='pharmacies',id=i,name=str(i),latitude=30.29,longitude=57.06) for i in range(30)]
  result=build_routes(bases,self.policy(),today=date(2026,11,12))
  self.assertFalse(result['feasible'])
 def test_month_and_dates_must_agree(self):
  with self.assertRaises(ValidationError):RoutePolicy(user_ids=[2],month='1405-09',dates=[date(2027,1,1)],depot_latitude=30, depot_longitude=57)
