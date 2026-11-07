from __future__ import annotations

import unittest

from core.research.acquisition.multi_symbol import build_manifest
from core.research.acquisition.accumulator import AccumulationError


KW = dict(boundary=100, expected_venue="DELTA",
          expected_source="Delta /v2/history/candles",
          expected_method="HistoricalLoader.candles_paginated",
          expected_timeframe="1m")


def batch(symbol, start):
    rows = [{"time": start, "open": "1", "high": "2", "low": "1",
             "close": "2", "volume": "3"}]
    prov = [{"time": start, "venue": "DELTA",
             "acquisition_source": "Delta /v2/history/candles",
             "acquisition_method": "HistoricalLoader.candles_paginated",
             "symbol": symbol, "timeframe": "1m"}]
    return {"symbol": symbol, "rows": rows, "provenance": prov}


class TestPhase37MultiSymbolAcquisition(unittest.TestCase):
    def test_same_timestamp_across_symbols_is_valid(self):
        result = build_manifest([batch("BTCUSDT", 120), batch("ETHUSDT", 120)], **KW)
        self.assertEqual(result["symbol_count"], 2)
        self.assertEqual([x["symbol"] for x in result["symbols"]], ["BTCUSDT", "ETHUSDT"])

    def test_duplicate_symbol_fails(self):
        with self.assertRaisesRegex(AccumulationError, "DUPLICATE_SYMBOL"):
            build_manifest([batch("BTCUSDT", 120), batch("BTCUSDT", 180)], **KW)

    def test_symbol_provenance_mismatch_fails(self):
        b = batch("ETHUSDT", 120)
        b["provenance"][0]["symbol"] = "BTCUSDT"
        with self.assertRaisesRegex(AccumulationError, "PROVENANCE_METADATA_MISMATCH"):
            build_manifest([b], **KW)

    def test_order_is_deterministic(self):
        a = build_manifest([batch("ETHUSDT", 120), batch("BTCUSDT", 180)], **KW)
        b = build_manifest([batch("BTCUSDT", 180), batch("ETHUSDT", 120)], **KW)
        self.assertEqual(a, b)

    def test_cross_symbol_overlap_does_not_merge_rows(self):
        result = build_manifest([batch("BTCUSDT", 120), batch("ETHUSDT", 120)], **KW)
        self.assertEqual(result["symbols"][0]["symbol"], "BTCUSDT")
        self.assertEqual(result["symbols"][1]["symbol"], "ETHUSDT")
        self.assertNotEqual(result["manifest_id"], "")


if __name__ == "__main__":
    unittest.main()
