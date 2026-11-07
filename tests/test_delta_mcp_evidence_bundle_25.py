import json
import unittest

from research.integrations.delta_mcp_evidence_bundle import (
    DOMAINS, EvidenceBundleError, build_evidence_bundle,
)
from research.integrations.delta_mcp_observations import normalize_public_response


def obs(tool, result, symbol="BTCUSD"):
    return normalize_public_response(tool, {"success": True, "result": result}, requested_symbol=symbol)


class TestDeltaMcpEvidenceBundle25(unittest.TestCase):
    def test_empty_bundle_is_explicitly_unavailable(self):
        b = build_evidence_bundle([], symbol="BTCUSD")
        self.assertEqual(len(DOMAINS), 10)
        self.assertTrue(all(v == "UNAVAILABLE" for _, v in b.domain_status))
        self.assertEqual(b.venue_authentication, "UNVERIFIED")

    def test_canonical_multi_domain_bundle(self):
        items = [
            obs("get_product", {"symbol": "BTCUSD", "state": "live"}),
            obs("get_candles", [{"time": 1, "open": "100", "high": "101", "low": "99", "close": "100"}]),
            obs("get_recent_trades", [{"time": 1, "price": "100", "size": "1"}]),
            obs("get_orderbook", [{"price": "100", "size": "1"}]),
            obs("get_oi_history", [{"time": 1, "value": "10"}]),
            obs("get_funding_history", [{"time": 1, "rate": "0.001"}]),
        ]
        b1 = build_evidence_bundle(items, symbol="BTCUSD")
        b2 = build_evidence_bundle(items, symbol="BTCUSD")
        self.assertEqual(b1.content_identity, b2.content_identity)
        self.assertEqual(dict(b1.domain_status)["candles"], "VERIFIED")
        self.assertEqual(dict(b1.domain_status)["trades"], "VERIFIED")
        self.assertEqual(dict(b1.domain_status)["orderbook"], "VERIFIED")
        self.assertEqual(dict(b1.domain_status)["funding"], "VERIFIED")
        self.assertEqual(dict(b1.domain_status)["options"], "UNAVAILABLE")

    def test_symbol_mismatch_is_retained(self):
        item = obs("get_ticker", {"symbol": "BTCUSD", "price": "100"})
        b = build_evidence_bundle([item], symbol="ETHUSD")
        self.assertIn("symbol_mismatch:get_ticker:BTCUSD", b.consistency_errors)

    def test_duplicate_domain_is_not_silently_overwritten(self):
        a = obs("get_candles", [{"time": 1, "open": "1", "high": "2", "low": "1", "close": "2"}])
        b = obs("get_candles", [{"time": 2, "open": "2", "high": "3", "low": "2", "close": "3"}])
        bundle = build_evidence_bundle([a, b], symbol="BTCUSD")
        self.assertIn("duplicate_domain:candles", bundle.consistency_errors)
        self.assertEqual(dict(bundle.domain_status)["candles"], "VERIFIED")

    def test_bundle_serializes_without_authentication_claim(self):
        item = obs("get_product", {"symbol": "BTCUSD", "state": "live"})
        data = build_evidence_bundle([item], symbol="BTCUSD").to_dict()
        encoded = json.dumps(data, sort_keys=True)
        self.assertIn('"venue_authentication": "UNVERIFIED"', encoded)

    def test_bundle_rejects_manual_authentication(self):
        item = obs("get_product", {"symbol": "BTCUSD"})
        with self.assertRaises(EvidenceBundleError):
            from research.integrations.delta_mcp_evidence_bundle import EvidenceBundle
            EvidenceBundle("BTCUSD", (item,), (("product", "VERIFIED"),), (), "0" * 64, "VERIFIED")


if __name__ == "__main__":
    unittest.main()
