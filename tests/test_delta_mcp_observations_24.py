"""Phase 24: deterministic normalization of Delta MCP public observations."""
from __future__ import annotations

import unittest

from research.integrations.delta_mcp_observations import (
    ObservationError,
    SCHEMA,
    normalize_public_response,
)


class TestDeltaMcpObservationNormalization(unittest.TestCase):
    def test_candle_response_verified(self):
        body = {"success": True, "result": {"symbol": "BTCUSD", "candles": [
            {"time": 1000, "open": "100", "high": "110", "low": "99", "close": "105"},
            {"time": 1060, "open": "105", "high": "112", "low": "104", "close": "111"},
        ]}}
        obs = normalize_public_response("get_candles", body, requested_symbol="BTCUSD")
        self.assertEqual(obs.status, "VERIFIED")
        self.assertEqual(dict(obs.observed)["valid_rows"], 2)
        self.assertEqual(len(obs.content_identity), 64)

    def test_candle_bad_ohlc_is_partial(self):
        body = {"success": True, "result": {"symbol": "BTCUSD", "candles": [
            {"time": 1000, "open": "100", "high": "90", "low": "99", "close": "105"},
        ]}}
        obs = normalize_public_response("get_candles", body, requested_symbol="BTCUSD")
        self.assertEqual(obs.status, "UNAVAILABLE")
        self.assertEqual(dict(obs.observed)["invalid_rows"], 1)

    def test_trades_require_price_and_size(self):
        body = {"success": True, "result": {"trades": [
            {"time": 1000, "price": "100", "size": "2"},
        ]}}
        obs = normalize_public_response("get_recent_trades", body, requested_symbol="BTCUSD")
        self.assertEqual(obs.status, "VERIFIED")

    def test_missing_history_fields_is_unavailable(self):
        body = {"success": True, "result": {"history": [{"time": 1000}]}}
        obs = normalize_public_response("get_funding_history", body, requested_symbol="BTCUSD")
        self.assertEqual(obs.status, "UNAVAILABLE")

    def test_product_preserves_observed_strings(self):
        body = {"success": True, "result": {
            "symbol": "BTCUSD", "state": "live", "tick_size": "0.1",
            "maker_commission_rate": "0.0002", "taker_commission_rate": "0.0005",
        }}
        obs = normalize_public_response("get_product", body, requested_symbol="BTCUSD")
        self.assertEqual(obs.status, "VERIFIED")
        self.assertEqual(dict(obs.observed)["tick_size"], "0.1")

    def test_symbol_mismatch_fails_closed(self):
        with self.assertRaises(ObservationError):
            normalize_public_response("get_product", {"success": True, "result": {"symbol": "ETHUSD"}}, requested_symbol="BTCUSD")

    def test_failed_response_fails_closed(self):
        with self.assertRaises(ObservationError):
            normalize_public_response("get_candles", {"success": False, "error": {"code": "x"}}, requested_symbol="BTCUSD")

    def test_identity_is_repeatable(self):
        body = {"success": True, "result": {"trades": [{"time": 1000, "price": "100.0", "size": "1"}]}}
        a = normalize_public_response("get_recent_trades", body, requested_symbol="BTCUSD")
        b = normalize_public_response("get_recent_trades", body, requested_symbol="BTCUSD")
        self.assertEqual(a.content_identity, b.content_identity)
        self.assertEqual(a.to_dict()["schema"], SCHEMA)

    def test_identity_changes_with_observation(self):
        a = normalize_public_response("get_recent_trades", {"success": True, "result": {"trades": [{"time": 1000, "price": "100", "size": "1"}]}}, requested_symbol="BTCUSD")
        b = normalize_public_response("get_recent_trades", {"success": True, "result": {"trades": [{"time": 1000, "price": "101", "size": "1"}]}}, requested_symbol="BTCUSD")
        self.assertNotEqual(a.content_identity, b.content_identity)

    def test_orderbook_empty_is_unavailable(self):
        obs = normalize_public_response("get_orderbook", {"success": True, "result": []}, requested_symbol="BTCUSD")
        self.assertEqual(obs.status, "UNAVAILABLE")

    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):
            normalize_public_response("place_order", {"success": True, "result": {}}, requested_symbol="BTCUSD")


if __name__ == "__main__":
    unittest.main()
