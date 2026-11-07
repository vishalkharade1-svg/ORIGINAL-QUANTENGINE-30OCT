"""11G-A Fibonacci adapter tests (frozen ratios, causal anchors)."""

import unittest

from research.phase11g.features import fibonacci as FB
from research.phase11g.tests.test_feature_contracts import bars


def _valley_peak():
    lows = [100, 100, 90, 100, 100, 100, 100, 100, 100, 100]
    highs = [100, 100, 100, 100, 100, 105, 120, 105, 100, 100]
    return [{"time": 1000 + 60 * i, "open": 100, "high": highs[i],
             "low": lows[i], "close": 100, "volume": 10.0} for i in range(10)]


class TestFibonacci(unittest.TestCase):
    def test_no_levels_before_confirmation(self):
        retr = FB.retracements(_valley_peak(), left=1, right=1)
        for i in range(7):
            self.assertEqual(retr[i]["status"], "NO_EVENT")
        self.assertEqual(retr[7]["status"], "OK")

    def test_anchor_timestamps(self):
        retr = FB.retracements(_valley_peak(), left=1, right=1)
        r = retr[7]
        self.assertLessEqual(r["formation_time"], r["confirmation_time"])
        self.assertEqual(r["availability_time"], r["confirmation_time"])

    def test_ratios_frozen(self):
        from research.phase11f.fibonacci import FIB_RETRACE_RATIOS, FIB_EXTENSION_RATIOS
        self.assertEqual(FIB_RETRACE_RATIOS, (0.382, 0.5, 0.618, 0.786))
        self.assertEqual(FIB_EXTENSION_RATIOS, (1.272, 1.618))

    def test_confluence_flag(self):
        b = bars(200)
        for i, r in enumerate(FB.confluence(b)):
            if r["status"] == "OK":
                self.assertIn("ratios", r["value"])
                self.assertEqual(r["availability_time"], b[i]["time"])


if __name__ == "__main__":
    unittest.main()
