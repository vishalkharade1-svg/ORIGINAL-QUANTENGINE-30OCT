"""11G-A volume tests (trailing statistics, regime ranks)."""

import unittest

from research.phase11g.features import volume as V
from research.phase11g.tests.test_feature_contracts import bars


class TestVolume(unittest.TestCase):
    def test_rolling_stats_hand_computed(self):
        b = [{"time": i, "open": 1, "high": 1, "low": 1, "close": 1,
              "volume": float(i + 1)} for i in range(10)]
        stats = V.rolling_stats(b, window=4)
        self.assertEqual(stats[2]["status"], "INSUFFICIENT_HISTORY")
        s = stats[3]
        self.assertAlmostEqual(s["value"]["mean"], 2.5)
        self.assertAlmostEqual(s["value"]["median"], 2.5)
        self.assertAlmostEqual(s["value"]["rvol_mean"], 4.0 / 2.5)

    def test_regime_ranks(self):
        def _mk(last):
            vols = [10.0] * 10 + [1.0] * 9 + [last]
            return [{"time": i, "open": 1, "high": 1, "low": 1, "close": 1,
                     "volume": v} for i, v in enumerate(vols)]
        # rank 20/20 (spike) -> HIGH; rank 10/20 (middle) -> NORMAL;
        # rank 0/20 (driest) -> LOW.
        self.assertEqual(V.volume_regime(_mk(1000.0), window=20)[19]["value"], "HIGH")
        self.assertEqual(V.volume_regime(_mk(5.0), window=20)[19]["value"], "NORMAL")
        self.assertEqual(V.volume_regime(_mk(0.5), window=20)[19]["value"], "LOW")

    def test_expansion_flag(self):
        b = [{"time": i, "open": 1, "high": 1, "low": 1, "close": 1,
              "volume": 10.0} for i in range(40)]
        b[30] = dict(b[30], volume=50.0)
        exp = V.expansion(b, window=20, mult=2.0)
        self.assertTrue(exp[30]["value"] is True)
        self.assertTrue(exp[25]["value"] is False)
        self.assertEqual(exp[10]["status"], "INSUFFICIENT_HISTORY")

    def test_no_centered_window(self):
        b = bars(120)
        ref = V.rolling_stats(b, window=20)
        wild = [dict(x) for x in b] + [
            {"time": b[-1]["time"] + 60 * k, "open": 1, "high": 999,
             "low": 1, "close": 500, "volume": 99999.0} for k in range(10)]
        got = V.rolling_stats(wild, window=20)
        for i in range(len(b)):
            self.assertEqual(got[i]["value"], ref[i]["value"])

    def test_neutral_terminology(self):
        import json
        b = bars(60)
        blob = json.dumps([V.volume_regime(b), V.rolling_stats(b)],
                          default=str).lower()
        self.assertNotIn("institutional", blob)


if __name__ == "__main__":
    unittest.main()
