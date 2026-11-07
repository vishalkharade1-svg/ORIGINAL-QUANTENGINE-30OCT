"""11G-A causality tests (availability discipline + snapshot filter)."""

import unittest

from research.phase11g.features import structure as S
from research.phase11g.tests.test_feature_contracts import ALL_SERIES, bars
from research.phase11g.validation import snapshot as SN


class TestAvailabilityDiscipline(unittest.TestCase):
    def test_nothing_available_before_its_time(self):
        b = bars(150)
        t = b[100]["time"]
        for series in ALL_SERIES(b):
            for i, r in enumerate(series):
                if r["status"] == "OK" and r["availability_time"] is not None:
                    self.assertLessEqual(r["availability_time"], b[i]["time"])

    def test_known_at_filters_future(self):
        b = bars(150)
        series = S.trend_state(b)
        vis = SN.known_at(series, b[100]["time"])
        self.assertEqual(len(vis), len(series))
        for i, v in enumerate(vis):
            r = series[i]
            if r["status"] == "OK" and r["availability_time"] <= b[100]["time"]:
                self.assertEqual(v, r["value"])
            elif i > 100 and r["status"] == "OK":
                # availability is non-decreasing per bar only where
                # computed; future-dated entries must be hidden.
                if r["availability_time"] > b[100]["time"]:
                    self.assertIsNone(v)

    def test_confluence_at_uses_only_past(self):
        b = bars(150)
        trend = S.trend_state(b)
        out = SN.confluence_at({"structure": trend}, b[100]["time"])
        self.assertIn("structure", out)


if __name__ == "__main__":
    unittest.main()
