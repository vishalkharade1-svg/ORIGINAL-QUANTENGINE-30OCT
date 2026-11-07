"""11G-A prefix-invariance + incremental/batch parity tests."""

import unittest

from research.phase11g.features import mitigation as M
from research.phase11g.features import mtf as T
from research.phase11g.features import structure as S
from research.phase11g.tests.test_feature_contracts import ALL_SERIES, bars


class TestPrefixInvariance(unittest.TestCase):
    def test_prefix_equals_full_history(self):
        b = bars(200)
        for series, full in ((S.swing_series, S.swing_series(b)),
                             (S.trend_state, S.trend_state(b))):
            short = series(b[:120])
            for i in range(120):
                a, c = short[i], full[i]
                self.assertEqual(a["status"], c["status"])
                if a["status"] == "OK":
                    self.assertEqual(a["value"], c["value"])

    def test_mtf_prefix_stable(self):
        b = bars(200)
        full = T.resample_15m(b)
        for p in (60, 120, 180):
            part = T.resample_15m(b[:p])
            # Closed buckets fully inside the prefix must match exactly.
            for c in part:
                if c["availability_time"] <= b[p - 1]["time"]:
                    match = [x for x in full if x["time"] == c["time"]]
                    self.assertEqual(len(match), 1)
                    self.assertEqual(match[0]["close"], c["close"])
                    self.assertEqual(match[0]["high"], c["high"])


class TestIncrementalBatchParity(unittest.TestCase):
    def test_mitigation_stepwise_equals_batch(self):
        # Incremental: track() over the growing prefix, keep each last
        # row. Batch: track() once over all bars. Pure left fold =>
        # identical.
        b = bars(80)
        z = [M.new_zone(108.0, 104.0, "short", 0, 0)]
        batch = M.track(b, [dict(x) for x in z])
        for i in range(len(b)):
            step = M.track(b[:i + 1], [M.new_zone(108.0, 104.0, "short", 0, 0)])
            self.assertEqual(step[-1][0], batch[i][0])

    def test_zone_state_dicts_deterministic(self):
        import json
        b = bars(80)
        z = [M.new_zone(108.0, 104.0, "short", 0, 0)]
        first = json.dumps(M.track(b, [dict(x) for x in z]), sort_keys=True)
        second = json.dumps(M.track(b, [dict(x) for x in z]), sort_keys=True)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
