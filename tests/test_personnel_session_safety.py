import os
import unittest
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import text
import operations as ops


@unittest.skipUnless(os.getenv('KIARAD_TEST_PERSONNEL_DB') == '1', 'Opt-in temporary database test')
class PersonnelSafetyTests(unittest.TestCase):
    def setUp(self):
        self.conn = ops.engine.connect()
        self.addCleanup(self.conn.close)
        tx = self.conn.begin()
        self.addCleanup(tx.rollback)
        for sql in (
            'CREATE TEMP TABLE salespersons (id INTEGER PRIMARY KEY)',
            '''CREATE TEMP TABLE users (id INTEGER PRIMARY KEY,username TEXT,full_name TEXT,role TEXT,
                salesperson_id INTEGER,is_active INTEGER,password_hash TEXT,password_version INTEGER DEFAULT 0)''',
            'INSERT INTO salespersons VALUES (10),(11)',
            "INSERT INTO users VALUES (1,'chief','مدیر','ceo',NULL,1,'old',0),(2,'field','پرسنل','salesperson',10,1,'old',0)",
        ):
            self.conn.execute(text(sql))
        @contextmanager
        def begin():
            with self.conn.begin_nested():
                yield self.conn
        patcher = patch.object(ops, 'engine', SimpleNamespace(begin=begin,connect=lambda:nullcontext(self.conn)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ceo = {'id':1,'role':'ceo'}

    def test_password_change_revokes_token_and_preserves_spaces(self):
        user = dict(self.conn.execute(text('SELECT * FROM users WHERE id=2')).mappings().one())
        with patch.object(ops, 'JWT_SECRET', 'x'*40):
            old_token = ops.create_token(user)
            ops.change_password(2, {'password':'  long password  '}, self.ceo)
            row = self.conn.execute(text('SELECT * FROM users WHERE id=2')).mappings().one()
            self.assertTrue(ops.verify_password('  long password  ', row['password_hash']))
            self.assertEqual(row['password_version'],1)
            with self.assertRaises(HTTPException) as error:
                ops.current_user('Bearer '+old_token)
            self.assertEqual(error.exception.status_code,401)

    def test_profile_required_and_unknown_profile_rejected(self):
        for value, code in ((None,422),(999,404)):
            with self.assertRaises(HTTPException) as error:
                ops.update_user(2, {'salesperson_id':value}, self.ceo)
            self.assertEqual(error.exception.status_code,code)
        ops.update_user(2, {'salesperson_id':11}, self.ceo)
        self.assertEqual(self.conn.execute(text('SELECT password_version FROM users WHERE id=2')).scalar(),1)

    def test_sales_manager_cannot_modify_privileged_account(self):
        manager={'id':3,'role':'sales_manager'}
        for call in (lambda:ops.update_user(1, {'full_name':'تغییر نام'},manager),
                     lambda:ops.change_password(1, {'password':'longpassword'},manager)):
            with self.assertRaises(HTTPException) as error:
                call()
            self.assertEqual(error.exception.status_code,403)

    def test_sales_manager_cannot_delete_privileged_accounts(self):
        self.conn.execute(text("""INSERT INTO users VALUES
            (3,'other-chief','مدیر دوم','ceo',NULL,1,'old',0),
            (4,'sales-chief','مدیر فروش','sales_manager',NULL,1,'old',0),
            (5,'finance-chief','مسئول مالی','finance',NULL,1,'old',0)"""))
        manager = {'id':99, 'role':'sales_manager'}
        for target_id in (3,4,5):
            with self.subTest(target_id=target_id), self.assertRaises(HTTPException) as error:
                ops.delete_user(target_id, manager)
            self.assertEqual(error.exception.status_code,403)
            self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM users WHERE id=:id'),
                                              {'id':target_id}).scalar(),1)

    def test_manager_can_delete_staff_and_ceo_can_delete_other_privileged_account(self):
        self.assertEqual(ops.delete_user(2, {'id':99,'role':'sales_manager'}), {'ok':True})
        self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM users WHERE id=2')).scalar(),0)
        self.conn.execute(text("INSERT INTO users VALUES (3,'other-chief','مدیر دوم','ceo',NULL,1,'old',0)"))
        self.assertEqual(ops.delete_user(3, self.ceo), {'ok':True})
        self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM users WHERE id=3')).scalar(),0)

    def test_delete_rejects_main_ceo_self_and_missing_account(self):
        for target_id,manager,expected in ((1,self.ceo,403),(2,{'id':2,'role':'sales_manager'},403),(999,self.ceo,404)):
            with self.subTest(target_id=target_id), self.assertRaises(HTTPException) as error:
                ops.delete_user(target_id,manager)
            self.assertEqual(error.exception.status_code,expected)
        self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM users')).scalar(),2)

    def test_invalid_activation_and_password_are_rejected(self):
        for data in ({'is_active':'false'},{'full_name':' '}):
            with self.assertRaises(HTTPException) as error:
                ops.update_user(2,data,self.ceo)
            self.assertEqual(error.exception.status_code,422)
        for password in (123,'short','x'*201):
            with self.assertRaises(HTTPException):
                ops.change_password(2,{'password':password},self.ceo)

    def _staff_with_password(self, password='previous test password'):
        self.conn.execute(text('UPDATE users SET password_hash=:hash WHERE id=2'),
                          {'hash': ops.hash_password(password)})
        return dict(self.conn.execute(text('SELECT * FROM users WHERE id=2')).mappings().one())

    def test_self_change_revokes_old_token_and_returns_working_session(self):
        user = self._staff_with_password()
        request = ops.PasswordChangeRequest(current_password='previous test password',
                                            new_password='replacement test password')
        with patch.object(ops, 'JWT_SECRET', 'x'*40):
            old_token = ops.create_token(user)
            result = ops.change_own_password(request, user)
            changed = self.conn.execute(text('SELECT * FROM users WHERE id=2')).mappings().one()
            self.assertTrue(ops.verify_password('replacement test password', changed['password_hash']))
            self.assertFalse(ops.verify_password('previous test password', changed['password_hash']))
            self.assertEqual(changed['password_version'], 1)
            with self.assertRaises(HTTPException) as error:
                ops.current_user('Bearer '+old_token)
            self.assertEqual(error.exception.status_code, 401)
            refreshed = ops.current_user('Bearer '+result['access_token'])
            self.assertEqual((refreshed['id'], refreshed['salesperson_id']), (2,10))
        self.assertNotIn('password_hash', result['user'])
        self.assertEqual(self.conn.execute(text('SELECT password_hash FROM users WHERE id=1')).scalar(), 'old')

    def test_wrong_current_password_does_not_change_account(self):
        user = self._staff_with_password()
        request = ops.PasswordChangeRequest(current_password='incorrect current password',
                                            new_password='replacement test password')
        with patch.object(ops, 'JWT_SECRET', 'x'*40):
            token = ops.create_token(user)
            with self.assertRaises(HTTPException) as error:
                ops.change_own_password(request, user)
            self.assertEqual(error.exception.status_code, 400)
            self.assertEqual(ops.current_user('Bearer '+token)['id'], 2)
        unchanged = self.conn.execute(text('SELECT password_hash,password_version FROM users WHERE id=2')).mappings().one()
        self.assertEqual(unchanged['password_hash'], user['password_hash'])
        self.assertEqual(unchanged['password_version'], 0)

    def test_same_password_is_rejected(self):
        user = self._staff_with_password()
        request = ops.PasswordChangeRequest(current_password='previous test password',
                                            new_password='previous test password')
        with patch.object(ops, 'JWT_SECRET', 'x'*40), self.assertRaises(HTTPException) as error:
            ops.change_own_password(request, user)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.conn.execute(text('SELECT password_version FROM users WHERE id=2')).scalar(), 0)

    def test_concurrent_manager_reset_invalidates_self_change(self):
        user = self._staff_with_password()
        self.conn.execute(text('UPDATE users SET password_version=1 WHERE id=2'))
        request = ops.PasswordChangeRequest(current_password='previous test password',
                                            new_password='replacement test password')
        with patch.object(ops, 'JWT_SECRET', 'x'*40), self.assertRaises(HTTPException) as error:
            ops.change_own_password(request, user)
        self.assertEqual(error.exception.status_code, 401)
        self.assertTrue(ops.verify_password('previous test password', self.conn.execute(
            text('SELECT password_hash FROM users WHERE id=2')).scalar()))

    def test_missing_signing_key_does_not_change_password(self):
        user = self._staff_with_password()
        request = ops.PasswordChangeRequest(current_password='previous test password',
                                            new_password='replacement test password')
        with patch.object(ops, 'JWT_SECRET', ''), self.assertRaises(HTTPException) as error:
            ops.change_own_password(request, user)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.conn.execute(text('SELECT password_version FROM users WHERE id=2')).scalar(), 0)


if __name__ == '__main__':
    unittest.main()
