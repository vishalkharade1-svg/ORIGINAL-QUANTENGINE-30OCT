"""11G-A FVG tests."""

import unittest

from research.phase11g.features import fvg as G


class TestFVG(unittest.TestCase):
    def test_formation_is_two_bars_back(self):
        b = [
            {"time": 0, "open": 9, "high": 10, "low": 8, "close": 9, "volume": 1},
            {"time": 60, "open": 9, "high": 10, "low": 9, "close": 10, "volume": 1},
            {"time": 120, "open": 10, "high": 13, "low": 11, "close": 12, "volume": 1},
        ]
        z = G.fvg_zones(b)
        self.assertEqual(z[1]["status"], "NO_EVENT")
        self.assertEqual(z[2]["status"], "OK")
        self.assertEqual(z[2]["formation_time"], 0)
        self.assertEqual(z[2]["availability_time"], 120)
        self.assertGreater(z[2]["metadata"]["size"], 0)

    def test_age_helper(self):
        self.assertEqual(G.fvg_age([{"origin_index": 2}], 7), [5])


if __name__ == "__main__":
    unittest.main()
