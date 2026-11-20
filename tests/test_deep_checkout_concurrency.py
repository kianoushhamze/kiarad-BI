"""Synthetic adversarial business transactions; isolated PostgreSQL schema only."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
import os
from pathlib import Path
from threading import Barrier
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, text

import platform_sync
import catalog
import proformas
import site_auth
import site_orders


class ProformaNumericBoundaryTests(unittest.TestCase):
    def test_decimal_price_and_nonfinite_erp_prices_are_handled(self):
        self.assertEqual(site_orders._consumer_unit_irr(Decimal('100'), None), 115)
        for price in (None, float('inf'), float('nan'), Decimal('NaN'), 'bad'):
            with self.subTest(price=str(price)):
                self.assertIsNone(site_orders._consumer_unit_irr(price, None))
    def test_nonfinite_amount_is_rejected_before_database_access(self):
        for amount in ('Infinity', '-Infinity', 'NaN'):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                proformas.ProformaCreate(customer_id=1, total_amount=amount)

    def test_extreme_json_numbers_return_validation_response_without_database(self):
        from api import validation_error_response
        app = FastAPI()
        app.include_router(proformas.router)
        app.add_exception_handler(RequestValidationError, validation_error_response)
        app.dependency_overrides[proformas.current_user] = lambda: {'role': 'salesperson', 'salesperson_id': 1}
        client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(client.close)
        with patch.object(proformas.engine, 'begin') as db:
            for amount in ('1e309', '-1e309', '"Infinity"', '"NaN"', '1e17'):
                with self.subTest(amount=amount):
                    response = client.post('/operations/proformas',
                        content='{"customer_id":1,"total_amount":' + amount + '}',
                        headers={'Content-Type': 'application/json'})
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(response.json()['detail'][0]['loc'], ['body', 'total_amount'])
            db.assert_not_called()

    def test_registration_without_signing_secret_does_not_create_an_account(self):
        data = site_auth.RegisterIn(name='Synthetic user', contact='missing-secret@example.test',
                                    password='Synthetic-password-0123')
        with patch.dict(os.environ, KIARAD_JWT_SECRET=''), patch.object(site_auth.engine, 'begin') as db:
            with self.assertRaises(HTTPException) as error:
                site_auth.register(data)
            self.assertEqual(error.exception.status_code, 503)
            db.assert_not_called()

    def test_malformed_platform_order_returns_422_without_writing(self):
        for items in ([{'code': 'A', 'qty': 'bad'}], ['bad'], [{'code': 'A', 'qty': 0}],
                      [{'code': 'A', 'qty': 1.5}], [{'code': 'A', 'qty': True}],
                      [{'code': 1, 'qty': 1}], [{'code': 'A', 'qty': 2**31}]):
            with self.subTest(items=items), patch.object(platform_sync.engine, 'begin') as db:
                with self.assertRaises(HTTPException) as error:
                    platform_sync.ingest_order({'platform': 'digikala', 'order_ref': 'invalid', 'items': items}, {'role': 'ceo'})
                self.assertEqual(error.exception.status_code, 422)
                db.assert_not_called()


@unittest.skipUnless(os.getenv('KIARAD_TEST_DEEP_CHECKOUT_DB') == '1', 'Opt-in isolated PostgreSQL tests')
class DeepCheckoutConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = proformas.engine
        cls.schema = 'qa_deep_checkout_' + uuid4().hex
        with cls.admin.begin() as conn:
            conn.execute(text('CREATE SCHEMA ' + cls.schema))
        cls.test_engine = create_engine(cls.admin.url, connect_args={'options':
            '-c search_path=' + cls.schema + ' -c statement_timeout=12000 -c lock_timeout=8000'})
        cls.addClassCleanup(cls.cleanup_schema)
        with cls.test_engine.begin() as c:
            for sql in (
                'CREATE TABLE customers(id SERIAL PRIMARY KEY,code TEXT UNIQUE,name TEXT,credit_limit NUMERIC)',
                'CREATE TABLE salespersons(id INTEGER PRIMARY KEY)',
                'CREATE TABLE products(id INTEGER PRIMARY KEY,code TEXT UNIQUE,name TEXT,price NUMERIC,price2 NUMERIC,stock NUMERIC,is_active INTEGER DEFAULT 1)',
                'CREATE TABLE sales(customer_id INTEGER,total_amount NUMERIC)',
                'CREATE TABLE payments(customer_id INTEGER,amount NUMERIC)',
            ):
                c.execute(text(sql))
            root = Path(__file__).resolve().parents[1]
            for migration in ("0005_cms_product_meta.sql", "0006_storefront_platform_storage.sql"):
                c.exec_driver_sql((root / "migrations" / migration).read_text(encoding="utf-8-sig"))
            proformas._ensure_proforma_storage(c)

    @classmethod
    def cleanup_schema(cls):
        cls.test_engine.dispose()
        with cls.admin.begin() as c:
            c.execute(text('DROP SCHEMA ' + cls.schema + ' CASCADE'))

    def setUp(self):
        p = patch.dict(os.environ, KIARAD_JWT_SECRET='synthetic-deep-test-signing-secret-0123456789')
        p.start()
        self.addCleanup(p.stop)
        for module in (proformas, platform_sync, site_auth, site_orders, catalog):
            p = patch.object(module, 'engine', self.test_engine)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(platform_sync, 'push_stock_many', return_value=[])
        p.start()
        self.addCleanup(p.stop)
        with self.test_engine.begin() as c:
            for table in ('inventory_reservations', 'platform_order_proformas', 'platform_reservations',
                          'platform_orders_raw', 'site_orders', 'proforma_invoices', 'products', 'customers', 'salespersons'):
                c.execute(text('TRUNCATE ' + table + ' RESTART IDENTITY CASCADE'))
            c.execute(text("INSERT INTO customers(code,name,credit_limit) VALUES('TEST','Synthetic',1000000)"))
            c.execute(text('INSERT INTO salespersons VALUES(1)'))
            # Intentionally opposite ordering: sorting IDs is not sorting SKU.
            c.execute(text("INSERT INTO products(id,code,name,price,price2,stock) VALUES(1,'B','Synthetic B',100,80,10),(2,'A','Synthetic A',100,80,10)"))

    def pf(self, ids):
        return proformas.create_proforma(proformas.ProformaCreate(customer_id=1,
            items=[{'product_id': i, 'quantity': 1} for i in ids]),
            {'id': 1, 'role': 'salesperson', 'salesperson_id': 1})

    def scalar(self, sql):
        with self.test_engine.connect() as c:
            return c.execute(text(sql)).scalar()

    def concurrent(self, *jobs):
        barrier = Barrier(len(jobs))
        def run(fn):
            barrier.wait(timeout=5)
            return fn()
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            return [f.result(timeout=15) for f in futures]

    def slow_product_locks(self):
        # Reproduce requests overlapping after a row lock, using real SQL.
        def delay(conn, cursor, statement, parameters, context, executemany):
            if 'FOR UPDATE' in statement.upper() and 'products' in statement:
                time.sleep(.12)
        event.listen(self.test_engine, 'after_cursor_execute', delay)
        self.addCleanup(event.remove, self.test_engine, 'after_cursor_execute', delay)

    def test_reverse_multi_item_proformas_do_not_deadlock(self):
        self.slow_product_locks()
        results = self.concurrent(lambda: self.pf([1, 2]), lambda: self.pf([2, 1]))
        self.assertEqual(len(results), 2)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM proforma_invoices'), 2)
        self.assertEqual(self.scalar('SELECT SUM(quantity) FROM inventory_reservations'), 4)

    def test_platform_and_proforma_share_sku_lock_order(self):
        with self.test_engine.begin() as c:
            c.execute(text("INSERT INTO customers(code,name) VALUES('PLATFORM:digikala','Synthetic platform')"))
        self.slow_product_locks()
        results = self.concurrent(lambda: self.pf([1, 2]), lambda: platform_sync.apply_order(
            'digikala', 'adversarial-order', [{'code': 'B', 'qty': 1}, {'code': 'A', 'qty': 1}]))
        self.assertEqual(len(results), 2)

    def test_legacy_orders_and_new_cart_lock_one_combined_product_set(self):
        with self.test_engine.begin() as c:
            c.execute(text("INSERT INTO site_orders(customer_id,customer_name,items) VALUES(1,'Synthetic legacy',CAST(:items AS JSONB))"),
                      {'items': json.dumps([{'code': 'A', 'qty': 1}])})
        self.slow_product_locks()
        def checkout():
            data = site_orders.OrderIn(customer_name='Synthetic buyer', phone='09000000000', city='Test',
                address='Synthetic address', items=[{'code': 'B', 'qty': 1}], request_id='legacy-overlap-0123456789')
            return site_orders.create_order(data, BackgroundTasks(), {'id': 1})
        self.assertEqual(len(self.concurrent(lambda: self.pf([1, 2]), checkout)), 2)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM site_orders WHERE reservation_managed'), 2)
        self.assertEqual(self.scalar("SELECT SUM(qty) FROM platform_reservations WHERE status='active'"), 2)

    def test_invalid_second_line_rolls_back_all_reservations(self):
        with self.assertRaises(HTTPException):
            self.pf([1, 99999])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM inventory_reservations'), 0)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM proforma_invoices'), 0)

    def test_unknown_nonfinite_stock_cannot_be_reserved(self):
        for stock in ('NaN', 'Infinity'):
            with self.test_engine.begin() as c:
                c.execute(text('UPDATE products SET stock=CAST(:stock AS NUMERIC) WHERE id=1'), {'stock': stock})
            for writer in (lambda: self.pf([1]), lambda: catalog.reserve(1, catalog.Reservation(
                    channel='synthetic', external_order_id='bad-stock', quantity=1), {'role': 'ceo'})):
                with self.subTest(stock=stock, writer=writer):
                    with self.assertRaises(HTTPException) as error:
                        writer()
                    self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM inventory_reservations'), 0)

    def test_fractional_or_boolean_product_ids_cannot_choose_another_product(self):
        for bad in (1.5, True, -1, 0):
            with self.subTest(product_id=bad):
                with self.assertRaises(HTTPException) as error:
                    self.pf([bad])
                self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM proforma_invoices'), 0)

    def test_parallel_site_registrations_use_migrated_schema(self):
        with self.test_engine.begin() as c:
            c.execute(text('TRUNCATE site_customers'))
        def register(n):
            return site_auth.register(site_auth.RegisterIn(name='Synthetic user',
                contact=f'first-{n}@example.test', password='Synthetic-password-0123'))
        results = self.concurrent(*(lambda n=n: register(n) for n in range(4)))
        self.assertEqual(len(results), 4)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM site_customers'), 4)

    def test_parallel_duplicate_registration_has_one_success_and_one_conflict(self):
        with self.test_engine.begin() as c:
            c.execute(text('TRUNCATE site_customers'))
        def register():
            try:
                site_auth.register(site_auth.RegisterIn(name='Synthetic user',
                    contact='duplicate@example.test', password='Synthetic-password-0123'))
                return 200
            except HTTPException as error:
                return error.status_code
        self.assertEqual(sorted(self.concurrent(register, register)), [200, 409])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM site_customers'), 1)

    def test_first_platform_orders_share_one_customer_without_unique_failure(self):
        # Both see the missing customer before either INSERT commits.
        barrier = Barrier(2)
        def delay(conn, cursor, statement, parameters, context, executemany):
            if 'SELECT id FROM customers WHERE code=' in statement:
                barrier.wait(timeout=5)
        event.listen(self.test_engine, 'after_cursor_execute', delay)
        self.addCleanup(event.remove, self.test_engine, 'after_cursor_execute', delay)
        results = self.concurrent(*(lambda n=n, code=code: platform_sync.apply_order(
            'digikala', 'first-' + str(n), [{'code': code, 'qty': 1}]) for n, code in enumerate(('A', 'B'))))
        self.assertEqual(len(results), 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM customers WHERE code='PLATFORM:digikala'"), 1)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM proforma_invoices'), 2)


if __name__ == '__main__':
    unittest.main()
