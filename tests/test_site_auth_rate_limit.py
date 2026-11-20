"""Trusted-proxy IP extraction and shared site-auth rate-limit behavior."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

import site_auth


def request_for(client="203.0.113.9", headers=None):
    header_items = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/site-auth/login",
        "raw_path": b"/site-auth/login",
        "query_string": b"",
        "headers": header_items,
        "client": (client, 12345),
        "server": ("testserver", 443),
    })


class _Result:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        if "INSERT INTO site_auth_rate_limits" in str(statement):
            return _Result(self.row)
        return _Result({})


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, traceback):
        return False


class SiteAuthRateLimitTests(unittest.TestCase):
    def test_untrusted_forwarded_headers_are_ignored(self):
        with patch.dict(os.environ, {"KIARAD_TRUSTED_PROXY_CIDRS": ""}, clear=False):
            request = request_for(
                client="203.0.113.9",
                headers={
                    "CF-Connecting-IP": "198.51.100.7",
                    "X-Forwarded-For": "192.0.2.4",
                },
            )
            self.assertEqual(site_auth._client_ip(request), "203.0.113.9")

    def test_cloudflare_header_is_used_only_from_trusted_peer(self):
        with patch.dict(os.environ, {"KIARAD_TRUSTED_PROXY_CIDRS": "127.0.0.1/32"}, clear=False):
            request = request_for(
                client="127.0.0.1",
                headers={"CF-Connecting-IP": "198.51.100.7"},
            )
            self.assertEqual(site_auth._client_ip(request), "198.51.100.7")

    def test_forwarded_chain_skips_trusted_proxy_hops(self):
        with patch.dict(os.environ, {"KIARAD_TRUSTED_PROXY_CIDRS": "10.0.0.0/8"}, clear=False):
            request = request_for(
                client="10.0.0.2",
                headers={"X-Forwarded-For": "198.51.100.7, 10.0.0.1"},
            )
            self.assertEqual(site_auth._client_ip(request), "198.51.100.7")

    def test_invalid_proxy_network_configuration_fails_closed(self):
        with patch.dict(os.environ, {"KIARAD_TRUSTED_PROXY_CIDRS": "not-a-cidr"}, clear=False):
            with self.assertRaises(HTTPException) as error:
                site_auth._client_ip(request_for(client="127.0.0.1"))
        self.assertEqual(error.exception.status_code, 503)

    def test_rate_limit_bucket_is_hashed_and_returns_retry_after(self):
        connection = _Connection({"attempts": 11, "retry_after": 123})
        fake_engine = SimpleNamespace(begin=lambda: _Transaction(connection))
        with patch.object(site_auth, "engine", fake_engine), patch.dict(
            os.environ, {"KIARAD_JWT_SECRET": "x" * 40, "KIARAD_TRUSTED_PROXY_CIDRS": ""}
        ):
            retry_after = site_auth._consume_rate_limit(request_for(), "login")

        self.assertEqual(retry_after, 123)
        insert_sql, params = connection.calls[0]
        self.assertIn("ON CONFLICT", insert_sql)
        self.assertEqual(len(params["bucket_key"]), 64)
        self.assertNotIn("203.0.113.9", params["bucket_key"])
        self.assertEqual(params["window_seconds"], 15 * 60)

    def test_login_route_stops_before_database_lookup_when_limited(self):
        request = request_for()
        data = site_auth.LoginIn(contact="user@example.com", password="wrong-password")
        with patch.dict(os.environ, {"KIARAD_JWT_SECRET": "x" * 40}), patch.object(
            site_auth, "_consume_rate_limit", return_value=45
        ), patch.object(site_auth.engine, "connect") as connect:
            with self.assertRaises(HTTPException) as error:
                site_auth.login(data, request)
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "45")
        connect.assert_not_called()

    def test_register_route_stops_before_insert_when_limited(self):
        request = request_for()
        data = site_auth.RegisterIn(name="Test User", contact="user@example.com", password="safe-password")
        with patch.dict(os.environ, {"KIARAD_JWT_SECRET": "x" * 40}), patch.object(
            site_auth, "_consume_rate_limit", return_value=90
        ), patch.object(site_auth.engine, "begin") as begin:
            with self.assertRaises(HTTPException) as error:
                site_auth.register(data, request)
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "90")
        begin.assert_not_called()


if __name__ == "__main__":
    unittest.main()
