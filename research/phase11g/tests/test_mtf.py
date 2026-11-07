"""11G-A multi-timeframe tests (closed-candle discipline, mandatory)."""

import unittest

from research.phase11g.features import mtf as T
from research.phase11g.tests.test_feature_contracts import bars


def _aligned(n=120, start=1787000400):
    # start on a 15m boundary for exact bucketing.
    out = []
    for i in range(n):
        out.append({"time": start + 60 * i, "open": 100.0, "high": 101.0,
                    "low": 99.0, "close": 100.5, "volume": 10.0})
    return out


class TestMTF(unittest.TestCase):
    def test_bucketing_exact(self):
        h = T.resample_15m(_aligned(30))
        self.assertEqual(len(h), 1)  # 30 bars = 2 buckets, terminal excluded
        self.assertEqual(h[0]["time"], 1787000400)
        self.assertEqual(h[0]["availability_time"], 1787000400 + 900)
        self.assertEqual(h[0]["n_source_bars"], 15)
        self.assertTrue(h[0]["closed"])

    def test_not_available_before_close(self):
        b = _aligned(20)
        h = T.resample_15m(b)
        # First bucket closes at start+900; a 1m decision 5 min before
        # the close must not see it.
        early = b[10]["time"]
        self.assertLess(early, h[0]["availability_time"])
        states = T.htf_context(h)
        mapped = T.map_to_ltf(b, h, states)
        self.assertEqual(mapped[10]["status"], "NO_EVENT")

    def test_high_low_cannot_leak(self):
        b = _aligned(45)
        b[20] = dict(b[20], high=500.0)
        b[40] = dict(b[40], low=1.0)
        h_clean = T.resample_15m(_aligned(45))
        h_mut = T.resample_15m(b)
        # Mutations inside bucket 1 (bars 15-29) must not alter the
        # already-closed bucket 0.
        self.assertEqual(h_mut[0]["high"], h_clean[0]["high"])
        self.assertEqual(h_mut[0]["low"], h_clean[0]["low"])

    def test_future_1m_invariance(self):
        b = _aligned(60)
        ref = {c["time"]: c for c in T.resample_15m(b)}
        wild = b + [{"time": b[-1]["time"] + 60, "open": 1, "high": 9999,
                     "low": 1, "close": 5000, "volume": 99999.0}]
        got = {c["time"]: c for c in T.resample_15m(wild)}
        # Every bucket closed before the appended bar is byte-identical;
        # the appended bar may legitimately complete one new bucket.
        for t, c in ref.items():
            self.assertIn(t, got)
            for k in ("open", "high", "low", "close", "volume",
                      "n_source_bars", "availability_time"):
                self.assertEqual(got[t][k], c[k], (t, k))
        self.assertLessEqual(len(got) - len(ref), 1)

    def test_deterministic_and_ordered(self):
        b = _aligned(90)
        first = T.resample_15m(b)
        second = T.resample_15m(list(b))
        self.assertEqual(first, second)
        times = [c["time"] for c in first]
        self.assertEqual(times, sorted(times))

    def test_gaps_deterministic(self):
        b = _aligned(45)
        gapped = b[:20] + b[25:]
        h = T.resample_15m(gapped)
        h2 = T.resample_15m(list(gapped))
        self.assertEqual(h, h2)
        self.assertTrue(all(c["closed"] for c in h))

    def test_terminal_excluded(self):
        b = _aligned(16)
        h = T.resample_15m(b)
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["n_source_bars"], 15)

    def test_hostile_future_htf(self):
        b = _aligned(90)
        h = T.resample_15m(b)
        states = T.htf_context(h)
        mapped = T.map_to_ltf(b, h, states)
        # Decision at bar 20 can only see HTF candles closed by then.
        for i in (5, 20):
            r = mapped[i]
            if r["status"] == "OK":
                self.assertLessEqual(r["metadata"]["htf_availability"],
                                     b[i]["time"])

    def test_htf_context_needs_history(self):
        b = _aligned(60)
        h = T.resample_15m(b)
        states = T.htf_context(h)
        self.assertTrue(all(s["status"] != "OK" for s in states))


if __name__ == "__main__":
    unittest.main()
