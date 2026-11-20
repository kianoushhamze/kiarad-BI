"""Offline regressions: mocked DB boundaries, no production writes/network."""
import importlib.util
import json
import os
from contextlib import nullcontext
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch
import jwt
from fastapi import HTTPException
from fastapi.testclient import TestClient
import api
import operations
import platform_sync as platforms
import site_auth
import site_orders as orders

SECRET = 'release-test-only-' + 'x' * 40
ROOT = Path(__file__).resolve().parents[1]

class ReleaseRegressionTests(TestCase):
    def test_database_url_preserves_special_characters(self):
        cfg = dict(host='localhost', port=5432, database='test_db', user='user@name', password='a@b:/?#%')
        spec = importlib.util.spec_from_file_location('db_url_test', ROOT / 'db.py')
        module = importlib.util.module_from_spec(spec)
        with patch('config.DB_CONFIG', cfg): spec.loader.exec_module(module)
        self.addCleanup(module.engine.dispose)
        self.assertEqual(module.DATABASE_URL.password, cfg['password'])
        self.assertEqual(module.DATABASE_URL.username, cfg['user'])
        self.assertEqual(module.DATABASE_URL.host, 'localhost')

    def test_customer_token_cannot_authenticate_employee(self):
        with patch.dict(os.environ, KIARAD_JWT_SECRET=SECRET), patch.object(operations.engine, 'connect') as connect:
            token = site_auth.create_site_token(1)
            with self.assertRaises(HTTPException) as err: operations.current_user('Bearer ' + token)
            self.assertEqual(err.exception.status_code, 401)
            connect.assert_not_called()

    def test_malformed_customer_subjects_return_401_before_database(self):
        with patch.dict(os.environ, KIARAD_JWT_SECRET=SECRET), patch.object(site_auth.engine, 'connect') as connect:
            for payload in ({'sub': None}, {'sub': 'bad'}, {'sub': '-1'}, {'sub': '0'}, {}):
                token = jwt.encode(dict(role='site_customer', **payload), SECRET, algorithm='HS256')
                with self.subTest(payload=payload), self.assertRaises(HTTPException) as err:
                    site_auth.current_site_customer('Bearer ' + token)
                self.assertEqual(err.exception.status_code, 401)
            connect.assert_not_called()

    def test_customer_gate_rejects_staff_routes_and_prefix_lookalikes(self):
        with patch.dict(os.environ, KIARAD_JWT_SECRET=SECRET), patch.object(api.engine, 'connect') as connect:
            token = site_auth.create_site_token(1)
            for path in ('/users', '/site-orders/all', '/site-orders-fake', '/site-orders/1/status'):
                with self.subTest(path=path):
                    response = TestClient(api.app).get(path, headers={'Authorization': 'Bearer ' + token})
                    self.assertEqual(response.status_code, 401)
            connect.assert_not_called()

    def test_anonymous_banner_write_is_rejected(self):
        self.assertEqual(TestClient(api.app).post('/site-banners').status_code, 401)

    def test_public_digikala_price_feed_requires_manager_authentication(self):
        self.assertNotIn('/public/catalog/prices', api._OPEN_PATHS)
        self.assertEqual(api._required_module('/public/catalog/prices'), 'online-sales')
        self.assertEqual(TestClient(api.app).get('/public/catalog/prices').status_code, 401)

    def test_public_catalog_exposes_availability_not_exact_stock(self):
        from contextlib import nullcontext
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.all.return_value = [{
            'id': 7, 'code': 'A', 'name': 'Synthetic product', 'category': 'Test',
            'price': 1000, 'stock': 9, 'image_url': None, 'discount_price_irr': None,
            'generated_at': None,
        }]
        with patch.object(api.engine, 'connect', return_value=nullcontext(conn)), \
             patch.object(api, 'reservation_totals', return_value={7: 4}):
            product = api.public_catalog()['products'][0]
        self.assertTrue(product['in_stock'])
        self.assertNotIn('stock', product)
        self.assertNotIn('price', product)
        self.assertNotIn('id', product)
        self.assertEqual(product['consumer_price_toman'], 115)

    def test_public_catalog_snapshots_do_not_include_internal_price_or_stock(self):
        for name in ("data.json", "data_demo_backup.json"):
            payload = json.loads((ROOT / "site" / name).read_text(encoding="utf-8"))
            for product in payload["products"]:
                self.assertIn("consumer_price_toman", product)
                self.assertIsInstance(product.get("in_stock"), bool)
                self.assertNotIn("price_holoo", product)
                self.assertNotIn("stock_holoo", product)
                self.assertNotIn("stock", product)

    def test_storefront_schema_is_migration_managed_not_request_managed(self):
        paths = (
            "site_auth.py", "site_orders.py", "site_cms.py", "platform_sync.py",
            "marketplace_feeds.py", "scripts/build_site_catalog.py",
            "scripts/derive_site_categories.py", "scripts/platform_stock_task.py",
        )
        for relative in paths:
            source = (ROOT / relative).read_text(encoding="utf-8-sig")
            with self.subTest(path=relative):
                self.assertNotRegex(source, r"(?im)^\s*(?:CREATE TABLE|ALTER TABLE)\b")

    def test_cors_rejects_unlisted_origin_and_allows_configured_origin(self):
        for origin, expected in [('https://untrusted.invalid', 400), ('http://localhost:3000', 200)]:
            with self.subTest(origin=origin):
                response = TestClient(api.app).options('/auth/login', headers={
                    'Origin': origin, 'Access-Control-Request-Method': 'POST',
                    'Access-Control-Request-Headers': 'authorization,content-type'})
                self.assertEqual(response.status_code, expected)
                self.assertNotEqual(response.headers.get('access-control-allow-origin'), '*')

    def cart_connection(self, stock=5, discount=None):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            'name': 'Test', 'price': 1000, 'stock': stock, 'discount_price_irr': discount}
        return conn

    def test_duplicate_cart_lines_cannot_exceed_stock(self):
        with self.assertRaises(HTTPException) as err:
            orders._recompute(self.cart_connection(), [orders.OrderItemIn(code='A', qty=3)] * 2)
        self.assertEqual(err.exception.status_code, 400)

    def test_duplicate_cart_lines_combined_and_priced_on_server(self):
        items, total = orders._recompute(self.cart_connection(discount=900), [orders.OrderItemIn(code='A', qty=2)] * 2)
        self.assertEqual((len(items), items[0]['qty'], total), (1, 4, 3600))

    def test_unknown_product_rejected(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = None
        with self.assertRaises(HTTPException) as err: orders._recompute(conn, [orders.OrderItemIn(code='X', qty=1)])
        self.assertEqual(err.exception.status_code, 400)

    def test_cancel_pushes_released_stock_after_commit(self):
        conn = MagicMock()
        conn.execute.return_value.all.return_value = [('A',), ('B',)]
        committed = []
        class Transaction:
            def __enter__(self): return conn
            def __exit__(self, *args): committed.append(True)
        def push(codes):
            self.assertTrue(committed)
            self.assertEqual(codes, ['A', 'B'])
            return [{'ok': True}]
        with patch.object(platforms.engine, 'begin', return_value=Transaction()), patch.object(platforms, 'push_stock_many', side_effect=push):
            result = platforms.apply_order('digikala', 'test', [], 'cancelled')
        self.assertTrue(result['released'])
        self.assertTrue(result['pushed'])

    def test_reinstatement_aggregates_lines_and_pushes_removed_codes(self):
        conn = MagicMock()
        conn.execute.return_value.all.return_value = [('OLD',)]
        with patch.object(platforms.engine, 'begin', return_value=nullcontext(conn)), patch.object(platforms, '_create_platform_order_proforma', return_value=42), \
             patch.object(platforms, 'push_stock_many', return_value=[]) as push:
            result = platforms.apply_order('digikala', 'test', [{'code': 'A', 'qty': 2}, {'code': 'A', 'qty': 3}], 'active')
        push.assert_called_once_with(['OLD', 'A'])
        inserts = [c for c in conn.execute.call_args_list if 'INSERT INTO platform_reservations' in str(c.args[0])]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0].args[1]['q'], 5)
        self.assertIn("status='active'", str(inserts[0].args[0]))
        self.assertEqual(result['proforma_id'], 42)

    def test_invalid_platform_lines_fail_before_database(self):
        with patch.object(platforms.engine, 'begin') as begin:
            for qty in (0, -1):
                with self.subTest(qty=qty), self.assertRaises(ValueError):
                    platforms.apply_order('digikala', 'test', [{'code': 'A', 'qty': qty}])
            begin.assert_not_called()

    def test_active_tasks_use_shared_configuration(self):
        for name in ('build_site_catalog.py', 'digikala_db_upsert.py', 'platform_stock_task.py', 'marketing_intel_task.py'):
            with self.subTest(script=name):
                source = (ROOT / 'scripts' / name).read_text(encoding='utf-8-sig')
                self.assertNotIn('D:\\project\\kiaradbi', source)
                self.assertNotIn("postgresql+psycopg2://", source)
                self.assertIn('from db import engine', source)
