"""Notification validation checks without database writes."""
import unittest

from fastapi import HTTPException
from operations import mark_notification_read


class NotificationValidationTests(unittest.TestCase):
    def test_empty_key_is_rejected_before_database_access(self):
        with self.assertRaises(HTTPException) as error:
            mark_notification_read("", user={"id": 1, "role": "ceo"})
        self.assertEqual(error.exception.status_code, 422)

    def test_oversized_key_is_rejected_before_database_access(self):
        with self.assertRaises(HTTPException) as error:
            mark_notification_read("x" * 201, user={"id": 1, "role": "ceo"})
        self.assertEqual(error.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
