"""Public storefront route gates: only the intended read-only endpoints are anonymous."""
import os
import unittest
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import JSONResponse

import api
from site_auth import current_site_customer
from fastapi import HTTPException


def request_for(path: str, method: str = "GET") -> Request:
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    })


class PublicStorefrontGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_read_routes_are_explicitly_allowlisted(self):
        for path in (
            "/public/catalog",
            "/public/feeds/torob",
            "/public/feeds/products.json",
            "/public/feeds/products.csv",
        ):
            with self.subTest(path=path):
                self.assertIn(path, api._OPEN_PATHS)

    async def test_internal_digikala_prices_are_not_public(self):
        path = "/public/catalog/prices"
        self.assertNotIn(path, api._OPEN_PATHS)
        self.assertEqual(api._required_module(path), "online-sales")
        with patch.dict(os.environ, {"KIARAD_JWT_SECRET": "", "KIARAD_API_KEY": ""}):
            called = False

            async def call_next(_request):
                nonlocal called
                called = True
                return JSONResponse({"unexpected": "allowed"})

            response = await api.auth_gate(request_for(path), call_next)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(called)

    async def test_csv_feed_is_public_for_get_but_not_post(self):
        with patch.dict(os.environ, {"KIARAD_JWT_SECRET": "", "KIARAD_API_KEY": ""}):
            async def call_next(_request):
                return JSONResponse({"allowed": True})

            allowed = await api.auth_gate(request_for("/public/feeds/products.csv", "GET"), call_next)
            denied = await api.auth_gate(request_for("/public/feeds/products.csv", "POST"), call_next)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 401)

    async def test_customer_profile_still_requires_customer_token(self):
        with self.assertRaises(HTTPException) as error:
            current_site_customer("")
        self.assertEqual(error.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
