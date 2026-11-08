import unittest
from unittest.mock import patch
from fastapi import HTTPException
from public_registry_review import review_registry, telephone
import field_intelligence as field


class RegistryCustomerGuards(unittest.TestCase):
    def test_iran_phone_formats_have_one_identity(self):
        self.assertEqual(telephone('۰۳۴۱۲۳۴۵۶۷۸'), telephone('+98 34 12345678'))
        self.assertEqual(telephone('0098 34 12345678'), telephone('3412345678'))
        self.assertEqual(telephone('123'), '')
    def test_matching_existing_customer_blocks_eligible_duplicate(self):
        dataset = {'observed_at': '2026-11-02', 'notice': '', 'batches': [], 'items': [
            {'source_id': 'a', 'batch_id': 'b', 'name': 'داروخانه علی', 'city': 'کرمان', 'phone': '03412345678'}]}
        existing = [{'id': 9, 'name': 'علی', 'city': 'کرمان', 'phone': '03412345678'}]
        report = review_registry(dataset, existing, {})
        self.assertEqual(report['items'][0]['possible_matches_count'], 1)
        self.assertEqual(report['items'][0]['possible_matches'][0]['customer_id'], 9)

    def test_staff_cannot_import_or_delete(self):
        staff = {'id': 2, 'role': 'salesperson'}
        with patch.object(field.engine, 'begin') as database:
            for operation in (
                lambda: field.import_registry_customer(field.RegistryCustomerImport(source_id='a', confirm=True), staff),
                lambda: field.delete_registry_customer(3, staff),
                lambda: field.refresh_public_registry(staff),
            ):
                with self.assertRaises(HTTPException) as denied:
                    operation()
                self.assertEqual(denied.exception.status_code, 403)
            database.assert_not_called()

    def test_missing_source_rejected_before_database(self):
        with patch.object(field, 'load_registry', return_value={'items': []}), patch.object(field.engine, 'begin') as database:
            with self.assertRaises(HTTPException) as rejected:
                field.import_registry_customer(field.RegistryCustomerImport(source_id='missing', confirm=True), {'id':1,'role':'ceo'})
            self.assertEqual(rejected.exception.status_code, 409)
            database.assert_not_called()
