"""User-reported aggregate questions must use source totals, not SKU lookup or sales prose."""
import unittest
from unittest.mock import patch
import assistant_engine as mod


class SummaryRoutingTests(unittest.TestCase):
    def ask(self, question, ctx, role='ceo'):
        with patch.object(mod.engine, 'connect') as database, \
             patch.object(mod, 'load_history', return_value=[]), \
             patch.object(mod, 'save_turn'), \
             patch.object(mod, 'build_live_context', return_value=ctx), \
             patch.object(mod, 'context_for_question', return_value={}), \
             patch.object(mod, 'role_has_module_permission', return_value=False), \
             patch.object(mod, 'call_gpt', return_value='incorrect model answer') as model:
            database.return_value.__enter__.return_value.execute.return_value.mappings.return_value = []
            result = mod.chat(mod.ChatRequest(message=question), user={'id': 1, 'role': role})
            model.assert_not_called()
            return result

    def test_reported_inventory_value_uses_actual_total(self):
        result = self.ask('ارزش انبار چقدره؟', {'products_active': 273, 'inventory_value': 123456780,
            'inventory_missing_values': 0, 'catalog_updated_at': '2026-11-14T10:00:00+00:00'})
        self.assertEqual(result['mode'], 'verified_inventory_value')
        self.assertIn('123,456,780', result['answer'])
        self.assertIn('قیمت فروش', result['answer'])
        self.assertIn('بهای خرید', result['answer'])
        self.assertEqual(result['action']['href'], '/catalog')

    def test_reported_debt_question_uses_balance_not_sales(self):
        result = self.ask('صورتحساب بدهکاران چنده ؟', {'debt_snapshot_id': 7, 'debt_snapshot_date': '2026-11-14',
            'debt_positive_total': 55000000, 'debt_rows': 452})
        self.assertEqual(result['mode'], 'verified_debt_summary')
        self.assertIn('55,000,000', result['answer'])
        self.assertNotIn('مالیات', result['answer'])
        self.assertNotIn('ویزیتور', result['answer'])
        self.assertEqual(result['action']['href'], '/debtors')

    def test_missing_inventory_is_not_zero(self):
        for ctx in ({}, {'products_active': 0, 'inventory_value': 0},
                    {'products_active': 2, 'inventory_value': 100, 'inventory_missing_values': 1}):
            self.assertEqual(self.ask('ارزش انبار چقدره؟', ctx)['mode'], 'inventory_data_required')

    def test_missing_debt_snapshot_is_not_zero(self):
        self.assertEqual(self.ask('صورتحساب بدهکاران چنده؟', {'debt_positive_total': 0, 'debt_rows': 0})['mode'], 'debt_data_required')

    def test_valid_snapshot_with_no_debt_is_zero(self):
        result = self.ask('مجموع بدهکاران چقدر است؟', {'debt_snapshot_id': 8, 'debt_snapshot_date': '2026-11-14',
            'debt_positive_total': 0, 'debt_rows': 0})
        self.assertEqual(result['mode'], 'verified_debt_summary')
        self.assertIn('0 ریال', result['answer'])

    def test_staff_cannot_read_company_totals(self):
        for question in ('ارزش انبار چقدره؟', 'صورتحساب بدهکاران چنده؟'):
            self.assertEqual(self.ask(question, {'inventory_value': 999999, 'debt_positive_total': 999999}, role='salesperson')['mode'], 'access_limited')

    def test_summary_classifier_preserves_products_dates_and_personal_scope(self):
        from assistant_inventory import aggregate_question
        for q in ('ارزش انبار لوفنته چقدره؟', 'صورتحساب بدهکاران دیروز چنده؟', 'بدهی مشتریان من چقدر است؟', 'قیمت محصول ارزش چیست؟'):
            self.assertIsNone(aggregate_question(q), q)
        for q in ('ارزش کل انبار چقدر است؟', 'ارزش موجودی انبار چقدره؟'):
            self.assertEqual(aggregate_question(q), 'inventory_value')

    def test_actual_aggregate_queries_keep_latest_snapshot_and_do_not_net_credit(self):
        from sqlalchemy import create_engine, text
        database = create_engine('sqlite://')
        self.addCleanup(database.dispose)
        with database.begin() as conn:
            conn.execute(text('CREATE TABLE receivable_snapshots(id INTEGER, snapshot_date TEXT)'))
            conn.execute(text("INSERT INTO receivable_snapshots VALUES(1,'2026-11-14'),(2,'2026-11-13')"))
            conn.execute(text('CREATE TABLE receivable_balances(snapshot_id INTEGER, balance NUMERIC, counterparty TEXT)'))
            conn.execute(text("INSERT INTO receivable_balances VALUES(1,10000,'A'),(1,20000,'B'),(1,-7000,'C'),(2,999999,'older')"))
            conn.execute(text('CREATE TABLE products(id INTEGER, name TEXT, stock NUMERIC, price NUMERIC, is_active INTEGER, min_stock NUMERIC, updated_at TEXT)'))
            conn.execute(text("INSERT INTO products VALUES(1,'A',3,1000,1,0,'2026-11-14'),(2,'B',NULL,2000,1,0,'2026-11-14')"))
        with database.connect() as conn, patch.object(mod, 'role_has_module_permission', return_value=False):
            ctx = mod.build_live_context(conn, {'id': 1, 'role': 'ceo'})
        self.assertEqual(ctx['debt_snapshot_id'], 1)
        self.assertEqual(ctx['debt_positive_total'], 30000)
        self.assertEqual(ctx['debt_rows'], 2)
        self.assertEqual(ctx['inventory_value'], 3000)
        self.assertEqual(ctx['inventory_missing_values'], 1)

    def test_generic_money_note_does_not_attach_sales_basis_to_debt(self):
        ctx = {'debt_positive_total': 5, 'debt_total': 5, 'debt_rows': 1, 'debt_snapshot_date': '2026-11-14'}
        result = mod.context_for_question(None, {'role': 'ceo'}, 'صورتحساب بدهکاران چنده؟', ctx)
        self.assertNotIn('مالیات', result.get('amount_note', ''))
        self.assertNotIn('sales_period', result)
