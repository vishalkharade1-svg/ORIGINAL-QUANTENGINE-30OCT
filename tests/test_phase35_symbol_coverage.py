"""Phase 35: explicit multi-symbol OOS coverage tests."""
from __future__ import annotations

import unittest

from core.research.readiness.symbol_coverage import audit


class TestPhase35SymbolCoverage(unittest.TestCase):
    def test_missing_symbol_is_not_invented(self):
        result = audit([{"time": 1}, {"time": 2, "symbol": "BTCUSDT"}],
                       required_bars=1, required_trades=0)
        self.assertEqual(result["missing_symbol_rows"], 1)
        self.assertEqual(result["symbols"][0]["symbol"], "BTCUSDT")

    def test_symbol_status_is_independent(self):
        rows = [
            {"time": 1, "symbol": "BTCUSDT", "completed_trades": 2},
            {"time": 2, "symbol": "ETHUSDT", "completed_trades": 0},
        ]
        result = audit(rows, required_bars=1, required_trades=1)
        self.assertEqual(result["symbols"][0]["status"], "VERIFIED")
        self.assertEqual(result["symbols"][1]["status"], "INCONCLUSIVE")

    def test_order_is_deterministic(self):
        rows = [
            {"time": 2, "symbol": "ETHUSDT"},
            {"time": 1, "symbol": "BTCUSDT"},
        ]
        a = audit(rows)
        b = audit(list(reversed(rows)))
        self.assertEqual(a, b)

    def test_identity_changes_when_evidence_changes(self):
        a = audit([{"time": 1, "symbol": "BTCUSDT"}])
        b = audit([{"time": 2, "symbol": "BTCUSDT"}])
        self.assertNotEqual(a["audit_id"], b["audit_id"])

    def test_no_universal_claim_from_single_symbol(self):
        result = audit([{"time": 1, "symbol": "BTCUSDT"}],
                       required_bars=2, required_trades=1)
        self.assertNotEqual(result["symbols"][0]["status"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
