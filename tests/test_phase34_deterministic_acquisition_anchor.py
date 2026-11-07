"""Phase 34: deterministic acquisition anchor tests."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

from data.historical_loader import HistoricalLoader
from scripts.fetch_oos_topup import GATE_A_END, _parse_args


class TestPhase34DeterministicAcquisitionAnchor(unittest.TestCase):
    def test_operator_script_has_no_wall_clock_dependency(self):
        source = (Path(__file__).resolve().parents[1] /
                  "scripts" / "fetch_oos_topup.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name for node in ast.walk(tree)
            if isinstance(node, ast.Import) for alias in node.names
        }
        imported.update(
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertNotIn("time", imported)
        self.assertNotIn("datetime", imported)

    def test_operator_requires_explicit_end_timestamp(self):
        with self.assertRaises(SystemExit):
            _parse_args([])

    def test_operator_rejects_boundary_or_earlier_anchor(self):
        with self.assertRaises(SystemExit):
            _parse_args(["--end-timestamp", str(GATE_A_END)])

    def test_positive_explicit_anchor_is_parsed(self):
        args = _parse_args(["--end-timestamp", str(GATE_A_END + 3600)])
        self.assertEqual(args.end_timestamp, GATE_A_END + 3600)
        self.assertEqual(args.extra_candles, 120)

    def test_paginated_loader_uses_explicit_anchor_not_wall_clock(self):
        loader = HistoricalLoader()
        calls = []

        def fake_fetch(symbol, resolution, start, end):
            calls.append((symbol, resolution, start, end))
            # One deterministic candle, then stop pagination.
            return {"success": True, "result": [{
                "time": end - 60,
                "open": 1.0, "high": 1.0,
                "low": 1.0, "close": 1.0, "volume": 1.0,
            }]}

        try:
            with patch.object(loader, "_fetch", side_effect=fake_fetch):
                with patch("data.historical_loader.time.time",
                           return_value=9999999999):
                    first = loader.candles_paginated(
                        "BTCUSDT", "1m", total_candles=1,
                        request_delay=0, end_timestamp=1234567890)
                calls_first = list(calls)
                calls.clear()
                with patch("data.historical_loader.time.time",
                           return_value=1111111111):
                    second = loader.candles_paginated(
                        "BTCUSDT", "1m", total_candles=1,
                        request_delay=0, end_timestamp=1234567890)
        finally:
            loader.close()

        self.assertEqual(first, second)
        self.assertEqual(calls_first, calls)
        self.assertEqual(calls_first[0][3], 1234567890)

    def test_invalid_anchor_fails_before_fetch(self):
        loader = HistoricalLoader()
        try:
            with self.assertRaises(ValueError):
                loader.candles_paginated(
                    "BTCUSDT", "1m", total_candles=1,
                    end_timestamp=0)
        finally:
            loader.close()


if __name__ == "__main__":
    unittest.main()
