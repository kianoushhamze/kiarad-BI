from datetime import date
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text

import assistant_engine
from assistant_commands import COMMANDS, prepare as prepare_command
from assistant_intake import blank_target_template, prepare_sales_targets, prepare_visit_coverage
from assistant_reports import execute_report_tool


MANAGER = {'id': 1, 'role': 'ceo'}
PREVIEW = {'status': 'operation_preview', 'review_href': '/assistant-actions?id=test', 'message': 'پیشنهاد آماده است.'}


class SemanticToolsTests(unittest.TestCase):
    def setUp(self):
        self.database = create_engine('sqlite://')
        self.addCleanup(self.database.dispose)
        with self.database.begin() as conn:
            conn.execute(text('CREATE TABLE salespersons (id INTEGER, name TEXT)'))
            conn.execute(text("INSERT INTO salespersons VALUES (6, 'سامان صادق نمونه'), (8, 'مینا نمونه'), (9, 'نیلوفر راد')"))

    def target(self, **extra):
        return {'month': 'اذرماه', 'rows': [{
            'title': 'تارگت لوفنته', 'person': 'سامان نمونه',
            'amount_phrase': '۲ میلیارد ریال', 'reward_phrase': '۲ میلیون تومن', **extra,
        }]}

    @patch('assistant_intake.prepare', return_value=PREVIEW.copy())
    def test_target_normalizes_each_quoted_unit_and_resolves_short_name(self, prepare):
        with patch('assistant_intake.engine', self.database), patch('assistant_intake.iran_today', return_value=date(2026, 11, 24)):
            result = prepare_sales_targets(self.target(), MANAGER,
                'تارگت لوفنته برای سامان نمونه؛ هدف ۲ میلیارد ریال و پاداش ۲ میلیون تومن برای آذر', [])
        self.assertEqual(result['status'], 'operation_preview')
        body = prepare.call_args.args[0]['payload']['body']
        self.assertEqual(body['unit'], 'IRR')
        self.assertEqual(body['rows'], [{
            'title': 'تارگت لوفنته', 'salesperson_id': 6, 'target_amount': '2000000000',
            'bonus_reward': '20000000', 'start_date': '2026-11-22', 'end_date': '2026-12-21',
        }])

    @patch('assistant_intake.prepare')
    def test_old_target_or_inconsistent_brand_does_not_prepare(self, prepare):
        history = [{'role': 'user', 'content': 'تارگت قدیمی برای سامان نمونه ۲ میلیارد ریال'}]
        target = self.target()
        target['rows'].append({'title': 'تارگت قدیمی', 'person': 'سامان نمونه', 'amount_phrase': '۲ میلیارد ریال'})
        message = 'تارگت لوفنته برای سامان نمونه؛ ۲ میلیارد ریال، پاداش ۲ میلیون تومن'
        with patch('assistant_intake.engine', self.database):
            result = prepare_sales_targets(target, MANAGER, message, history)
            conflicting = prepare_sales_targets(self.target(product_focus='لابورن'), MANAGER, message + ' کالای هدف لابورن', [])
        self.assertEqual(result['status'], 'needs_information')
        self.assertIn('برند', conflicting['message'])
        prepare.assert_not_called()

    @patch('assistant_intake.prepare', return_value=PREVIEW.copy())
    @patch('assistant_intake.iran_today', return_value=date(2026, 11, 24))
    def test_shared_unit_and_person_in_a_three_brand_request(self, _today, prepare):
        message = 'برای خانم راد تو آذر از برند سولامور ۱۰۰ میلیون از لوفنته ۱۰۰ میلیون و برای وی ان وی ۲۰۰ میلیون تومن تارگت تعیین کن'
        args = {'month': 'آذر', 'person': 'خانم راد', 'shared_unit': 'تومان', 'rows': [
            {'product_focus': 'سولامور', 'amount_phrase': '۱۰۰ میلیون'},
            {'product_focus': 'لوفنته', 'amount_phrase': '100 میلیون'},
            {'product_focus': 'وی اند وی', 'amount_phrase': '۲۰۰ میلیون تومن'},
        ]}
        with patch('assistant_intake.engine', self.database):
            result = prepare_sales_targets(args, MANAGER, message, [])
            invalid = prepare_sales_targets({**args, 'rows': [
                {'product_focus': 'سولامور', 'amount_phrase': '۱۰۰'}, *args['rows'][1:],
            ]}, MANAGER, message, [])
        self.assertEqual(result['status'], 'operation_preview')
        self.assertEqual(invalid['status'], 'needs_information')
        rows = prepare.call_args.args[0]['payload']['body']['rows']
        self.assertEqual([row['salesperson_id'] for row in rows], [9, 9, 9])
        self.assertEqual([row['target_amount'] for row in rows], ['1000000000', '1000000000', '2000000000'])

    @patch('assistant_intake.prepare', return_value=PREVIEW.copy())
    @patch('assistant_intake.iran_today', return_value=date(2026, 11, 24))
    def test_settlement_target_defaults_to_the_current_month(self, _today, prepare):
        with patch('assistant_intake.engine', self.database):
            result = prepare_sales_targets({'person': 'آقای سامان نمونه', 'rows': [
                {'kind': 'settlement', 'amount_phrase': '۱ میلیارد تومن'},
            ]}, MANAGER, 'برای آقای سامان نمونه ۱ میلیارد تومن تارگت تسویه ایجاد کن', [])
        row = prepare.call_args.args[0]['payload']['body']['rows'][0]
        self.assertEqual(row['target_type'], 'تسویه')
        self.assertEqual(row['target_amount'], '10000000000')
        self.assertIn('1405-09', result['message'])

    def test_twenty_blank_entries_are_a_form_and_require_permissions(self):
        with patch('assistant_intake.prepare') as prepare:
            data = blank_target_template({'rows': 20}, MANAGER)
            denied = execute_report_tool('open_target_template', {'rows': 20}, {'id': 4, 'role': 'visitor'})
        self.assertEqual(data['review_href'], '/data-entry?entity=targets&rows=20')
        self.assertEqual(denied['status'], 'access_denied')
        prepare.assert_not_called()

    @patch('assistant_intake.prepare', return_value=PREVIEW.copy())
    @patch('assistant_intake.iran_today', return_value=date(2026, 11, 24))
    def test_route_resolves_database_bases_and_previews_complete_dates(self, _today, prepare):
        choices = {'users': [{'id': 91, 'full_name': 'سامان صادق نمونه'}], 'bases': [
            {'id': 122, 'name': 'پایگاه الف', 'city': 'شهر کرمان', 'source': 'pharmacies'},
            {'id': 355, 'name': 'پایگاه ب', 'city': 'كرمان', 'source': 'cosmetics_shops'},
            {'id': 311, 'name': 'پایگاه پ', 'city': 'بم', 'source': 'pharmacies'},
        ]}
        local = {'city': 'کرمان', 'scope': 'all_bases', 'visits': 2, 'days': [5, 16]}
        trip = {'city': 'شهرستان بم', 'scope': 'trip', 'visits': 1}
        with patch('assistant_intake.options', return_value=choices):
            partial = prepare_visit_coverage({'person': 'سامان نمونه', 'cities': [local, trip]}, MANAGER)
            prepare.assert_not_called()
            ready = prepare_visit_coverage({'person': 'سامان نمونه', 'cities': [
                local, {**trip, 'base_names': ['پایگاه پ'], 'days': [22]},
            ]}, MANAGER)
        self.assertEqual(partial['coverage'][0]['required_stops'], 4)
        self.assertEqual(partial['coverage'][1]['registered_bases'], 1)
        self.assertEqual(ready['status'], 'operation_preview')
        body = prepare.call_args.args[0]['payload']['body']
        self.assertEqual(body['user_id'], 91)
        self.assertEqual([s['base_id'] for s in body['stops']], [122, 355, 122, 355, 311])
        self.assertEqual(len({s['visit_date'] for s in body['stops']}), 3)

    def test_model_can_choose_tool_with_unexpected_wording(self):
        def complete(payload, _headers):
            self.assertNotIn('tool_choice', payload)
            return {'choices': [{'message': {'tool_calls': [{'id': 'call1', 'type': 'function', 'function': {
                'name': 'open_target_template', 'arguments': json.dumps({'rows': 20}),
            }}]}}]}

        with patch.object(assistant_engine, 'get_env_live', return_value='model'), \
             patch.object(assistant_engine, '_chat_completion', side_effect=complete):
            response = assistant_engine.call_gpt('بیست جای خالی بذار، جزئیاتش با من',
                                                  {'_actor': MANAGER}, [], 'ceo', '')
        self.assertEqual(response['mode'], 'target_template')

    def test_public_search_delegates_to_the_configured_connector(self):
        with patch('agent_center.market_search', return_value={'sources': [{'url': 'https://example.org'}]}) as search:
            data = execute_report_tool('search_public_web', {'query': 'آخرین اخبار اخترشناسی'}, MANAGER)
        search.assert_called_once_with({'query': 'آخرین اخبار اخترشناسی'})
        self.assertEqual(data['sources'][0]['url'], 'https://example.org')

    def test_storefront_patch_preserves_unmentioned_fields(self):
        with patch('assistant_commands.before_state', return_value={'code':'SKU-1'}):
            payload, _ = prepare_command('site_product_update', {
                'path_params': {'code':'SKU-1'}, 'body': {'hidden':True},
            }, MANAGER)
        self.assertEqual(payload['body'], {'hidden':True})

    def test_editing_visitor_identity_cannot_include_role_or_password(self):
        self.assertNotIn('password_hash', COMMANDS['personnel_update_identity']['snapshot'])
        with patch('assistant_commands.before_state') as read:
            with self.assertRaises(HTTPException):
                prepare_command('personnel_update_identity', {
                    'path_params': {'user_id': 8}, 'body': {'username':'visitor_8','role':'ceo'},
                }, MANAGER)
        read.assert_not_called()
