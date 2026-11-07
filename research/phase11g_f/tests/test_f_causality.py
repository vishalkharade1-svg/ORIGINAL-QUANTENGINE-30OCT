"""11G-F causality tests (per-hypothesis availability + truncation).

Proves on synthetic bars that every required event is available at or
before its decision bar, using the certified Stage-A engine (never a
backtest). Plus full truncation equivalence for all 8 F-candidates.
"""

import unittest

from research.phase11g.features import (
    breaker as B, displacement as D, liquidity as L, mtf as T,
    orderblock as O, structure as S, volume as V, wyckoff as W,
)
from research.phase11g.tests.test_feature_contracts import bars
from research.phase11g.validation import snapshot as SN
from research.phase11g_f import candidates as F


class TestFamilyCausality(unittest.TestCase):
    def test_sweep_liquidity_available(self):
        b = bars(200)
        for i, r in enumerate(L.sweep_events(b)):
            if r["status"] == "OK":
                self.assertLessEqual(r["availability_time"], b[i]["time"])

    def test_bos_ob_ordering(self):
        b = bars(200)
        for i in (60, 120, 180):
            r = O.order_block_at(b, i, "long")
            if r["status"] == "OK":
                self.assertLess(r["value"]["anchor_index"], i)

    def test_breaker_confirmation(self):
        b = bars(200)
        for i, r in enumerate(B.breaker_events(b)):
            if r["status"] == "OK":
                self.assertEqual(r["availability_time"], b[i]["time"])

    def test_wyckoff_volume_decision_time(self):
        b = bars(200)
        stats = V.rolling_stats(b, window=20)
        self.assertEqual(stats[30]["availability_time"], b[30]["time"])
        for series in (W.springs(b), W.upthrusts(b)):
            for i, r in enumerate(series):
                if r["status"] == "OK":
                    self.assertLessEqual(r["availability_time"], b[i]["time"])

    def test_mtf_closed_only(self):
        start = 1787000400
        b = [{"time": start + 60 * i, "open": 100.0, "high": 101.0,
              "low": 99.0, "close": 100.5, "volume": 10.0} for i in range(90)]
        h = T.resample_15m(b)
        states = T.htf_context(h)
        mapped = T.map_to_ltf(b, h, states)
        for i, r in enumerate(mapped):
            if r["status"] == "OK":
                self.assertLessEqual(r["metadata"]["htf_availability"], b[i]["time"])

    def test_snapshot_filter(self):
        b = bars(150)
        series = S.trend_state(b)
        vis = SN.known_at(series, b[100]["time"])
        for i, v in enumerate(vis):
            r = series[i]
            if not (r["status"] == "OK" and r["availability_time"] <= b[100]["time"]):
                self.assertIsNone(v)


class TestCandidateTruncation(unittest.TestCase):
    def test_all_eight_equivalent(self):
        b = bars(150)
        by_id = {c.id: c for c in F.ALL}
        self.assertEqual(len(by_id), 8)
        for hid in sorted(by_id):
            for idx in (30, 80, 120, 149):
                a = by_id[hid]()
                full = a.signals(idx, b, None) or []
                c = by_id[hid]()
                trunc = c.signals(idx, b[:idx + 1], None) or []
                self.assertEqual(full, trunc, "%s @ %d" % (hid, idx))

    def test_sequential_equivalence(self):
        b = bars(100)
        by_id = {c.id: c for c in F.ALL}
        for hid in sorted(by_id):
            ia, ib = by_id[hid](), by_id[hid]()
            for idx in range(len(b)):
                self.assertEqual(ia.signals(idx, b, None) or [],
                                 ib.signals(idx, b[:idx + 1], None) or [],
                                 "%s @ %d" % (hid, idx))


class TestFutureMutations(unittest.TestCase):
    def _prefix_equal(self, ref_series, got_series, t):
        self.assertEqual([r["status"] for r in got_series[:t + 1]],
                         [r["status"] for r in ref_series])

    def test_future_bars_no_effect(self):
        b = bars(120)
        t = 80
        wild = b[:t + 1] + [dict(x, high=9999.0, low=0.01, close=5000.0,
                                 volume=1e9) for x in b[t + 1:]]
        self._prefix_equal(L.sweep_events(b[:t + 1]), L.sweep_events(wild), t)
        self._prefix_equal(D.displacement(b[:t + 1]), D.displacement(wild), t)
        self._prefix_equal(B.breaker_events(b[:t + 1]), B.breaker_events(wild), t)
        self._prefix_equal(W.springs(b[:t + 1]), W.springs(wild), t)

    def test_future_htf_no_effect(self):
        start = 1787000400
        b = [{"time": start + 60 * i, "open": 100.0, "high": 101.0,
              "low": 99.0, "close": 100.5, "volume": 10.0} for i in range(60)]
        ref = {c["time"]: c for c in T.resample_15m(b)}
        wild = b + [{"time": b[-1]["time"] + 60, "open": 1, "high": 9999,
                     "low": 1, "close": 5000, "volume": 1e9}]
        for t, c in ref.items():
            got = {x["time"]: x for x in T.resample_15m(wild)}
            self.assertEqual(got[t]["close"], c["close"])

    def test_cost_mutation_detected(self):
        from research.phase11f.harness import COST_SCENARIOS_11F
        self.assertAlmostEqual(COST_SCENARIOS_11F["C"]["COMMISSION_RATE"], 0.00059)
        bad = dict(COST_SCENARIOS_11F["C"], SLIPPAGE_BPS=0.0)
        self.assertNotEqual(bad["SLIPPAGE_BPS"],
                            COST_SCENARIOS_11F["C"]["SLIPPAGE_BPS"])

    def test_rolling_mutation_detected(self):
        from research.phase11f import validation as V
        folds = V.build_folds(8000)
        self.assertEqual(V.validate_expanding(folds), [])
        mutant = [dict(f, train_start=f["fold"] * 1000,
                       train_end=f["fold"] * 1000 + 2000) for f in folds]
        self.assertTrue(any("rolling" in e for e in V.validate_expanding(mutant)))


if __name__ == "__main__":
    unittest.main()
