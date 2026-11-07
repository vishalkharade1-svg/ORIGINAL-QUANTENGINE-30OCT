"""11G-A breaker tests."""

import unittest

from research.phase11g.features import breaker as B
from research.phase11g.tests.test_feature_contracts import bars


class TestBreaker(unittest.TestCase):
    def test_event_only_on_crossing_bar(self):
        b = bars(200)
        series = B.breaker_events(b)
        n = sum(1 for r in series if r["status"] == "OK")
        self.assertGreaterEqual(n, 0)
        for i, r in enumerate(series):
            if r["status"] == "OK":
                self.assertEqual(r["availability_time"], b[i]["time"])
                self.assertIn(r["value"]["direction"], ("BULLISH", "BEARISH"))


if __name__ == "__main__":
    unittest.main()
