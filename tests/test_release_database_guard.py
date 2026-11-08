import importlib.util
from pathlib import Path
from io import StringIO
import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import OperationalError

spec = importlib.util.spec_from_file_location('release_db_guard', Path(__file__).resolve().parents[1] / 'scripts/check_release_database.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ReleaseDatabaseGuardTests(unittest.TestCase):
    def connection(self, results):
        conn = MagicMock()
        conn.execute.side_effect = [MagicMock(scalar=MagicMock(return_value=value)) for value in results]
        return conn

    def test_empty_database_requires_restore(self):
        self.assertEqual(guard.missing_tables(self.connection([None] * 3)), list(guard.REQUIRED))

    def test_partial_schema_is_not_accepted(self):
        self.assertEqual(guard.missing_tables(self.connection(['users', None, 'customers'])), ['products'])

    def test_check_is_read_only_and_parameters_are_bound(self):
        conn = self.connection(list(guard.REQUIRED))
        self.assertEqual(guard.missing_tables(conn), [])
        for call in conn.execute.call_args_list:
            self.assertEqual(str(call.args[0]), 'SELECT to_regclass(:table_name)')
        self.assertEqual([call.args[1]['table_name'] for call in conn.execute.call_args_list], ['public.' + name for name in guard.REQUIRED])

    def test_unavailable_database_fails_without_leaking_driver_details(self):
        with patch.object(guard.engine, 'connect', side_effect=OperationalError('private SQL', {}, Exception('private host'))), patch('sys.stdout', new_callable=StringIO) as output:
            self.assertEqual(guard.main(), 1)
        self.assertNotIn('private', output.getvalue())

    def test_main_returns_failure_for_missing_tables(self):
        conn = self.connection([None] * 3)
        with patch.object(guard.engine, 'connect') as connect, patch('sys.stdout', new_callable=StringIO) as output:
            connect.return_value.__enter__.return_value = conn
            self.assertEqual(guard.main(), 1)
        self.assertIn('restore_required', output.getvalue())

    def test_core_tables_do_not_claim_full_migration_validation(self):
        conn = self.connection(list(guard.REQUIRED))
        with patch.object(guard.engine, 'connect') as connect, patch('sys.stdout', new_callable=StringIO) as output:
            connect.return_value.__enter__.return_value = conn
            self.assertEqual(guard.main(), 0)
        self.assertIn('core_tables_present_only', output.getvalue())
