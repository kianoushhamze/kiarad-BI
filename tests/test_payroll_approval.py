"""Validation checks for payroll approval; no database rows are changed."""
import unittest

from fastapi import HTTPException
from compensation import _validate_payroll_month


class PayrollApprovalValidationTests(unittest.TestCase):
    def test_valid_month_is_accepted(self):
        self.assertIsNone(_validate_payroll_month("2026-10"))

    def test_out_of_range_month_is_rejected(self):
        with self.assertRaises(HTTPException) as error:
            _validate_payroll_month("2026-13")
        self.assertEqual(error.exception.status_code, 422)

    def test_wrong_month_shape_is_rejected(self):
        with self.assertRaises(HTTPException):
            _validate_payroll_month("1405/07")


if __name__ == "__main__":
    unittest.main()
