"""Offline business regressions plus opt-in PostgreSQL concurrency tests.

DB tests use a unique disposable schema and synthetic rows only. No external
API requests; every inventory publication is mocked. Requires CREATE SCHEMA.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timezone
from threading import Barrier
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine, text
import site_orders as orders
import platform_sync as platforms


def order_data(request_id='request_test_1234567890', items=None):
    return orders.OrderIn(customer_name='Test customer', phone='09123456789', city='Test',
        address='Test address', items=items or [{'code': 'A', 'qty': 1}], request_id=request_id)


class StorefrontOrderUnitTests(unittest.TestCase):
    def test_missing_active_snapshot_cannot_release_existing_reservations(self):
        with patch.object(platforms.engine, 'begin') as begin, self.assertRaises(ValueError):
            platforms.apply_order('digikala', 'test', [])
        begin.assert_not_called()

    def test_fingerprint_normalizes_duplicate_lines_and_ignores_retry_key(self):
        a = order_data(items=[{'code': 'A', 'qty': 1}, {'code': 'A', 'qty': 2}])
        b = order_data('request_another_1234567', [{'code': 'A', 'qty': 3}])
        self.assertEqual(orders._fingerprint(a), orders._fingerprint(b))
        self.assertNotEqual(orders._fingerprint(a), orders._fingerprint(order_data()))

    def test_stock_check_subtracts_cross_platform_reservations(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            'name': 'Test', 'stock': 4, 'price': 1000, 'discount_price_irr': None}
        with patch.object(orders, 'reserved_count', return_value=4), self.assertRaises(HTTPException) as error:
            orders._recompute(conn, order_data().items)
        self.assertEqual(error.exception.status_code, 400)

    def test_retry_returns_original_without_another_reservation(self):
        data = order_data()
        existing = {'id': 7, 'created_at': datetime.now(timezone.utc), 'items': [], 'total_irr': 1150,
                    'request_fingerprint': orders._fingerprint(data)}
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = existing
        with patch.object(orders.engine, 'begin', return_value=nullcontext(conn)), \
             patch.object(orders, 'ensure'), patch.object(orders, 'ensure_catalog'), patch.object(orders, 'ensure_platforms'), \
             patch.object(orders, '_reserve_items') as reserve:
            result = orders.create_order(data, BackgroundTasks(), {'id': 1})
        self.assertEqual(result['order_id'], 7)
        self.assertTrue(result['replayed'])
        reserve.assert_not_called()

    def test_same_key_with_different_payload_rejected(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {'request_fingerprint': 'different'}
        with patch.object(orders.engine, 'begin', return_value=nullcontext(conn)), \
             patch.object(orders, 'ensure'), patch.object(orders, 'ensure_catalog'), patch.object(orders, 'ensure_platforms'), \
             self.assertRaises(HTTPException) as error:
            orders.create_order(order_data(), BackgroundTasks(), {'id': 1})
        self.assertEqual(error.exception.status_code, 409)

    def test_registered_financial_document_is_not_rewritten(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            'proforma_id': 9, 'holoo_registered': True, 'invoice_status': 'draft'}
        self.assertEqual(platforms._create_platform_order_proforma(conn, 'digikala', 'test', []), 9)
        self.assertEqual(conn.execute.call_count, 1)

    def test_cancelled_financial_document_is_not_reopened_by_polling(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value = {
            'proforma_id': 9, 'holoo_registered': False, 'invoice_status': 'cancelled'}
        self.assertEqual(platforms._create_platform_order_proforma(conn, 'digikala', 'test', []), 9)
        self.assertEqual(conn.execute.call_count, 1)

    def test_conflicting_duplicate_prices_fail_before_database(self):
        with patch.object(platforms.engine, 'begin') as begin, self.assertRaises(ValueError):
            platforms.apply_order('digikala', 'test', [
                {'code': 'A', 'qty': 1, 'price_irr': 1000},
                {'code': 'A', 'qty': 1, 'price_irr': 2000}])
        begin.assert_not_called()

    def test_repeated_platform_poll_updates_existing_draft(self):
        conn = MagicMock()
        existing = {'proforma_id': 9, 'holoo_registered': False, 'invoice_status': 'draft'}
        product = {'id': 1, 'name': 'Test', 'price': 1000}
        conn.execute.return_value.mappings.return_value.first.side_effect = [existing, product]
        with patch.object(platforms, '_platform_customer_id', return_value=1):
            result = platforms._create_platform_order_proforma(conn, 'digikala', 'test', [{'code': 'A', 'qty': 2, 'price_irr': 1200}])
        self.assertEqual(result, 9)
        sql = [str(call.args[0]) for call in conn.execute.call_args_list]
        self.assertFalse(any('INSERT INTO proforma_invoices' in statement for statement in sql))
        updates = [call for call in conn.execute.call_args_list if 'UPDATE proforma_invoices' in str(call.args[0])]
        self.assertEqual(updates[0].args[1]['amount'], 2400)

    def test_holoo_registration_is_scoped_to_platform_and_order_ref(self):
        conn = MagicMock()
        conn.execute.return_value.rowcount = 1
        with patch.object(platforms.engine, 'begin', return_value=nullcontext(conn)), \
             patch.object(platforms, 'ensure'), patch.object(platforms, '_ensure_platform_proforma_storage'):
            result = platforms.mark_holoo_registered('digikala', 'shared-ref', {'role':'ceo'})
        self.assertEqual(result['platform'], 'digikala')
        statement, params = conn.execute.call_args.args
        self.assertIn('platform=:p AND order_ref=:r', str(statement))
        self.assertEqual(params, {'p':'digikala', 'r':'shared-ref'})

    def test_holoo_registration_rejects_unknown_platform(self):
        with patch.object(platforms.engine, 'begin') as begin, self.assertRaises(HTTPException) as error:
            platforms.mark_holoo_registered('unknown', 'shared-ref', {'role':'ceo'})
        self.assertEqual(error.exception.status_code, 400)
        begin.assert_not_called()

    def test_stock_publication_failure_does_not_undo_committed_order(self):
        with patch.object(orders, 'push_stock_many', side_effect=RuntimeError('offline')), \
             self.assertLogs(orders.logger, level='ERROR'):
            orders._publish_stock(['A'])


@unittest.skipUnless(os.getenv('KIARAD_TEST_STOREFRONT_DB') == '1', 'Opt-in disposable PostgreSQL schema')
class StorefrontOrderDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = 'qa_storefront_' + uuid4().hex
        cls.admin = orders.engine
        with cls.admin.begin() as conn:
            conn.execute(text('CREATE SCHEMA ' + cls.schema))
        cls.test_engine = create_engine(cls.admin.url, connect_args={'options':
            '-c search_path=' + cls.schema + ' -c statement_timeout=15000 -c lock_timeout=10000'})
        cls.addClassCleanup(cls.cleanup_schema)
        with cls.test_engine.begin() as conn:
            conn.execute(text('CREATE TABLE products(id SERIAL PRIMARY KEY, code TEXT UNIQUE, name TEXT, price BIGINT, stock INT, is_active INT)'))
            conn.execute(text('CREATE TABLE customers(id SERIAL PRIMARY KEY, code TEXT UNIQUE, name TEXT, credit_limit BIGINT)'))
            conn.execute(text('CREATE TABLE salespersons(id SERIAL PRIMARY KEY)'))
            orders.ensure(conn)
            orders.ensure_catalog(conn)
            platforms.ensure(conn)
            platforms._ensure_platform_proforma_storage(conn)

    @classmethod
    def cleanup_schema(cls):
        cls.test_engine.dispose()
        with cls.admin.begin() as conn: conn.execute(text('DROP SCHEMA ' + cls.schema + ' CASCADE'))

    def setUp(self):
        for module in (orders, platforms):
            patcher = patch.object(module, 'engine', self.test_engine)
            patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(platforms, 'push_stock_many', return_value=[])
        patcher.start(); self.addCleanup(patcher.stop)
        with self.test_engine.begin() as conn:
            for table in ('platform_order_proformas', 'proforma_invoices', 'platform_reservations', 'platform_orders_raw', 'site_orders', 'products', 'customers'):
                conn.execute(text('TRUNCATE ' + table + ' RESTART IDENTITY CASCADE'))
            conn.execute(text("INSERT INTO products(code,name,price,stock,is_active) VALUES ('A','Test A',1000,1,1),('B','Test B',2000,0,1)"))

    def scalar(self, sql):
        with self.test_engine.connect() as conn: return conn.execute(text(sql)).scalar()

    def checkout(self, key='request_test_1234567890', items=None):
        return orders.create_order(order_data(key, items), BackgroundTasks(), {'id': 1})

    def test_concurrent_checkouts_cannot_sell_the_last_item_twice(self):
        barrier = Barrier(2)
        def buy(n):
            barrier.wait(timeout=5)
            try: return self.checkout('request_race_1234567890_' + str(n))['order_id']
            except HTTPException as error: return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(buy, (1,2)))
        self.assertEqual(results.count(400), 1)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM site_orders'), 1)
        self.assertEqual(self.scalar("SELECT SUM(qty) FROM platform_reservations WHERE status='active'"), 1)

    def test_concurrent_retry_creates_only_one_order(self):
        barrier = Barrier(2)
        def buy(_):
            barrier.wait(timeout=5)
            return self.checkout()
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(buy, (1,2)))
        self.assertEqual(results[0]['order_id'], results[1]['order_id'])
        self.assertEqual(sum(row['replayed'] for row in results), 1)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM site_orders'), 1)

    def test_failed_cart_rolls_back_every_line(self):
        with self.assertRaises(HTTPException):
            self.checkout(items=[{'code':'A','qty':1},{'code':'B','qty':1}])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM site_orders'), 0)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM platform_reservations'), 0)

    def test_cancel_releases_stock_and_cancelled_order_cannot_reopen(self):
        result = self.checkout()
        orders.set_status(result['order_id'], orders.StatusIn(status='لغو شد'), BackgroundTasks(), {'role':'ceo','id':1})
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM platform_reservations WHERE status='active'"), 0)
        self.assertTrue(self.checkout()['replayed'])
        with self.assertRaises(HTTPException) as error:
            orders.set_status(result['order_id'], orders.StatusIn(status='جدید'), BackgroundTasks(), {'role':'ceo','id':1})
        self.assertEqual(error.exception.status_code, 409)
        self.checkout('request_second_1234567890')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM site_orders'), 2)

    def test_shipped_order_cannot_be_cancelled_or_reopened(self):
        result = self.checkout()
        orders.set_status(result['order_id'], orders.StatusIn(status='ارسال شد'), BackgroundTasks(), {'role':'ceo','id':1})
        with self.assertRaises(HTTPException) as error:
            orders.set_status(result['order_id'], orders.StatusIn(status='لغو شد'), BackgroundTasks(), {'role':'ceo','id':1})
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM platform_reservations WHERE status='active'"), 1)
        self.assertEqual(self.scalar("SELECT status FROM site_orders"), 'ارسال شد')
        with self.assertRaises(HTTPException) as error:
            orders.set_status(result['order_id'], orders.StatusIn(status='جدید'), BackgroundTasks(), {'role':'ceo','id':1})
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM platform_reservations WHERE status='active'"), 1)

    def test_external_platform_reservation_blocks_checkout(self):
        platforms.apply_order('digikala', 'test_external', [{'code':'A','qty':1}])
        with self.assertRaises(HTTPException) as error: self.checkout()
        self.assertEqual(error.exception.status_code, 400)

    def test_pending_legacy_orders_are_reserved_once(self):
        with self.test_engine.begin() as conn:
            conn.execute(text("INSERT INTO site_orders(customer_id,customer_name,items,total_irr) VALUES (1,'Legacy',CAST(:items AS JSONB),1150)"),
                         {'items':json.dumps([{'code':'A','qty':1}])})
            orders._reserve_legacy_pending(conn)
            orders._reserve_legacy_pending(conn)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM platform_reservations'), 1)
        with self.assertRaises(HTTPException): self.checkout()

    def test_repeated_platform_sync_reuses_draft_and_preserves_amount(self):
        first = platforms.apply_order('digikala', 'test_poll', [{'code':'A','qty':1,'price_irr':1200}])
        second = platforms.apply_order('digikala', 'test_poll', [{'code':'A','qty':2,'price_irr':1200}])
        self.assertEqual(first['proforma_id'], second['proforma_id'])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM proforma_invoices'), 1)
        self.assertEqual(self.scalar('SELECT total_amount FROM proforma_invoices'), 2400)
