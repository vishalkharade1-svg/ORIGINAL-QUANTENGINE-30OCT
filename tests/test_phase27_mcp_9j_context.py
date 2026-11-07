import unittest
from core.research.dataset import ResearchDataset, ResearchRow, DatasetSource
from research.integrations.delta_mcp_discovery_context import summarize_mcp_context, context_limitations

class TestPhase27(unittest.TestCase):
    def test_empty_context_is_explicit(self):
        c = summarize_mcp_context(ResearchDataset(), symbol="BTCUSDT")
        self.assertEqual(c["available_domains"], ())
        self.assertEqual(c["venue_authentication"], "UNVERIFIED")
        self.assertEqual(c["hypothesis_generation"], "UNCHANGED")

    def test_context_reads_9i_rows(self):
        rows = [
            ResearchRow(source=DatasetSource.RESEARCH, instrument_id="BTCUSDT",
                        category="DELTA_MCP_TRADES", result="PARTIAL",
                        source_id="x", kv={"source":"delta_mcp_public", "mcp_domain":"trades"}),
            ResearchRow(source=DatasetSource.RESEARCH, instrument_id="BTCUSDT",
                        category="DELTA_MCP_ORDERBOOK", result="VERIFIED",
                        source_id="y", kv={"source":"delta_mcp_public", "mcp_domain":"orderbook"}),
        ]
        c = summarize_mcp_context(ResearchDataset(rows), "BTCUSDT")
        self.assertEqual(c["available_domains"], ("orderbook", "trades"))
        self.assertIn("funding", c["unavailable_domains"])

    def test_other_symbol_is_filtered(self):
        row = ResearchRow(source=DatasetSource.RESEARCH, instrument_id="ETHUSDT",
                          category="DELTA_MCP_TRADES", result="VERIFIED",
                          source_id="z", kv={"source":"delta_mcp_public", "mcp_domain":"trades"})
        c = summarize_mcp_context(ResearchDataset([row]), "BTCUSDT")
        self.assertEqual(c["available_domains"], ())

    def test_limitations_are_deterministic_and_honest(self):
        c = summarize_mcp_context(ResearchDataset(), "BTCUSDT")
        notes = context_limitations(c)
        self.assertEqual(notes, context_limitations(c))
        self.assertTrue(any("UNVERIFIED" in x for x in notes))
        self.assertTrue(any("does not create hypotheses" in x for x in notes))

if __name__ == "__main__":
    unittest.main()
