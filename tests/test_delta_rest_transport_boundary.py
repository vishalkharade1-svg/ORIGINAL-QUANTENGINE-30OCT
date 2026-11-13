"""Credential-boundary regressions for Delta signed REST transport targets."""

import unittest
from unittest.mock import Mock

from core.exchanges.delta.delta_auth import DeltaSignedREST


class TestDeltaRESTTransportBoundary(unittest.TestCase):
    def _client(self, base_url):
        rest = DeltaSignedREST(
            api_key="test-api-key",
            api_secret="test-api-secret",
            base_url=base_url,
        )
        rest.client = Mock()
        return rest

    def test_authenticated_http_origin_is_rejected_before_get(self):
        rest = self._client("http://testnet.delta.example")
        with self.assertRaisesRegex(ValueError, "require HTTPS"):
            rest.get("/v2/orders")
        rest.client.get.assert_not_called()

    def test_absolute_url_cannot_override_signed_request_origin(self):
        rest = self._client("https://testnet.delta.example")
        with self.assertRaisesRegex(ValueError, "must not override"):
            rest.get("https://attacker.example/collect")
        rest.client.get.assert_not_called()

    def test_authority_relative_and_backslash_paths_are_rejected(self):
        rest = self._client("https://testnet.delta.example")
        for path in ("//attacker.example/collect", r"/\\attacker.example\\collect"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    rest.get(path)
        rest.client.get.assert_not_called()

    def test_base_url_userinfo_and_query_are_rejected(self):
        for base_url in (
            "https://user:password@testnet.delta.example",
            "https://testnet.delta.example/?api_key=secret",
        ):
            with self.subTest(base_url=base_url):
                rest = self._client(base_url)
                with self.assertRaisesRegex(ValueError, "clean HTTP"):
                    rest.get("/v2/orders")
                rest.client.get.assert_not_called()

    def test_write_target_is_validated_before_authority_consumption(self):
        rest = self._client("https://testnet.delta.example")
        with self.assertRaisesRegex(ValueError, "must not override"):
            rest.post("https://attacker.example/orders", {"size": 1})
        rest.client.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
