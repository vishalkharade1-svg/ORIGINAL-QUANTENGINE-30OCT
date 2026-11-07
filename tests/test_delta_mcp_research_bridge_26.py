import json
import unittest

from research.integrations.delta_mcp_evidence_bundle import build_evidence_bundle
from research.integrations.delta_mcp_observations import normalize_public_response
from research.integrations.delta_mcp_research_bridge import bundle_to_dataset, bundle_to_rows
from core.research.dataset import DatasetSource


def obs(tool, result, symbol="BTCUSD"):
    return normalize_public_response(tool, {"success": True, "result": result}, requested_symbol=symbol)


class TestDeltaMcpResearchBridge26(unittest.TestCase):
    def _bundle(self):
        return build_evidence_bundle([
            obs("get_product", {"symbol": "BTCUSD", "state": "live"}),
            obs("get_candles", [{"time": 1700000000, "open": "100", "high": "101", "low": "99", "close": "100"}]),
            obs("get_recent_trades", [{"time": 1700000000, "price": "100", "size": "1"}]),
            obs("get_orderbook", [{"price": "100", "size": "1"}]),
            obs("get_oi_history", [{"time": 1700000000, "value": "10"}]),
            obs("get_funding_history", [{"time": 1700000000, "rate": "0.001"}]),
        ], symbol="BTCUSD")

    def test_all_domains_remain_visible(self):
        rows = bundle_to_rows(self._bundle())
        self.assertEqual(len(rows), 10)
        self.assertEqual({r.category for r in rows}, {"DELTA_MCP_" + d.upper() for d in (
            "product", "candles", "trades", "orderbook", "open_interest", "funding",
            "mark_price", "settlement", "options", "indices")})

    def test_rows_use_research_source_only(self):
        self.assertTrue(all(r.source == DatasetSource.RESEARCH for r in bundle_to_rows(self._bundle())))

    def test_unavailable_domain_is_explicit(self):
        row = next(r for r in bundle_to_rows(self._bundle()) if r.category == "DELTA_MCP_OPTIONS")
        self.assertEqual(row.result, "UNAVAILABLE")
        self.assertIn("observation", row.kv["missing"])

    def test_bundle_identity_is_preserved(self):
        b = self._bundle()
        rows = bundle_to_rows(b)
        self.assertTrue(all(r.kv["bundle_identity"] == b.content_identity for r in rows))

    def test_observation_identity_is_stable(self):
        rows1 = bundle_to_rows(self._bundle())
        rows2 = bundle_to_rows(self._bundle())
        self.assertEqual([r.row_id for r in rows1], [r.row_id for r in rows2])
        self.assertEqual([r.to_dict() for r in rows1], [r.to_dict() for r in rows2])

    def test_dataset_is_9i_compatible(self):
        ds = bundle_to_dataset(self._bundle())
        self.assertEqual(ds.row_count(), 10)
        self.assertEqual(len(ds.rows(DatasetSource.RESEARCH)), 10)

    def test_dataset_serialization_is_deterministic(self):
        a = bundle_to_dataset(self._bundle()).to_dict()
        b = bundle_to_dataset(self._bundle()).to_dict()
        self.assertEqual(json.dumps(a, sort_keys=True, separators=(",", ":")), json.dumps(b, sort_keys=True, separators=(",", ":")))

    def test_authentication_claim_cannot_be_invented(self):
        rows = bundle_to_rows(self._bundle())
        self.assertTrue(all(r.kv["venue_authentication"] == "UNVERIFIED" for r in rows))

    def test_consistency_errors_are_visible(self):
        b = build_evidence_bundle([obs("get_product", {"symbol": "BTCUSD"})], symbol="ETHUSD")
        rows = bundle_to_rows(b)
        self.assertTrue(all("symbol_mismatch:get_product:BTCUSD" in r.kv["consistency_errors"] for r in rows))

    def test_bridge_has_no_production_imports(self):
        from pathlib import Path
        text = Path("research/integrations/delta_mcp_research_bridge.py").read_text(encoding="utf-8")
        self.assertNotIn("core.execution", text)
        self.assertNotIn("core.live", text)
        self.assertNotIn("core.broker", text)


if __name__ == "__main__":
    unittest.main()
