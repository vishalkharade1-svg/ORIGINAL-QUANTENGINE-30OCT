from __future__ import annotations

import unittest

from core.research.readiness.symbol_aggregation import aggregate_symbol_results


class TestPhase38SymbolAggregation(unittest.TestCase):
    def test_preserves_independent_statuses(self):
        result = aggregate_symbol_results([
            {"symbol": "BTCUSDT", "status": "VALIDATED", "rows": 100, "trades": 20},
            {"symbol": "ETHUSDT", "status": "REJECTED", "rows": 100, "trades": 20},
        ], required_symbols=2)
        self.assertEqual(result["status_counts"]["VALIDATED"], 1)
        self.assertEqual(result["status_counts"]["REJECTED"], 1)
        self.assertEqual(result["missing_required_symbols"], 0)
        self.assertEqual(result["cross_symbol_evidence"], "AVAILABLE")

    def test_missing_symbol_is_not_rejected(self):
        result = aggregate_symbol_results([
            {"symbol": "BTCUSDT", "status": "VALIDATED", "rows": 100, "trades": 20},
        ], required_symbols=2)
        self.assertEqual(result["status_counts"]["REJECTED"], 0)
        self.assertEqual(result["missing_required_symbols"], 1)
        self.assertEqual(result["cross_symbol_evidence"], "UNAVAILABLE")

    def test_inconclusive_is_distinct(self):
        result = aggregate_symbol_results([
            {"symbol": "BTCUSDT", "status": "INCONCLUSIVE", "rows": 10, "trades": 1},
        ], required_symbols=1)
        self.assertEqual(result["status_counts"]["INCONCLUSIVE"], 1)
        self.assertEqual(result["status_counts"]["REJECTED"], 0)

    def test_deterministic_order(self):
        a = aggregate_symbol_results([
            {"symbol": "ETHUSDT", "status": "PROMISING", "rows": 5, "trades": 2},
            {"symbol": "BTCUSDT", "status": "VALIDATED", "rows": 5, "trades": 2},
        ], required_symbols=2)
        b = aggregate_symbol_results([
            {"symbol": "BTCUSDT", "status": "VALIDATED", "rows": 5, "trades": 2},
            {"symbol": "ETHUSDT", "status": "PROMISING", "rows": 5, "trades": 2},
        ], required_symbols=2)
        self.assertEqual(a, b)

    def test_duplicate_symbol_fails(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SYMBOL"):
            aggregate_symbol_results([
                {"symbol": "BTCUSDT", "status": "VALIDATED"},
                {"symbol": "BTCUSDT", "status": "REJECTED"},
            ])

    def test_invalid_status_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "INVALID_SYMBOL_STATUS"):
            aggregate_symbol_results([{"symbol": "BTCUSDT", "status": "ROBUST"}])

    def test_unavailable_is_preserved(self):
        result = aggregate_symbol_results([
            {"symbol": "SOLUSDT", "status": "UNAVAILABLE", "rows": 0, "trades": 0},
        ], required_symbols=1)
        self.assertEqual(result["status_counts"]["UNAVAILABLE"], 1)
        self.assertEqual(result["cross_symbol_evidence"], "AVAILABLE")


if __name__ == "__main__":
    unittest.main()
