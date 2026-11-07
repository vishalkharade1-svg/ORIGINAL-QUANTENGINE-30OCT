"""Phase154: DELETE signing + error-propagation audit (offline, stdlib).

Proves: the request() branch signs and sends byte-identical bodies;
HTTP errors propagate (never swallowed into a fake success); both
client shapes produce identical signatures for identical inputs.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import unittest
from unittest import mock

from core.exchanges.delta.delta_auth import (
    DeltaSignedREST, build_prehash, sign,
)

SECRET = "phase154-secret"
KEY = "phase154-key"


class RequestClient:
    def __init__(self, exc=None):
        self.calls = []
        self.exc = exc

    def request(self, verb, path, content=b"", headers=None):
        self.calls.append((verb, path, bytes(content), dict(headers or {})))
        if self.exc is not None:
            raise self.exc
        resp = mock.Mock()
        resp.json.return_value = {"success": True, "result": {}}
        return resp


class LegacyClient:
    def __init__(self):
        self.calls = []

    def delete(self, path, content=b"", headers=None):
        self.calls.append(("delete", path, bytes(content), dict(headers or {})))
        resp = mock.Mock()
        resp.json.return_value = {"success": True, "result": {}}
        return resp


def make(authenticated=True, client=None):
    c = DeltaSignedREST(api_key=KEY if authenticated else "",
                        api_secret=SECRET if authenticated else "",
                        # Offline delete-signing bytes test on fake clients;
                        # write authority is not the subject here.
                        enforce_write_authority=False)
    c.client = client if client is not None else RequestClient()
    return c


class TestDeleteCanonicalBytes(unittest.TestCase):
    def test_signed_body_equals_sent_body(self):
        c = make(client=RequestClient())
        payload = {"id": 2175085905, "product_id": 84}
        with mock.patch("core.exchanges.delta.delta_auth.time.time", return_value=2000000000.0):
            c.delete("/v2/orders", payload=payload)
        verb, path, content, headers = c.client.calls[0]
        self.assertEqual(verb, "DELETE")
        expected_body = json.dumps(payload, separators=(",", ":"))
        self.assertEqual(content.decode(), expected_body)
        self.assertEqual(headers["signature"],
                         sign(SECRET, build_prehash("DELETE", "2000000000", "/v2/orders", expected_body)))
        self.assertEqual(headers["timestamp"], "2000000000")
        # Independent recomputation, not via module helpers for the HMAC leg.
        expect = hmac.new(SECRET.encode(), ("DELETE2000000000/v2/orders" + expected_body).encode(),
                          hashlib.sha256).hexdigest()
        self.assertEqual(headers["signature"], expect)

    def test_both_branches_sign_identically(self):
        bodies = []
        for client in (RequestClient(), LegacyClient()):
            c = make(client=client)
            with mock.patch("core.exchanges.delta.delta_auth.time.time", return_value=2000000000.0):
                c.delete("/v2/orders", payload={"id": 1, "product_id": 84})
            bodies.append((client.calls[0][2], client.calls[0][3]["signature"]))
        self.assertEqual(bodies[0], bodies[1])

    def test_empty_body_signs_bare_path(self):
        c = make(client=RequestClient())
        with mock.patch("core.exchanges.delta.delta_auth.time.time", return_value=2000000000.0):
            c.delete("/v2/orders/123")
        _, _, content, headers = c.client.calls[0]
        self.assertEqual(content, b"")
        self.assertEqual(headers["signature"], sign(SECRET, "DELETE2000000000/v2/orders/123"))


class TestDeleteErrorPropagation(unittest.TestCase):
    def test_http_error_is_never_success(self):
        import httpx
        boom = httpx.HTTPStatusError("bad", request=mock.Mock(), response=mock.Mock())
        c = make(client=RequestClient(exc=boom))
        with self.assertRaises(httpx.HTTPStatusError):
            c.delete("/v2/orders", payload={"id": 1, "product_id": 84})

    def test_unsuccessful_payload_is_returned_not_raised(self):
        # The client surfaces the venue envelope; SUCCESS interpretation
        # belongs to callers (exp._cancel re-queries state). A 200 with
        # success:false must be visible, not converted.
        class Envelope(RequestClient):
            pass
        c = make(client=RequestClient())
        denied = {"success": False, "error": {"code": "out_of_bankruptcy"}}
        with mock.patch.object(RequestClient, "request", return_value=(
                mock.Mock(**{"json.return_value": denied}))):
            out = c.delete("/v2/orders", payload={"id": 1, "product_id": 84})
        self.assertEqual(out, denied)


if __name__ == "__main__":
    unittest.main()
