"""Offline regressions for the new gap-closure endpoints (no network, mocked boundaries).

Covers the two explicit client requests from the ZCode sessions:
  1. PATCH /digikala/variants/{id}/mapping — real server-side mapping write
  2. POST /marketing/leads/discover — live lead discovery, mocked sources
"""
import datetime
import json
import os
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import jwt
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api
import digikala_router
import marketing_intel
import operations

SECRET = 'gap-test-only-' + 'x' * 40

CEO_ROW = {'id': 1, 'username': 'ceo', 'full_name': 'CEO', 'role': 'ceo',
           'salesperson_id': None, 'is_active': 1, 'password_version': 0}


def _ceo_token() -> str:
    return jwt.encode({'sub': '1', 'role': 'ceo'}, SECRET, algorithm='HS256')


def _mock_connect():
    """A connection mock shaped like SQLAlchemy's context manager."""
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = lambda s, *a: None
    return conn


class DigikalaMappingTests(unittest.TestCase):
    def _authorized_env(self):
        """One mocked connection answers BOTH the JWT-gate user lookup (mappings().first)
        and the schema probe (scalar) — operations.engine and db.engine are the same object."""
        conn = _mock_connect()
        result = MagicMock()
        result.mappings.return_value.first.return_value = dict(CEO_ROW)
        result.scalar.return_value = 'dkp_id'
        conn.execute.return_value = result
        return patch.dict(os.environ, KIARAD_JWT_SECRET=SECRET), \
            patch.object(digikala_router.db.engine, 'connect', return_value=conn)

    def test_mapping_requires_auth(self):
        self.assertEqual(TestClient(api.app).patch('/digikala/variants/1/mapping',
                                                   json={'holoo_code': '11001'}).status_code, 401)

    def test_mapping_rejects_extra_fields(self):
        env, auth = self._authorized_env()
        with env, auth:
            resp = TestClient(api.app).patch('/digikala/variants/111001/mapping',
                                             headers={'Authorization': 'Bearer ' + _ceo_token()},
                                             json={'holoo_code': '11001', 'evil': 1})
        self.assertEqual(resp.status_code, 422)

    def test_mapping_rejects_empty_code(self):
        env, auth = self._authorized_env()
        with env, auth:
            resp = TestClient(api.app).patch('/digikala/variants/111001/mapping',
                                             headers={'Authorization': 'Bearer ' + _ceo_token()},
                                             json={'holoo_code': '  '})
        self.assertEqual(resp.status_code, 422)

    def test_mapping_writes_holoo_code(self):
        env, auth = self._authorized_env()
        session = MagicMock()
        session_result = MagicMock()
        session_result.scalar.return_value = 'updated_at'
        session_result.rowcount = 1
        session.execute.return_value = session_result
        with env, auth, patch.object(digikala_router.db, 'SessionLocal', return_value=session):
            resp = TestClient(api.app).patch('/digikala/variants/111001/mapping',
                                             headers={'Authorization': 'Bearer ' + _ceo_token()},
                                             json={'holoo_code': '11001'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['variant_id'], 111001)
        self.assertEqual(body['holoo_code'], '11001')
        self.assertEqual(body['applied_to_column'], 'dkp_id')
        executed_sql = [str(call.args[0]) for call in session.execute.call_args_list]
        self.assertTrue(any('UPDATE digikala_variants' in sql and 'holoo_code' in sql for sql in executed_sql),
                        executed_sql)

    def test_mapping_404_message_is_persian(self):
        exc = HTTPException(404, 'واریانت 5 در digikala_variants یافت نشد.')
        self.assertIn('یافت نشد', exc.detail)


class DigikalaStockTests(unittest.TestCase):
    def test_stock_sync_uses_seller_variant_and_available_quantity(self):
        conn = _mock_connect()
        variant = MagicMock()
        variant.mappings.return_value.first.return_value = {
            'seller_id': '5678', 'holoo_code': 'A', 'status': 'active',
        }
        product = MagicMock()
        product.mappings.return_value.first.return_value = {
            'id': 99, 'stock': 10, 'is_active': 1,
        }
        conn.execute.side_effect = [variant, product, None]
        client = MagicMock()
        client.update_stock.return_value.status_code = 204
        with patch.object(digikala_router.db.engine, 'begin', return_value=conn), \
             patch.object(digikala_router, 'reserved_quantity', return_value=3.5), \
             patch.object(digikala_router, 'get_client', return_value=client):
            self.assertEqual(digikala_router.sync_variant_stock(123, CEO_ROW), {'new_stock': 6})
        client.update_stock.assert_called_once_with(5678, 6)
        client.update_price.assert_not_called()
        self.assertEqual(conn.execute.call_args.args[1], {'count': 6, 'key': 123})

    def test_stock_sync_rejects_non_ceo(self):
        with self.assertRaises(HTTPException) as error:
            digikala_router.sync_variant_stock(123, {'role': 'visitor'})
        self.assertEqual(error.exception.status_code, 403)


class LeadDiscoveryTests(unittest.TestCase):
    def test_discover_requires_auth(self):
        self.assertEqual(TestClient(api.app).post('/marketing/leads/discover', json={}).status_code, 401)

    def test_p24_items_to_leads(self):
        items = [{
            'prefix': 'دکتر', 'display_name': 'آزمون تست', 'title': 'آزمون تست',
            'display_expertise': 'متخصص بیماریهای پوست', 'display_address': 'کرمان,خیابان آزمون',
            'medical_code': '123456', 'url': '/dr/test/',
            'centers': [{'phone': '03431234567، 09131234567'}],
            'rate_info': {'rate': 4.5},
        }]
        leads = marketing_intel._p24_items_to_leads(items, 'کرمان')
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]['source'], 'paziresh24')
        self.assertEqual(leads[0]['name'], 'دکتر آزمون تست')
        self.assertEqual(leads[0]['address'], 'کرمان,خیابان آزمون')
        self.assertEqual(leads[0]['phone'], '03431234567')
        self.assertEqual(leads[0]['detail']['medical_code'], '123456')
        self.assertEqual(leads[0]['detail']['url'], 'https://paziresh24.com/dr/test/')

    def test_p24_items_skip_nameless(self):
        self.assertEqual(marketing_intel._p24_items_to_leads([{'display_name': ''}], 'کرمان'), [])

    def test_mojavez_normalizer(self):
        body = {'data': {'items': [{'name': 'عطاری نمونه', 'phone': '03432221100',
                                    'license_id': 6051, 'city': 'کرمان'}]}}
        leads = marketing_intel._normalize_mojavez_items(body, 'کرمان')
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]['source'], 'mojavez')
        self.assertEqual(leads[0]['phone'], '03432221100')

    def test_discover_without_sources_reports_honestly(self):
        conn = _mock_connect()
        conn.execute.return_value.mappings.return_value.first.return_value = dict(CEO_ROW)
        with patch.dict(os.environ, KIARAD_JWT_SECRET=SECRET), \
             patch.object(operations.engine, 'connect', return_value=conn), \
             patch.object(marketing_intel.engine, 'begin', return_value=nullcontext()), \
             patch.object(marketing_intel, '_p24_search', side_effect=RuntimeError('offline')):
            resp = TestClient(api.app).post('/marketing/leads/discover',
                                            headers={'Authorization': 'Bearer ' + _ceo_token()},
                                            json={'save': False})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['found'], 0)
        self.assertTrue(any('پذیرش۲۴' in note for note in body['notes']))


if __name__ == '__main__':
    unittest.main()
