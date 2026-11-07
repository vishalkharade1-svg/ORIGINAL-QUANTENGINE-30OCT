"""Phase134: DeltaSignedREST.delete works on httpx 0.27 and 0.28.

Regression for the live-cancel outage: httpx 0.28 removed `content` from
the delete() shortcut, so cancels never reached the venue (TypeError
swallowed -> straggler). delete() must use request() when available.
"""

from __future__ import annotations

import unittest
from unittest import mock


class _RequestClient:
    def __init__(self):
        self.calls = []

    def request(self, verb, path, content=b"", headers=None):
        self.calls.append((verb, path, content, headers))
        resp = mock.Mock()
        resp.json.return_value = {"success": True, "result": {}}
        return resp


class TestDeleteCompat134(unittest.TestCase):
    def test_delete_uses_request_when_available(self):
        from core.exchanges.delta.delta_auth import DeltaSignedREST
        c = DeltaSignedREST(api_key="K", api_secret="S", base_url="https://x",
                            enforce_write_authority=False)
        fake = _RequestClient()
        c.client = fake
        with mock.patch("core.exchanges.delta.delta_auth.time.time", return_value=1.0):
            c.delete("/v2/orders", payload={"id": 1, "product_id": 84})
        verb, path, content, headers = fake.calls[0]
        self.assertEqual(verb, "DELETE")
        self.assertIn(b'"id":1', content)

    def test_delete_falls_back_to_shortcut_for_legacy_fakes(self):
        from core.exchanges.delta.delta_auth import DeltaSignedREST
        c = DeltaSignedREST(api_key="K", api_secret="S", base_url="https://x",
                            enforce_write_authority=False)

        class Legacy:
            def __init__(self):
                self.calls = []

            def delete(self, path, content=b"", headers=None):
                self.calls.append(("delete", path, content, headers))
                resp = mock.Mock()
                resp.json.return_value = {"success": True, "result": {}}
                return resp

        c.client = Legacy()
        with mock.patch("core.exchanges.delta.delta_auth.time.time", return_value=1.0):
            c.delete("/v2/orders/123")
        self.assertEqual(c.client.calls[0][0], "delete")


if __name__ == "__main__":
    unittest.main()
