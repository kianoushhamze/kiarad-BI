"""The unsupported Digikala product-create route must fail closed without network writes."""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import HTTPException

import platform_sync
from digikala_api import DigikalaClient, DigikalaProductCreationUnavailable


class _Result:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row

    def execute(self, *_args, **_kwargs):
        return _Result(self.row)


class DigikalaCreationGuardTests(unittest.TestCase):
    def test_client_never_posts_to_unverified_product_endpoint(self):
        client = DigikalaClient.__new__(DigikalaClient)
        with patch("digikala_api.requests.request") as request:
            with self.assertRaises(DigikalaProductCreationUnavailable):
                client.create_product({"title": "fixture"})
            request.assert_not_called()

    def test_confirm_endpoint_returns_409_without_calling_digikala(self):
        row = {"id": 7, "status": "pending"}

        @contextmanager
        def begin():
            yield _Connection(row)

        with patch.object(platform_sync.engine, "begin", begin), \
             patch.object(platform_sync, "_dk_client") as client:
            with self.assertRaises(HTTPException) as raised:
                platform_sync.confirm_create_proposal(7, {"role": "ceo"})

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("پنل فروشنده", raised.exception.detail)
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
