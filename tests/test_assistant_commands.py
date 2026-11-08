import unittest
from unittest.mock import patch
from fastapi import HTTPException
from assistant_commands import COMMANDS,catalog,prepare,execute,path_for,authorize

CEO={'id':1,'role':'ceo'}


class CommandTests(unittest.TestCase):
    def test_all_commands_have_real_route_schema(self):
        for name in COMMANDS:
            with self.subTest(operation=name):
                self.assertEqual(catalog(CEO,operation=name)['operations'][0]['operation'],name)

    def test_staff_cannot_prepare_financial_writes(self):
        for name,spec in COMMANDS.items():
            if spec['module']=='treasury':
                with self.subTest(operation=name),self.assertRaises(HTTPException):
                    authorize(name,{'id':2,'role':'salesperson'})

    def test_no_arbitrary_url_or_path_parameters(self):
        with self.assertRaises(HTTPException):authorize('https://example.org',CEO)
        for params in ({'product_id':'../users'},{'product_id':True},{'product_id':1,'url':'https://example.org'}):
            with self.subTest(params=params),self.assertRaises(HTTPException):path_for(COMMANDS['catalog_update_product'],params)

    def test_unknown_fields_and_invalid_amount_fail_before_snapshot(self):
        for body in ({'price':-1},{'price':1,'is_admin':True}):
            with patch('assistant_commands.before_state') as state:
                with self.assertRaises(HTTPException):prepare('catalog_update_product',{'body':body,'path_params':{'product_id':1}},CEO)
                state.assert_not_called()

    def test_changed_record_is_not_executed(self):
        with patch('assistant_commands.before_state',return_value={'price':2}),patch('assistant_commands.dispatch') as request:
            with self.assertRaises(HTTPException) as error:
                execute('catalog_update_product',{'body':{'price':3},'path_params':{'product_id':1}},{'before_hash':'old'},CEO)
            self.assertEqual(error.exception.status_code,409)
            request.assert_not_called()

    def test_invalid_campaign_is_not_prepared(self):
        with self.assertRaises(HTTPException):
            prepare('campaign_create',{'body':{'title':'آزمون','starts_at':'2026-11-10','ends_at':'2026-11-01','target_amount':100,'reward_type':'fixed','reward_value':10}},CEO)
