"""
====================================================

QuantEngine

Delta Auth (Signature) Contract Tests

Run with:

    python -m unittest tests.test_delta_auth -v

Locks the Delta v2 private-API signing scheme:

- the pre-hash string is method + timestamp + path(with
  query) + body, plain concatenation, no separators;
- the signature is HMAC-SHA256 of that string keyed by the
  API secret, hex-encoded;
- the `timestamp` header is the same seconds value used in
  the signature;
- GET query strings are signed as part of the path;
- POST bodies are serialized once and signed byte-for-byte.

The documented pre-hash reference format is verified against
an independently-computed hmac (no network, no copied hex).

====================================================
"""

import unittest
from unittest import mock

from core.exchanges.delta.delta_auth import (
    DeltaSignedREST,
    build_prehash,
    query_string,
    sign,
)


SECRET = "7b6f39dcf660ec1c7c664f612c60410a2bd0c258416b49"


class TestBuildPrehash(unittest.TestCase):

    def test_documented_prehash_format(self):
        # Delta docs: concatenate method + timestamp + path +
        # query + payload with no separators.
        prehash = build_prehash(
            "GET",
            "1542110948",
            "/v2/orders?product_id=1&state=open",
            "",
        )
        self.assertEqual(
            prehash,
            "GET1542110948/v2/orders?product_id=1&state=open",
        )

    def test_post_prehash_includes_body_after_path(self):
        prehash = build_prehash(
            "POST",
            "1542110948",
            "/v2/orders",
            '{"size":3,"side":"buy"}',
        )
        self.assertEqual(
            prehash,
            "POST1542110948/v2/orders"
            '{"size":3,"side":"buy"}',
        )

    def test_delete_prehash_has_no_body(self):
        prehash = build_prehash(
            "DELETE",
            "1542110948",
            "/v2/orders/12345",
            "",
        )
        self.assertEqual(
            prehash,
            "DELETE1542110948/v2/orders/12345",
        )


class TestSign(unittest.TestCase):

    def test_signature_is_hmac_sha256_hexdigest(self):
        import hashlib
        import hmac

        prehash = "GET1542110948/v2/orders?product_id=1&state=open"

        produced = sign(SECRET, prehash)

        reference = hmac.new(
            SECRET.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        self.assertEqual(produced, reference)
        self.assertEqual(len(produced), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in produced))

    def test_signature_is_deterministic(self):
        prehash = "POST1542110948/v2/orders"
        self.assertEqual(sign(SECRET, prehash), sign(SECRET, prehash))

    def test_signature_changes_with_timestamp(self):
        self.assertNotEqual(
            sign(SECRET, "GET1/v2/orders"),
            sign(SECRET, "GET2/v2/orders"),
        )


class TestQueryString(unittest.TestCase):

    def test_empty_params_produce_no_query(self):
        self.assertEqual(query_string(None), "")
        self.assertEqual(query_string({}), "")

    def test_params_become_single_query_string(self):
        self.assertEqual(
            query_string({"product_id": 1, "state": "open"}),
            "?product_id=1&state=open",
        )


