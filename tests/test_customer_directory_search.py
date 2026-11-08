import unittest
from unittest.mock import MagicMock, patch
import proformas


class CustomerDirectorySearchTests(unittest.TestCase):
    def test_partial_persian_arabic_digits_and_word_order(self):
        self.assertEqual(proformas._customer_search_terms('  كِرمان رازي ۱۲٣ '), ['کرمان', 'رازی', '123'])
        self.assertEqual(proformas._customer_search_terms('ضد\u200cآفتاب'), ['ضد', 'افتاب'])
        self.assertEqual(proformas._customer_search_terms('%_'), [])

    def test_search_is_parameterized_and_all_terms_match_across_contact_fields(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.all.return_value = []
        with patch.object(proformas.engine, 'connect') as connect:
            connect.return_value.__enter__.return_value = conn
            result = proformas.get_customer_directory('رازي كرمان', {'id': 1})
        self.assertEqual(result, [])
        statement, params = conn.execute.call_args.args
        sql = str(statement)
        self.assertEqual(params, {'q0': '%رازی%', 'q1': '%کرمان%'})
        self.assertIn(' AND ', sql)
        self.assertIn("concat_ws(' ',name,city,phone,code)", sql)
        self.assertNotIn('رازی', sql)
        self.assertTrue(sql.endswith('ORDER BY name LIMIT 500'))

    def test_empty_query_preserves_existing_unfiltered_directory_and_limit(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value.all.return_value = []
        with patch.object(proformas.engine, 'connect') as connect:
            connect.return_value.__enter__.return_value = conn
            proformas.get_customer_directory(None, {'id': 1})
        statement, params = conn.execute.call_args.args
        self.assertNotIn(' WHERE ', str(statement))
        self.assertEqual(params, {})


if __name__ == '__main__':
    unittest.main()
