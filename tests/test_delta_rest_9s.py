"""
Phase 9S — Delta REST 429 backoff + Retry-After
"""

import unittest
from unittest.mock import Mock, patch
import httpx

from core.exchanges.delta.delta_rest import DeltaREST


def _resp(status_code, headers=None, json_data=None, request=None):
    req = request or httpx.Request("GET", "https://api.delta.exchange/v2/products")
    resp = httpx.Response(status_code=status_code, headers=headers or {}, request=req, json=json_data or {"result": []})
    return resp


class TestDeltaRest429(unittest.TestCase):

    def test_429_retry_with_retry_after_then_success(self):
        client = DeltaREST(max_retries=2, backoff_base=0.01)
        # First 429 with Retry-After 0.01, then 200
        mock_client = Mock()
        mock_client.get.side_effect = [
            _resp(429, headers={"Retry-After": "0.01"}),
            _resp(200, json_data={"result": [{"id": 1}]}),
        ]
        client.client = mock_client
        with patch("core.exchanges.delta.delta_rest.time.sleep") as mock_sleep:
            data = client.get("/v2/products")
            self.assertEqual(data["result"][0]["id"], 1)
            mock_sleep.assert_called_once()
            # sleep called with ~0.01
            self.assertAlmostEqual(mock_sleep.call_args[0][0], 0.01, places=2)

    def test_429_exhaustion_raises(self):
        client = DeltaREST(max_retries=1, backoff_base=0.01)
        mock_client = Mock()
        mock_client.get.side_effect = [
            _resp(429, headers={"Retry-After": "0.01"}),
            _resp(429, headers={"Retry-After": "0.01"}),
        ]
        client.client = mock_client
        with patch("core.exchanges.delta.delta_rest.time.sleep"):
            with self.assertRaises(httpx.HTTPStatusError):
                client.get("/v2/products")

    def test_500_retry(self):
        client = DeltaREST(max_retries=1, backoff_base=0.01)
        mock_client = Mock()
        mock_client.get.side_effect = [
            _resp(500),
            _resp(200, json_data={"result": []}),
        ]
        client.client = mock_client
        with patch("core.exchanges.delta.delta_rest.time.sleep") as mock_sleep:
            data = client.get("/v2/products")
            self.assertEqual(data["result"], [])
            mock_sleep.assert_called_once()

    def test_non_retryable_400_raises_immediately(self):
        client = DeltaREST(max_retries=2, backoff_base=0.01)
        mock_client = Mock()
        mock_client.get.return_value = _resp(400)
        client.client = mock_client
        with patch("core.exchanges.delta.delta_rest.time.sleep") as mock_sleep:
            with self.assertRaises(httpx.HTTPStatusError):
                client.get("/v2/products")
            mock_sleep.assert_not_called()
