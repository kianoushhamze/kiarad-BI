import unittest
from unittest.mock import patch
from urllib.error import URLError
from operational_readiness import assess_blockers, probe_url


class OperationalReadinessTests(unittest.TestCase):
    def test_missing_accounts_and_unverified_speech_are_not_ready(self):
        blockers = assess_blockers({'linked_field_accounts':0}, {'state':'local_files_present'}, {'backend':{'ok':True}})
        self.assertEqual(len(blockers), 3)

    def test_even_loaded_model_does_not_prove_phone_test(self):
        blockers = assess_blockers({'linked_field_accounts':1}, {'state':'loaded'}, {'backend':{'ok':True}})
        self.assertEqual(len(blockers), 1)
        self.assertIn('گوشی', blockers[0])

    def test_database_failure_does_not_claim_no_accounts(self):
        blockers = assess_blockers({'error':True}, {'state':'loaded'}, {'backend':{'ok':False}})
        self.assertEqual(len(blockers), 3)
        self.assertFalse(any('موجود نیست' in item for item in blockers))

    def test_unreachable_service_is_reported_without_exception_details(self):
        with patch('operational_readiness.urlopen', side_effect=URLError('private details')):
            self.assertEqual(probe_url('http://localhost'), {'ok':False,'status':None})


if __name__ == '__main__':
    unittest.main()
