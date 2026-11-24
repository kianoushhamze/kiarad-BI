import os
import unittest
from decimal import Decimal
from unittest.mock import Mock

from sqlalchemy import text

from target_schema import ensure_person_target_columns, normalize_person_target


class TargetSchemaSafetyTests(unittest.TestCase):
    def test_manual_target_accepts_persian_amounts_and_derives_jalali_period(self):
        values = normalize_person_target({
            'title': ' هدف تسویه ', 'target_amount': '۱٬۰۰۰٬۰۰۰٬۰۰۰', 'bonus_reward': '',
            'target_type': 'تسویه', 'start_date': '۱۴۰۵/۰۹/۰۱', 'end_date': '۱۴۰۵/۰۹/۳۰',
        })
        self.assertEqual(values['title'], 'هدف تسویه')
        self.assertEqual(values['target_amount'], '1000000000')
        self.assertEqual(values['bonus_reward'], '0')
        self.assertEqual((values['month'], values['year']), (9, 1405))
        self.assertEqual(values['start_date'], '2026-11-22')

    def test_status_only_patch_does_not_require_dates_for_a_legacy_target(self):
        self.assertEqual(normalize_person_target({'status':'archived'}, existing={'id':7,'start_date':None}),
                         {'status':'archived'})

    def test_only_adds_the_three_optional_nullable_columns(self):
        conn = Mock()
        ensure_person_target_columns(conn)
        statements = [str(call.args[0]) for call in conn.execute.call_args_list]
        self.assertEqual(statements, [
            "ALTER TABLE targets ADD COLUMN IF NOT EXISTS period_type VARCHAR(50)",
            "ALTER TABLE targets ADD COLUMN IF NOT EXISTS product_focus VARCHAR(150)",
            "ALTER TABLE targets ADD COLUMN IF NOT EXISTS bonus_reward NUMERIC(15,2)",
        ])
        for statement in statements:
            self.assertNotRegex(statement.upper(), r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|DEFAULT)\b")
            self.assertNotIn("NOT NULL", statement.upper())
            self.assertEqual(statement.count(";"), 0)
        conn.commit.assert_not_called()
        conn.rollback.assert_not_called()

@unittest.skipUnless(os.getenv("KIARAD_TEST_TARGET_SCHEMA_DB") == "1", "آزمون موقت پایگاه‌داده نیازمند فعال‌سازی صریح است")
class TargetSchemaTemporaryDatabaseTests(unittest.TestCase):
    def setUp(self):
        from db import engine

        self.conn = engine.connect()
        self.addCleanup(self.conn.close)
        transaction = self.conn.begin()
        self.addCleanup(transaction.rollback)
        self.conn.execute(text("""
            CREATE TEMP TABLE targets (
                id INTEGER PRIMARY KEY,
                title VARCHAR(100),
                target_amount NUMERIC(15,2)
            ) ON COMMIT DROP
        """))
        self.conn.execute(text("""
            INSERT INTO targets (id, title, target_amount)
            VALUES (1, 'رکورد اصلی', 125.50)
        """))

    def test_additions_preserve_existing_record_and_optional_user_values(self):
        ensure_person_target_columns(self.conn)
        original = self.conn.execute(text("""
            SELECT id, title, target_amount, period_type, product_focus, bonus_reward
            FROM targets WHERE id=1
        """)).one()
        self.assertEqual(tuple(original), (1, "رکورد اصلی", Decimal("125.50"), None, None, None))

        self.conn.execute(text("""
            UPDATE targets
            SET period_type=:period, product_focus=:focus, bonus_reward=:bonus
            WHERE id=1
        """), {"period": "دورهٔ انتخابی", "focus": "کالای انتخابی", "bonus": Decimal("345.67")})
        ensure_person_target_columns(self.conn)
        preserved = self.conn.execute(text("""
            SELECT id, title, target_amount, period_type, product_focus, bonus_reward
            FROM targets WHERE id=1
        """)).one()
        self.assertEqual(tuple(preserved), (
            1, "رکورد اصلی", Decimal("125.50"), "دورهٔ انتخابی", "کالای انتخابی", Decimal("345.67"),
        ))
        self.assertEqual(self.conn.execute(text("SELECT COUNT(*) FROM targets")).scalar_one(), 1)
        column_rows = self.conn.execute(text("""
            SELECT column_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema=(SELECT nspname FROM pg_namespace WHERE oid=pg_my_temp_schema())
              AND table_name='targets'
              AND column_name IN ('period_type', 'product_focus', 'bonus_reward')
        """)).mappings().all()
        self.assertEqual(len(column_rows), 3)
        self.assertTrue(all(row["is_nullable"] == "YES" and row["column_default"] is None for row in column_rows))


if __name__ == "__main__":
    unittest.main()
