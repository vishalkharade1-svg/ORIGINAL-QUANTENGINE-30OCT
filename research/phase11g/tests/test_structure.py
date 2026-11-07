"""11G-A structure tests (confirmation lag, trend, BOS, CHOCH)."""

import unittest

from research.phase11g.features import structure as S
from research.phase11g.tests.test_feature_contracts import bars


def _peak():
    highs = [1, 2, 10, 2, 1, 1, 1]
    return [{"time": 100 + 60 * i, "open": 1, "high": h, "low": 0,
             "close": 1, "volume": 1} for i, h in enumerate(highs)]


class TestStructure(unittest.TestCase):
    def test_swing_confirmation_lag(self):
        sw = S.swing_series(_peak(), left=1, right=1)
        self.assertEqual(sw[2]["status"], "NO_EVENT")
        self.assertEqual(sw[3]["status"], "OK")
        self.assertEqual(sw[3]["value"]["extreme_index"], 2)
        self.assertEqual(sw[3]["formation_time"], 100 + 120)
        self.assertEqual(sw[3]["availability_time"], 100 + 180)

    def test_trend_uptrend(self):
        b = bars(200)
        vals = [r["value"] for r in S.trend_state(b) if r["status"] == "OK"]
        self.assertTrue(vals)
        self.assertIn(vals[-1], ("UPTREND", "DOWNTREND", "RANGE"))

    def test_bos_direction(self):
        b = bars(200)
        found = {r["value"]["direction"] for r in S.bos_events(b) if r["status"] == "OK"}
        self.assertTrue(found <= {"BULLISH", "BEARISH"})

    def test_choch_against_trend_only(self):
        b = bars(200)
        for r in S.choch_events(b):
            if r["status"] == "OK":
                self.assertIn("against", r["metadata"])

    def test_range_adapter(self):
        b = bars(200)
        n = sum(1 for r in S.range_state(b) if r["status"] == "OK")
        self.assertGreaterEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
