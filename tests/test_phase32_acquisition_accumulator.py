"""Phase 32 deterministic acquisition accumulator tests."""
from __future__ import annotations

import json
import unittest

from core.research.acquisition.accumulator import (
    AccumulationError,
    accumulate,
    batch_identity,
    validate_batch,
)

BOUNDARY = 1788601440
META = dict(
    boundary=BOUNDARY,
    expected_venue="DELTA",
    expected_source="Delta /v2/history/candles",
    expected_method="HistoricalLoader.candles_paginated",
    expected_symbol="BTCUSDT",
    expected_timeframe="1m",
)


def rows(start, count, close=100.5):
    return [{"time": start + i * 60, "open": 100.0, "high": 101.0,
             "low": 99.0, "close": close, "volume": 2.5}
            for i in range(count)]


def prov(rs):
    return [{"time": r["time"], "venue": "DELTA",
             "acquisition_source": "Delta /v2/history/candles",
             "acquisition_method": "HistoricalLoader.candles_paginated",
             "symbol": "BTCUSDT", "timeframe": "1m"} for r in rs]


class TestPhase32Accumulator(unittest.TestCase):
    def test_batch_identity_is_order_independent(self):
        a = rows(BOUNDARY + 60, 4)
        self.assertEqual(batch_identity(a), batch_identity(list(reversed(a))))

    def test_pre_boundary_fails_closed(self):
        bad = rows(BOUNDARY, 1)
        with self.assertRaisesRegex(AccumulationError, "PRE_BOUNDARY_ROW"):
            validate_batch(bad, prov(bad), **META)

    def test_missing_provenance_fails_closed(self):
        rs = rows(BOUNDARY + 60, 3)
        with self.assertRaisesRegex(AccumulationError,
                                   "PROVENANCE_COVERAGE_MISMATCH"):
            validate_batch(rs, prov(rs[:-1]), **META)

    def test_identical_overlap_is_deduplicated(self):
        old = rows(BOUNDARY + 60, 3)
        new = rows(BOUNDARY + 120, 3)
        out = accumulate(old, new, prov(old), prov(new), **META)
        self.assertEqual(out["added_rows"], 1)
        self.assertEqual(out["identical_duplicates"], 2)
        self.assertEqual(out["total_rows"], 4)

    def test_conflicting_overlap_fails_closed(self):
        old = rows(BOUNDARY + 60, 3)
        new = rows(BOUNDARY + 120, 3, close=999.0)
        with self.assertRaisesRegex(AccumulationError,
                                   "CONFLICTING_DUPLICATE_TIMESTAMP"):
            accumulate(old, new, prov(old), prov(new), **META)

    def test_future_mutation_changes_only_new_identity(self):
        base = rows(BOUNDARY + 60, 5)
        mutated = [dict(r) for r in base]
        mutated[-1]["close"] = 777.0
        self.assertEqual(batch_identity(base[:-1]),
                         batch_identity(mutated[:-1]))
        self.assertNotEqual(batch_identity(base), batch_identity(mutated))

    def test_output_is_byte_stable(self):
        old = rows(BOUNDARY + 60, 2)
        new = rows(BOUNDARY + 180, 2)
        a = accumulate(old, new, prov(old), prov(new), **META)
        b = accumulate(old, new, prov(old), prov(new), **META)
        self.assertEqual(json.dumps(a, sort_keys=True, separators=(",", ":")),
                         json.dumps(b, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    unittest.main()