class TestDeltaSignedREST(unittest.TestCase):

    def _client(self, authenticated=True):

        rest = DeltaSignedREST(
            api_key="k" if authenticated else "",
            api_secret=SECRET if authenticated else "",
            # Offline signing test against a fake HTTP client: the
            # transport-level write authority is not under test here
            # (explicit opt-out; real callers are gating by default).
            enforce_write_authority=False,
        )

        rest.client = _FakeHttpClient()

        return rest

    def test_unauthenticated_headers_have_no_signature(self):
        headers = self._client(authenticated=False)._headers(
            "GET",
            "/v2/products",
            "",
        )
        self.assertNotIn("api-key", headers)
        self.assertNotIn("timestamp", headers)
        self.assertNotIn("signature", headers)

    def test_authenticated_headers_carry_signed_timestamp(self):
        client = self._client(authenticated=True)

        with mock.patch(
            "core.exchanges.delta.delta_auth.time.time",
            return_value=1542110948.0,
        ):
            headers = client._headers(
                "POST",
                "/v2/orders",
                '{"side":"buy"}',
            )

        self.assertEqual(headers["timestamp"], "1542110948")
        self.assertEqual(headers["api-key"], "k")

        expected = sign(
            SECRET,
            build_prehash(
                "POST",
                "1542110948",
                "/v2/orders",
                '{"side":"buy"}',
            ),
        )

        self.assertEqual(headers["signature"], expected)

    def test_get_signs_path_including_query(self):
        client = self._client(authenticated=True)

        with mock.patch(
            "core.exchanges.delta.delta_auth.time.time",
            return_value=2000000000.0,
        ):
            client.get(
                "/v2/wallet/balances",
            )
            client.get(
                "/v2/orders",
                params={"product_id": 1, "state": "open"},
            )

        calls = client.client.calls

        self.assertEqual(calls[0][0], "get")
        self.assertEqual(
            calls[0][1],
            "/v2/wallet/balances",
        )

        expected_sig = sign(
            SECRET,
            "GET2000000000/v2/orders?product_id=1&state=open",
        )

        self.assertEqual(calls[1][0], "get")
        self.assertEqual(
            calls[1][1],
            "/v2/orders?product_id=1&state=open",
        )
        self.assertEqual(calls[1][2]["signature"], expected_sig)

    def test_post_sends_and_signs_identical_body(self):
        client = self._client(authenticated=True)

        payload = {"product_id": 2, "side": "buy", "size": 0.1}

        with mock.patch(
            "core.exchanges.delta.delta_auth.time.time",
            return_value=2000000000.0,
        ):
            client.post("/v2/orders", payload=payload)

        verb, path, headers, body = client.client.calls[0]

        self.assertEqual(verb, "post")
        self.assertEqual(path, "/v2/orders")

        import json

        expected_body = json.dumps(payload, separators=(",", ":"))

        self.assertEqual(body, expected_body)

        self.assertEqual(
            headers["signature"],
            sign(
                SECRET,
                build_prehash(
                    "POST",
                    "2000000000",
                    "/v2/orders",
                    expected_body,
                ),
            ),
        )

    def test_delete_signed_without_body(self):
        client = self._client(authenticated=True)

        with mock.patch(
            "core.exchanges.delta.delta_auth.time.time",
            return_value=2000000000.0,
        ):
            client.delete("/v2/orders/123")

        verb, path, headers, body = client.client.calls[0]

        self.assertEqual(verb, "delete")
        self.assertEqual(path, "/v2/orders/123")
        self.assertEqual(body, "")
        self.assertEqual(
            headers["signature"],
            sign(SECRET, "DELETE2000000000/v2/orders/123"),
        )

    def test_delete_signed_with_body(self):
        # Venue-verified cancel shape: DELETE /v2/orders with a JSON
        # body; the exact wire body is the signed body.
        client = self._client(authenticated=True)

        with mock.patch(
            "core.exchanges.delta.delta_auth.time.time",
            return_value=2000000000.0,
        ):
            client.delete("/v2/orders",
                          payload={"id": 2175085905, "product_id": 84})

        verb, path, headers, body = client.client.calls[0]

        self.assertEqual(verb, "delete")
        self.assertEqual(path, "/v2/orders")
        self.assertEqual(
            body, '{"id":2175085905,"product_id":84}')
        self.assertEqual(
            headers["signature"],
            sign(SECRET, "DELETE2000000000/v2/orders"
                         '{"id":2175085905,"product_id":84}'),
        )


class _FakeHttpClient:

    def __init__(self):
        self.calls = []

    def get(self, url, headers=None):
        self.calls.append(("get", url, headers))
        return _FakeResponse()

    def post(self, url, content=None, headers=None):
        self.calls.append(
            (
                "post",
                url,
                headers,
                (content or b"").decode("utf-8"),
            )
        )
        return _FakeResponse()

    def delete(self, url, content=None, headers=None):
        self.calls.append(("delete", url, headers,
                           (content or b"").decode("utf-8")))
        return _FakeResponse()


class _FakeResponse:

    def raise_for_status(self):
        return None

    def json(self):
        return {"success": True}


if __name__ == "__main__":
    unittest.main()