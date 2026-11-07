from __future__ import annotations

import json
import pathlib
import unittest

from core.research.extension.provenance import (
    build_row_provenance, provenance_identity, validate_row_provenance,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "data/history/BTCUSDT_1m_oos_topup.json"
ROW_PROV = ROOT / "data/history/BTCUSDT_1m_oos_topup.row_provenance.json"


class TestRowProvenance(unittest.TestCase):
    def rows(self):
        return [
            {"time": 180, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 3},
            {"time": 120, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 3},
        ]

    def test_a_deterministic_order_and_identity(self):
        records = build_row_provenance(
            self.rows(), venue="DELTA", acquisition_source="Delta /v2/history/candles",
            acquisition_method="HistoricalLoader.candles_paginated",
            symbol="BTCUSDT", timeframe="1m")
        self.assertEqual([r["time"] for r in records], [120, 180])
        self.assertEqual(provenance_identity(records), provenance_identity(list(records)))

    def test_b_exact_coverage_verified(self):
        records = build_row_provenance(
            self.rows(), venue="DELTA", acquisition_source="Delta /v2/history/candles",
            acquisition_method="HistoricalLoader.candles_paginated",
            symbol="BTCUSDT", timeframe="1m")
        self.assertEqual(validate_row_provenance(
            self.rows(), records, expected_venue="DELTA",
            expected_source="Delta /v2/history/candles",
            expected_method="HistoricalLoader.candles_paginated",
            expected_symbol="BTCUSDT", expected_timeframe="1m"),
            (True, "VERIFIED"))

    def test_c_missing_timestamp_rejected(self):
        records = build_row_provenance(
            self.rows(), venue="DELTA", acquisition_source="Delta /v2/history/candles",
            acquisition_method="HistoricalLoader.candles_paginated",
            symbol="BTCUSDT", timeframe="1m")[:-1]
        self.assertEqual(validate_row_provenance(
            self.rows(), records, expected_venue="DELTA",
            expected_source="Delta /v2/history/candles",
            expected_method="HistoricalLoader.candles_paginated",
            expected_symbol="BTCUSDT", expected_timeframe="1m")[1],
            "ROW_COUNT_MISMATCH")

    def test_d_metadata_tamper_rejected(self):
        records = build_row_provenance(
            self.rows(), venue="DELTA", acquisition_source="Delta /v2/history/candles",
            acquisition_method="HistoricalLoader.candles_paginated",
            symbol="BTCUSDT", timeframe="1m")
        records[0]["venue"] = "OTHER"
        self.assertEqual(validate_row_provenance(
            self.rows(), records, expected_venue="DELTA",
            expected_source="Delta /v2/history/candles",
            expected_method="HistoricalLoader.candles_paginated",
            expected_symbol="BTCUSDT", expected_timeframe="1m")[1],
            "METADATA_MISMATCH")


class TestRealArtifact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CACHE.exists() or not ROW_PROV.exists():
            raise unittest.SkipTest("operator-generated top-up row provenance absent")
        cls.cache = json.loads(CACHE.read_text(encoding="utf-8"))
        cls.prov = json.loads(ROW_PROV.read_text(encoding="utf-8"))

    def test_e_row_count_and_identity(self):
        rows = self.cache["raw"]
        records = self.prov["records"]
        self.assertEqual(len(rows), len(records))
        self.assertEqual(self.prov["provenance_identity"], provenance_identity(records))

    def test_f_exact_artifact_coverage(self):
        ok, reason = validate_row_provenance(
            self.cache["raw"], self.prov["records"], expected_venue="DELTA",
            expected_source="Delta /v2/history/candles",
            expected_method="HistoricalLoader.candles_paginated",
            expected_symbol="BTCUSDT", expected_timeframe="1m")
        self.assertTrue(ok, reason)

    def test_g_raw_candles_unchanged_by_sidecar(self):
        self.assertEqual(set(self.cache["raw"][0].keys()),
                         {"time", "open", "high", "low", "close", "volume"})


if __name__ == "__main__":
    unittest.main()
