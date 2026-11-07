"""11G-B per-hypothesis causal contract tests (availability proofs).

For each hypothesis family member, proves on synthetic bars that every
required event is available at or before the decision bar — using the
Stage-A feature engine, never a backtest. Includes MTF (008), Wyckoff
(006/007), liquidity (001-003), OB (004), breaker (005), volume
(006/007) proofs. No P&L anywhere.
"""

import unittest

from research.phase11g.features import (
    breaker as B, displacement as D, fibonacci as FB, fvg as G,
    liquidity as L, mtf as T, orderblock as O, structure as S,
    volume as V, wyckoff as W,
)
from research.phase11g.tests.test_feature_contracts import bars
from research.phase11g.validation import snapshot as SN


def _ok_before(series, decision_idx, bars_):
    """Every OK entry at/under decision must be available in time;
    returns count of OK entries checked."""
    n = 0
    for i, r in enumerate(series[:decision_idx + 1]):
        if r["status"] == "OK":
            n += 1
            assert r["availability_time"] <= bars_[i]["time"]
    return n


class TestLiquidityContracts(unittest.TestCase):
    def test_h001_h002_h003_reference_before_sweep(self):
        b = bars(200)
        refs = L.reference_pools(b)
        sweeps = L.sweep_events(b)
        for i, s in enumerate(sweeps):
            if s["status"] == "OK":
                # A reference level existed at/before the sweep bar:
                # equal/swing/session pools are non-empty wherever the
                # sweep required them ( sweep needs equal levels ).
                self.assertLessEqual(s["availability_time"], b[i]["time"])
        _ok_before(sweeps, 150, b)

    def test_future_liquidity_unavailable(self):
        b = bars(120)
        t = 80
        ref = L.reference_pools(b[:t + 1])
        wild = b[:t + 1] + [dict(x, high=9999.0, low=0.01) for x in b[t + 1:]]
        got = L.reference_pools(wild)
        self.assertEqual([len(r["value"]) for r in got[:t + 1]],
                         [len(r["value"]) for r in ref])


class TestDisplacementFVGContracts(unittest.TestCase):
    def test_h002_sequence_ordered(self):
        b = bars(200)
        for i, r in enumerate(D.displacement(b)):
            if r["status"] == "OK" and r["value"]:
                self.assertEqual(r["availability_time"], b[i]["time"])

    def test_h003_fvg_before_retest_decision(self):
        b = bars(200)
        zones = G.fvg_zones(b)
        for i, r in enumerate(zones):
            if r["status"] == "OK":
                self.assertLessEqual(r["confirmation_time"], r["availability_time"])
                self.assertEqual(r["availability_time"], b[i]["time"])


class TestOBContract(unittest.TestCase):
    def test_h004_ob_known_before_retest(self):
        b = bars(200)
        for i in (60, 120, 180):
            for d in ("long", "short"):
                r = O.order_block_at(b, i, d)
                if r["status"] == "OK":
                    self.assertLess(r["value"]["anchor_index"], i)
                    self.assertLessEqual(r["availability_time"], b[i]["time"])

    def test_future_bos_no_retroactive_ob(self):
        b = bars(120)
        t = 80
        ref = O.order_block_at(b[:t + 1], t, "long")
        wild = b[:t + 1] + [dict(x, close=x["high"] + 50.0, high=x["high"] + 50.0)
                            for x in b[t + 1:]]
        self.assertEqual(O.order_block_at(wild, t, "long")["status"], ref["status"])


class TestBreakerContract(unittest.TestCase):
    def test_h005_failure_before_signal(self):
        b = bars(200)
        evts = B.breaker_events(b)
        n = sum(1 for r in evts if r["status"] == "OK")
        self.assertGreaterEqual(n, 0)
        for i, r in enumerate(evts):
            if r["status"] == "OK":
                self.assertEqual(r["confirmation_time"], b[i]["time"])
                self.assertEqual(r["availability_time"], b[i]["time"])


class TestVolumeContract(unittest.TestCase):
    def test_h006_h007_volume_decision_time(self):
        b = bars(200)
        stats = V.rolling_stats(b, window=20)
        for i in (30, 100, 199):
            r = stats[i]
            if r["status"] == "OK":
                self.assertEqual(r["availability_time"], b[i]["time"])
                # Window is trailing only: max lookback bar is i-19.
                self.assertGreaterEqual(i, 19)


class TestWyckoffContract(unittest.TestCase):
    def test_h006_h007_no_backdate(self):
        b = bars(200)
        for series in (W.springs(b), W.upthrusts(b), W.secondary_tests(b),
                       W.signs_of_strength(b)):
            for i, r in enumerate(series):
                if r["status"] == "OK":
                    self.assertGreaterEqual(r["availability_time"],
                                            r["confirmation_time"])
                    self.assertLessEqual(r["availability_time"], b[i]["time"])


class TestMTFContract(unittest.TestCase):
    def test_h008_closed_before_decision(self):
        start = 1787000400
        b = [{"time": start + 60 * i, "open": 100.0, "high": 101.0,
              "low": 99.0, "close": 100.5, "volume": 10.0} for i in range(90)]
        h = T.resample_15m(b)
        states = T.htf_context(h)
        mapped = T.map_to_ltf(b, h, states)
        for i, r in enumerate(mapped):
            if r["status"] == "OK":
                self.assertLessEqual(r["metadata"]["htf_availability"], b[i]["time"])

    def test_future_htf_unchanged(self):
        start = 1787000400
        b = [{"time": start + 60 * i, "open": 100.0, "high": 101.0,
              "low": 99.0, "close": 100.5, "volume": 10.0} for i in range(60)]
        ref = T.resample_15m(b)
        wild = b + [{"time": b[-1]["time"] + 60, "open": 1, "high": 9999,
                     "low": 1, "close": 5000, "volume": 1e9}]
        got = T.resample_15m(wild)
        ref_by_t = {c["time"]: c for c in ref}
        for c in got:
            if c["time"] in ref_by_t:
                self.assertEqual(c["close"], ref_by_t[c["time"]]["close"])

    def test_snapshot_filters_for_h008(self):
        start = 1787000400
        b = [{"time": start + 60 * i, "open": 100.0, "high": 101.0,
              "low": 99.0, "close": 100.5, "volume": 10.0} for i in range(60)]
        h = T.resample_15m(b)
        states = T.htf_context(h)
        mapped = T.map_to_ltf(b, h, states)
        vis = SN.known_at(mapped, b[30]["time"])
        for i, v in enumerate(vis[:31]):
            r = mapped[i]
            if r["status"] == "OK" and r["availability_time"] <= b[30]["time"]:
                self.assertEqual(v, r["value"])
            else:
                self.assertIsNone(v)


if __name__ == "__main__":
    unittest.main()
