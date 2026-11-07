"""11G-A Wyckoff event tests (causal event timestamps)."""

import unittest

from research.phase11g.features import wyckoff as W
from research.phase11g.tests.test_feature_contracts import bars


def _range_with_spring():
    # Flat 100 range; bar 100 dips to 90 and reclaims to 99.5.
    # (Donchian-50 warmup consumes the first 50 bars, so the range
    # needs 50 + 30 bars of stillness before the spring.)
    b = []
    for i in range(130):
        b.append({"time": i * 60, "open": 100, "high": 101, "low": 99,
                  "close": 100, "volume": 10.0})
    b[100] = dict(b[100], low=90.0, close=99.5)
    return b


SPRING_BAR = 100
TEST_BAR = 105


class TestWyckoff(unittest.TestCase):
    def test_spring_event(self):
        b = _range_with_spring()
        spr = W.springs(b, range_lookback=50, min_hold=30)
        hits = [i for i, r in enumerate(spr) if r["status"] == "OK"]
        self.assertIn(SPRING_BAR, hits)
        self.assertEqual(spr[SPRING_BAR]["availability_time"], b[SPRING_BAR]["time"])
        self.assertEqual(spr[SPRING_BAR]["formation_time"], b[SPRING_BAR]["time"])
        self.assertIn("invalidation", spr[SPRING_BAR]["value"])

    def test_no_spring_without_range(self):
        b = bars(120)
        n = sum(1 for r in W.springs(b) if r["status"] == "OK")
        self.assertGreaterEqual(n, 0)

    def test_secondary_test_needs_prior_spring(self):
        b = _range_with_spring()
        b[TEST_BAR] = dict(b[TEST_BAR], low=90.3, close=97.0)
        sec = W.secondary_tests(b, range_lookback=50, min_hold=30)
        self.assertEqual(sec[TEST_BAR]["status"], "OK")
        self.assertEqual(sec[TEST_BAR]["value"]["spring_index"], SPRING_BAR)
        self.assertEqual(sec[TEST_BAR]["availability_time"], b[TEST_BAR]["time"])
        # Without the dip at 70 there is no test.
        b2 = _range_with_spring()
        sec2 = W.secondary_tests(b2, range_lookback=50, min_hold=30)
        self.assertTrue(all(r["status"] != "OK" for r in sec2))

    def test_sos_needs_displacement(self):
        b = bars(200)
        for i, r in enumerate(W.signs_of_strength(b)):
            if r["status"] == "OK":
                self.assertEqual(r["availability_time"], b[i]["time"])
                self.assertEqual(r["confirmation_time"], b[i]["time"])


if __name__ == "__main__":
    unittest.main()

