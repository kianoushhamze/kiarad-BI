import unittest
from unittest.mock import patch
from fastapi import HTTPException
import field_intelligence as intel
from public_registry_review import review_registry


class PublicRegistryReviewTests(unittest.TestCase):
    def setUp(self):
        self.dataset={'observed_at':'2026-10-27','notice':'source rows only','batches':[{'id':'a'},{'id':'b'}],
                      'items':[{'source_id':'a:1','batch_id':'a','name':'داروخانه رازی','city':'کرمان','phone':'03412345678','address':'الف'},
                               {'source_id':'b:1','batch_id':'b','name':'رازي','city':'کرمان','address':'دیگر'},
                               {'source_id':'b:2','batch_id':'b','name':'داروخانه رازی','city':'بم','phone':'12345678'}]}
        self.customers=[{'id':1,'name':'داروخانه رازي','city':'كرمان','phone':'۰۳۴۱۲۳۴۵۶۷۸'},
                        {'id':2,'name':'نام دیگر','city':'بم','phone':'03412345678'}]

    def test_possible_matches_never_confirm_or_merge_source_rows(self):
        report=review_registry(self.dataset,self.customers,{1:{'source':'pharmacies','id':10}})
        self.assertEqual(report['total_source_rows'],3)
        self.assertEqual(report['rows_with_possible_matches'],2)
        self.assertEqual(len(report['items'][0]['possible_matches']),2)
        self.assertFalse(report['automatic_customer_import'])
        self.assertIsNone(report['province_coverage_percent'])
        self.assertTrue(all(not item['identity_confirmed'] for item in report['items']))
        self.assertEqual(report['items'][1]['possible_matches'][0]['base']['id'],10)
        self.assertEqual(report['items'][2]['possible_matches'],[])

    def test_pagination_and_partial_search_do_not_change_global_counts(self):
        report=review_registry(self.dataset,self.customers,{},q='رازي كرمان',batch='b',offset=0,limit=1)
        self.assertEqual(report['total_source_rows'],3)
        self.assertEqual(report['total_matches'],1)
        self.assertEqual(report['items'][0]['source_id'],'b:1')
        self.assertEqual(review_registry(self.dataset,[],{},offset=2,limit=1)['items'][0]['source_id'],'b:2')

    def test_staff_denied_before_loading_public_or_customer_data(self):
        with patch.object(intel,'load_registry') as load,patch.object(intel,'engine') as engine:
            for role in ('visitor','salesperson','finance'):
                with self.assertRaises(HTTPException) as error:intel.public_registry(user={'id':2,'role':role})
                self.assertEqual(error.exception.status_code,403)
            load.assert_not_called();engine.begin.assert_not_called()
