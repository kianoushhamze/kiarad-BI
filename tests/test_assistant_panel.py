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
