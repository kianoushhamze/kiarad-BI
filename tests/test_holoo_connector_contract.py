"""Read-only contract checks for the Holoo connector; no network or database writes."""

import unittest
from unittest.mock import Mock, patch

import holoo_router
import holoo_sync


class HolooConnectorContractTests(unittest.TestCase):
    def test_both_connectors_share_transport(self):
        self.assertIs(holoo_router._holoo_request, holoo_sync._holoo_request)

    def test_tailnet_uses_direct_session(self):
        for host in ('100.99.182.6:8080', 'holoo.example.ts.net'):
            with patch.object(holoo_router.requests, 'Session') as factory:
                session = factory.return_value.__enter__.return_value
                holoo_router._holoo_request('GET', 'http://' + host + '/Settings', timeout=25)
                self.assertIs(session.trust_env, False)
                session.request.assert_called_once_with('GET', 'http://' + host + '/Settings', timeout=25)

    def test_other_hosts_keep_proxy_configuration(self):
        with patch.object(holoo_router.requests, 'request') as request:
            holoo_router._holoo_request('GET', 'https://example.com/Settings', timeout=25)
            request.assert_called_once()

    def test_login_requires_active_session(self):
        for module, function_name in (
            (holoo_router, "login_holoo"),
            (holoo_sync, "holoo_login"),
        ):
            with self.subTest(module=module.__name__):
                response = Mock()
                for state in (False, "False"):
                    response.json.return_value = {"Login": {"State": state, "Token": "unused"}}
                    with patch.object(module, '_holoo_request', return_value=response):
                        with self.assertRaises(ValueError):
                            getattr(module, function_name)()

    def test_documented_textual_true_login(self):
        for module, function_name in (
            (holoo_router, "login_holoo"),
            (holoo_sync, "holoo_login"),
        ):
            with self.subTest(module=module.__name__):
                response = Mock()
                response.json.return_value = {"Login": {"State": "True", "Token": "Bearer test-token"}}
                with patch.object(module, '_holoo_request', return_value=response):
                    self.assertEqual(getattr(module, function_name)(), "Bearer test-token")

    def test_documented_lowercase_customer_collection(self):
        for module, getter_name in (
            (holoo_router, "get_holoo"),
            (holoo_sync, "holoo_get"),
        ):
            with self.subTest(module=module.__name__):
                with patch.object(module, getter_name, return_value={"customer": []}):
                    self.assertEqual(module.sync_customers(Mock(), "unused"), 0)

    def test_missing_collections_are_not_reported_as_success(self):
        for module, getter_name in (
            (holoo_router, "get_holoo"),
            (holoo_sync, "holoo_get"),
        ):
            for sync_name in ("sync_customers", "sync_products"):
                with self.subTest(module=module.__name__, sync=sync_name):
                    with patch.object(module, getter_name, return_value={}):
                        with self.assertRaises(ValueError):
                            getattr(module, sync_name)(Mock(), "unused")


if __name__ == "__main__":
    unittest.main()
