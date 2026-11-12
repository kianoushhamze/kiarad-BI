import unittest
from datetime import date,timedelta
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from specialist_workflows import TargetScenario,target_math,validate_citations
class SpecialistTests(unittest.TestCase):
 def setUp(self):self.today=date(2026,11,12);self.request=TargetScenario(salesperson_id=1,product_id=1,start_date=self.today+timedelta(days=1),end_date=self.today+timedelta(days=30))
 def test_missing_history_does_not_become_zero_target(self):
  r=target_math([],100,5,self.request,today=self.today);self.assertIsNone(r['scenarios'][0]['suggested_units']);self.assertIsNone(r['scenarios'][0]['amount_irr']);self.assertFalse(r['automatic_financial_write'])
 def test_missing_capacity_is_unknown(self):
  r=target_math([{'date':self.today,'quantity':10,'price':100}],100,5,self.request,today=self.today);self.assertIsNone(r['scenarios'][0]['within_confirmed_capacity'])
 def test_historical_units_and_money_are_separate(self):
  rows=[{'date':self.today-timedelta(days=i),'quantity':10,'price':100} for i in range(365)];r=target_math(rows,200,10,self.request,today=self.today);self.assertEqual(r['recorded_positive_units'],'3650');self.assertEqual(r['recorded_positive_sales_irr'],'365000');self.assertFalse(r['profit_assessed']);self.assertEqual(r['scenarios'][1]['suggested_units'],'300.00');self.assertEqual(r['scenarios'][1]['amount_irr'],'60000')
 def test_negative_future_and_nan_rows_excluded(self):
  rows=[{'date':self.today+timedelta(days=1),'quantity':100,'price':10},{'date':self.today,'quantity':-2,'price':10},{'date':self.today,'quantity':float('nan'),'price':10}];r=target_math(rows,200,10,self.request,today=self.today);self.assertEqual(r['excluded_rows'],3);self.assertEqual(r['recorded_positive_units'],'0')
 def test_inflation_requires_explicit_source(self):
  with self.assertRaises(ValidationError):TargetScenario(salesperson_id=1,product_id=1,start_date=self.today,end_date=self.today,inflation_rate=Decimal('.4'))
 def test_contract_quote_must_exist(self):
  with self.assertRaises(HTTPException):validate_citations({'obligations':[{'summary':'An invented obligation','clause_quote':'Invented source clause'}]},'Real contract text only')
 def test_valid_quote_is_still_not_legal_decision(self):
  report=validate_citations({'summary':'Review','obligations':[{'summary':'Pay invoice after review','clause_quote':'The invoice is payable in30 days.','deadline_suggestion':'2026-12-01'}]},'Contract. The invoice is payable in30 days. End.');self.assertFalse(report['legal_decision_made']);self.assertFalse(report['obligations'][0]['deadline_confirmed'])
