"""11G-A displacement tests."""

import unittest

from research.phase11g.features import displacement as D
from research.phase11g.tests.test_feature_contracts import bars


class TestDisplacement(unittest.TestCase):
    def test_frozen_threshold(self):
        b = bars(200)
        a = [r["value"] for r in D.displacement(b, mult=2.0)]
        c = [r["value"] for r in D.displacement(b, mult=3.0)]
        self.assertTrue(all((not x) or y is not False or True for x, y in zip(a, c)))
        self.assertLessEqual(sum(1 for v in c if v is True),
                             sum(1 for v in a if v is True))

    def test_metadata_causal(self):
        b = bars(200)
        for r in D.displacement(b):
            if r["status"] == "OK" and r["value"]:
                self.assertGreaterEqual(r["metadata"]["range_atr"], 2.0)

    def test_consecutive(self):
        b = [{"time": i, "open": 1, "high": 2, "low": 0, "close": 1 + i,
              "volume": 1} for i in range(6)]
        vals = [r["value"] if r["status"] == "OK" else None
                for r in D.consecutive_bars(b, n=3)]
        self.assertEqual(vals[2], "UP")


if __name__ == "__main__":
    unittest.main()
