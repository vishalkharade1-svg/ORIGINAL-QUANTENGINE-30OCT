import unittest

from core.research.dataset import ResearchDataset, ResearchRow, DatasetSource
from core.research.regime.engine import OpportunityDiscoveryEngine
from research.integrations.delta_mcp_regime_context import (
    summarize_regime_context,
    regime_context_limitations,
)


class _C:
    def __init__(self, ts, close=100.0):
        self.timestamp = ts
        self.open = close
        self.high = close + 1.0
        self.low = close - 1.0
        self.close = close


class TestPhase28(unittest.TestCase):
    def test_empty_context_is_honest(self):
        c = summarize_regime_context(ResearchDataset(), "BTCUSDT")
        self.assertEqual(c["conditioning_domains_available"], ())
        self.assertEqual(c["regime_labels_from_mcp"], ())
        self.assertEqual(c["regime_detection"], "UNCHANGED")
        self.assertEqual(c["venue_authentication"], "UNVERIFIED")

    def test_public_domains_become_context_only(self):
        rows = [
            ResearchRow(source=DatasetSource.RESEARCH, instrument_id="BTCUSDT",
                        category="DELTA_MCP_ORDERBOOK", result="VERIFIED",
                        source_id="ob", kv={"source":"delta_mcp_public", "mcp_domain":"orderbook"}),
            ResearchRow(source=DatasetSource.RESEARCH, instrument_id="BTCUSDT",
                        category="DELTA_MCP_FUNDING", result="PARTIAL",
                        source_id="fund", kv={"source":"delta_mcp_public", "mcp_domain":"funding"}),
            ResearchRow(source=DatasetSource.RESEARCH, instrument_id="BTCUSDT",
                        category="DELTA_MCP_PRODUCT", result="VERIFIED",
                        source_id="prod", kv={"source":"delta_mcp_public", "mcp_domain":"product"}),
        ]
        c = summarize_regime_context(ResearchDataset(rows), "BTCUSDT")
        self.assertEqual(c["conditioning_domains_available"], ("funding", "orderbook"))
        self.assertEqual(c["regime_labels_from_mcp"], ())

    def test_other_symbol_is_not_used(self):
        row = ResearchRow(source=DatasetSource.RESEARCH, instrument_id="ETHUSDT",
                          category="DELTA_MCP_TRADES", result="VERIFIED",
                          source_id="x", kv={"source":"delta_mcp_public", "mcp_domain":"trades"})
        c = summarize_regime_context(ResearchDataset([row]), "BTCUSDT")
        self.assertEqual(c["conditioning_domains_available"], ())

    def test_limitations_are_deterministic(self):
        c = summarize_regime_context(ResearchDataset(), "BTCUSDT")
        self.assertEqual(regime_context_limitations(c), regime_context_limitations(c))
        self.assertTrue(any("regime labels" in x for x in regime_context_limitations(c)))

    def test_9k_run_preserves_detector_and_adds_context_limitations(self):
        candles = [_C(i) for i in range(50)]
        row = ResearchRow(source=DatasetSource.RESEARCH, instrument_id="BTCUSDT",
                          category="DELTA_MCP_ORDERBOOK", result="VERIFIED",
                          source_id="ob", kv={"source":"delta_mcp_public", "mcp_domain":"orderbook"})
        ds = ResearchDataset([row])
        report = OpportunityDiscoveryEngine(candles=candles, min_cell_n=5).run(
            records=[], base_config={}, candidates=[], symbol="BTCUSDT", dataset=ds)
        self.assertFalse(report.is_production_ready)
        self.assertTrue(any("conditioning domains" in x for x in report.limitations))
        self.assertTrue(any("regime labels" in x for x in report.limitations))
        self.assertEqual(report.to_dict()["limitations"], list(report.limitations))


if __name__ == "__main__":
    unittest.main()
