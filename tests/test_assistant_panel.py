import unittest
from unittest.mock import patch
from fastapi import HTTPException
from assistant_panel import read_panel, RESOURCES


class PanelScope(unittest.TestCase):
    def test_unknown_resource_never_makes_http_request(self):
        with patch('assistant_panel.requests.Session') as http:
            with self.assertRaises(HTTPException):
                read_panel({'resource':'https://example.com'}, {'id':1,'role':'ceo'})
            http.assert_not_called()

    def test_staff_treasury_denied_before_http(self):
        with patch('assistant_panel.role_has_module_permission',return_value=False),patch('assistant_panel.requests.Session') as http:
            with self.assertRaises(HTTPException) as denied:
                read_panel({'resource':'treasury_checks'}, {'id':2,'role':'salesperson'})
            self.assertEqual(denied.exception.status_code,403)
            http.assert_not_called()

    def test_ceo_catalog_covers_requested_domains(self):
        resources=read_panel({'resource':'capabilities'},{'id':1,'role':'ceo'})['resources']
        self.assertEqual(len(resources),len(RESOURCES))
        self.assertTrue({'treasury_checks','online_channels','social_calendar','map_locations','personnel','voice_reports'}<={r['resource'] for r in resources})

    def test_all_origins_are_fixed_internal_paths(self):
        self.assertTrue(all(path.startswith('/') and not path.startswith('//') and '?' not in path for _,path in RESOURCES.values()))


class SitePanelScope(unittest.TestCase):
    def test_ceo_site_resources_are_discoverable_and_fixed(self):
        from assistant_reports import REPORT_TOOLS
        names = {'site_products', 'site_orders', 'site_banners'}
        actual = read_panel({'resource': 'capabilities'}, {'id': 1, 'role': 'ceo'})
        self.assertTrue(names <= {r['resource'] for r in actual['resources']})
        tool = next(t for t in REPORT_TOOLS if t['function']['name'] == 'read_panel_module')
        self.assertEqual(set(tool['function']['parameters']['properties']['resource']['enum']), {'capabilities', *RESOURCES})
        self.assertEqual(RESOURCES['site_orders'][1], '/site-orders/all')

    def test_non_ceo_cannot_discover_or_read_site_even_with_generic_grant(self):
        with patch('assistant_panel.role_has_module_permission', return_value=True), patch('assistant_panel.requests.Session') as http:
            actor = {'id': 2, 'role': 'sales_manager'}
            result = read_panel({'resource': 'capabilities'}, actor)
            self.assertFalse(any(r['module'] == 'site-cms' for r in result['resources']))
            for name in ('site_products', 'site_orders', 'site_banners'):
                with self.assertRaises(HTTPException) as denied:
                    read_panel({'resource': name}, actor)
                self.assertEqual(denied.exception.status_code, 403)
            http.assert_not_called()

    def test_ceo_orders_use_actor_token_and_read_only_method(self):
        with patch('assistant_panel.create_token', return_value='synthetic-ceo-token'), patch('assistant_panel.requests.Session') as factory:
            response = factory.return_value.get.return_value
            response.status_code = 200
            response.content = b'{}'
            response.json.return_value = {'count': 0, 'orders': []}
            result = read_panel({'resource': 'site_orders'}, {'id': 1, 'role': 'ceo'})
            self.assertEqual(result['source_path'], '/site-orders/all')
            self.assertEqual(factory.return_value.get.call_args.args, ('http://127.0.0.1:8000/site-orders/all',))
            self.assertEqual(factory.return_value.get.call_args.kwargs['headers']['Authorization'], 'Bearer synthetic-ceo-token')
            factory.return_value.post.assert_not_called()


class ReportFilters(unittest.TestCase):
    def test_model_schema_exposes_filters(self):
        from assistant_reports import REPORT_TOOLS
        tool = next(t for t in REPORT_TOOLS if t['function']['name'] == 'read_panel_module')
        properties = tool['function']['parameters']['properties']
        self.assertTrue({'month', 'period', 'up_to_date'} <= properties.keys())

    def test_authorized_reports_receive_requested_periods(self):
        from datetime import date

        with patch('assistant_panel.create_token', return_value='test'), \
             patch('assistant_panel.iran_today', return_value=date(2026, 11, 22)), \
             patch('assistant_panel.requests.Session') as factory:
            get = factory.return_value.get
            get.return_value.status_code = 200
            get.return_value.content = b'{}'
            get.return_value.json.return_value = {}
            actor = {'id': 1, 'role': 'ceo'}
            for args, key, expected in (
                ({'resource': 'monthly_visit_plans'}, 'month', '1405-09'),
                ({'resource': 'payroll_detail', 'salesperson_id': 2, 'month': '1405-07'}, 'month', '1405-07'),
                ({'resource': 'dashboard_full', 'period': '30d'}, 'range', '30d'),
                ({'resource': 'plan_reconciliation', 'plan_id': 2, 'up_to_date': '2026-11-22'}, 'up_to_date', '2026-11-22'),
            ):
                with self.subTest(resource=args['resource']):
                    read_panel(args, actor)
                    self.assertEqual(get.call_args.kwargs['params'][key], expected)
