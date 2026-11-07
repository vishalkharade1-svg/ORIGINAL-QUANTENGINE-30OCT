from __future__ import annotations
import unittest
from core.research.readiness.symbol_coverage import audit

class TestPhase36ProvenanceSymbolCoverage(unittest.TestCase):
    def test_row_provenance_establishes_symbol(self):
        rows = [{"time": 1}, {"time": 2}]
        prov = [
            {"time": 1, "symbol": "BTCUSDT"},
            {"time": 2, "symbol": "BTCUSDT"},
        ]
        result = audit(rows, required_bars=2, provenance=prov)
        self.assertEqual(result["symbol_source"], "row_level_provenance")
        self.assertEqual(result["missing_symbol_rows"], 0)
        self.assertEqual(result["symbols"][0]["status"], "VERIFIED")

    def test_provenance_mismatch_fails_closed_to_explicit(self):
        rows = [{"time": 1, "symbol": "ETHUSDT"}]
        prov = [{"time": 2, "symbol": "BTCUSDT"}]
        result = audit(rows, provenance=prov)
        self.assertEqual(result["symbol_source"], "explicit_row_metadata_fallback")
        self.assertEqual(result["symbol_source_error"], "PROVENANCE_COVERAGE_MISMATCH")
        self.assertEqual(result["symbols"][0]["symbol"], "ETHUSDT")

    def test_conflicting_provenance_fails_closed(self):
        rows = [{"time": 1}]
        prov = [{"time": 1, "symbol": "BTCUSDT"}, {"time": 1, "symbol": "ETHUSDT"}]
        result = audit(rows, provenance=prov)
        self.assertEqual(result["symbol_source_error"], "CONFLICTING_PROVENANCE")
        self.assertEqual(result["missing_symbol_rows"], 1)

    def test_deterministic(self):
        rows = [{"time": 2}, {"time": 1}]
        prov = [{"time": 1, "symbol": "BTCUSDT"}, {"time": 2, "symbol": "BTCUSDT"}]
        self.assertEqual(audit(rows, provenance=prov), audit(list(reversed(rows)), provenance=list(reversed(prov))))

if __name__ == "__main__":
    unittest.main()
