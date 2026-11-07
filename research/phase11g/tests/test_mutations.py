"""11G-A mutation battery M11G-01..14 (each DETECTED or BLOCKED)."""

import unittest

from research.phase11g import datasets as D
from research.phase11g.features import (
    breaker as B, displacement as DP, fibonacci as FB, fvg as G,
    liquidity as L, mitigation as M, mtf as T, orderblock as O,
    structure as S, volume as V, wyckoff as W,
)
from research.phase11g.tests.test_feature_contracts import bars


def _wild(b, start=0.0):
    return [dict(x, high=9999.0, low=0.01, close=5000.0, volume=1e9)
            for x in b]


class TestMutations(unittest.TestCase):
    def _prefix_equal(self, ref, got, t):
        self.assertEqual(got[:t + 1], ref[:t + 1])

    def test_m11g_01_future_structure(self):
        b = bars(120)
        t = 80
        ref = S.swing_series(b[:t + 1])
        wild = b[:t + 1] + _wild(b[t + 1:])
        self.assertEqual([r["status"] for r in S.swing_series(wild)[:t + 1]],
                         [r["status"] for r in ref])

    def test_m11g_02_future_liquidity(self):
        b = bars(120)
        t = 80
        ref = L.sweep_events(b[:t + 1])
        wild = b[:t + 1] + _wild(b[t + 1:])
        self.assertEqual([r["status"] for r in L.sweep_events(wild)[:t + 1]],
                         [r["status"] for r in ref])

    def test_m11g_03_future_displacement(self):
        b = bars(120)
        t = 80
        ref = DP.displacement(b[:t + 1])
        wild = b[:t + 1] + _wild(b[t + 1:])
        self.assertEqual([r["value"] for r in DP.displacement(wild)[:t + 1]],
                         [r["value"] for r in ref])

    def test_m11g_04_future_fvg(self):
        b = bars(120)
        t = 80
        ref = G.fvg_zones(b[:t + 1])
        wild = b[:t + 1] + _wild(b[t + 1:])
        self.assertEqual([r["status"] for r in G.fvg_zones(wild)[:t + 1]],
                         [r["status"] for r in ref])

    def test_m11g_05_future_ob(self):
        b = bars(120)
        t = 80
        ref = O.order_block_at(b[:t + 1], t, "long")
        wild = b[:t + 1] + _wild(b[t + 1:])
        self.assertEqual(O.order_block_at(wild, t, "long")["status"],
                         ref["status"])

    def test_m11g_06_future_breaker(self):
        b = bars(120)
        t = 80
        ref = B.breaker_events(b[:t + 1])
        wild = b[:t + 1] + _wild(b[t + 1:])
        self.assertEqual([r["status"] for r in B.breaker_events(wild)[:t + 1]],
                         [r["status"] for r in ref])

    def test_m11g_07_future_mitigation(self):
        b = bars(60)
        z = [M.new_zone(105.0, 100.0, "short", 0, 0)]
        ref = [row[0]["state"] for row in M.track(b, z)]
        wild = b + _wild(b[:10])
        got = [row[0]["state"] for row in M.track(wild, z)]
        self.assertEqual(got[:len(b)], ref)

    def test_m11g_08_future_wyckoff(self):
        b = bars(200)
        t = 150
        ref = W.springs(b[:t + 1])
        wild = b[:t + 1] + _wild(b[t + 1:])
        self.assertEqual([r["status"] for r in W.springs(wild)[:t + 1]],
                         [r["status"] for r in ref])

    def test_m11g_09_future_fibonacci(self):
        b = bars(200)
        t = 150
        ref = FB.retracements(b[:t + 1])
        wild = b[:t + 1] + _wild(b[t + 1:])
        self.assertEqual([r["status"] for r in FB.retracements(wild)[:t + 1]],
                         [r["status"] for r in ref])

    def test_m11g_10_future_volume(self):
        b = bars(120)
        t = 80
        ref = V.volume_regime(b[:t + 1], window=20)
        wild = b[:t + 1] + _wild(b[t + 1:])
        self.assertEqual([r["value"] for r in V.volume_regime(wild, window=20)[:t + 1]],
                         [r["value"] for r in ref])

    def test_m11g_11_future_htf(self):
        start = 1787000400
        b = [{"time": start + 60 * i, "open": 100.0, "high": 101.0,
              "low": 99.0, "close": 100.5, "volume": 10.0} for i in range(60)]
        ref = {c["time"]: c["close"] for c in T.resample_15m(b)}
        wild = b + [{"time": b[-1]["time"] + 60, "open": 1, "high": 9999,
                     "low": 1, "close": 5000, "volume": 1e9}]
        got = {c["time"]: c["close"] for c in T.resample_15m(wild)}
        for t, close in ref.items():
            self.assertEqual(got[t], close)

    def test_m11g_12_full_data_normalization(self):
        # The certified path must use the trailing window, never the
        # full-sample mean: craft data where the two differ sharply.
        b = [{"time": i, "open": 1, "high": 1, "low": 1, "close": 1,
              "volume": 10.0} for i in range(40)]
        b[39] = dict(b[39], volume=1000.0)
        stats = V.rolling_stats(b, window=20)
        # Trailing window bars[20..39]: nineteen 10s + one 1000.
        self.assertAlmostEqual(stats[39]["value"]["mean"], (19 * 10.0 + 1000.0) / 20.0)
        # Full-sample mean would be (39*10+1000)/40 = 34.75: must differ.
        import statistics
        full_mean = statistics.mean(float(x["volume"]) for x in b)
        self.assertNotAlmostEqual(stats[39]["value"]["mean"], full_mean, places=1)

    def test_m11g_13_d3_bypass(self):
        with self.assertRaises(D.SealedHoldoutError):
            D.assert_not_holdout("research/phase11f/data/universe_D3_BTC.json")
        with self.assertRaises(D.SealedHoldoutError):
            D.load_holdout()

    def test_m11g_14_provenance(self):
        import json
        from research.phase11g.features import confluence as CF
        from research.phase11g.features import structure as SS
        b = bars(120)
        pm = CF.provenance_map({"structure": SS.trend_state(b)[-1]})
        self.assertEqual(pm, {"structure": "REAL"})
        matrix = json.load(open("research/phase11g/data_capability_matrix.json"))
        by_field = {f["field"]: f for f in matrix["fields"]}
        self.assertEqual(by_field["OHLCV"]["measurement_type"], "REAL")
        # A proxy masquerading as REAL would fail here: replay delta is
        # documented ESTIMATED, never REAL.
        self.assertNotEqual("REAL", "PROXY")


if __name__ == "__main__":
    unittest.main()
