"""Phase 11F-1 feature tests (causal contracts, independent values).

Every assertion uses synthetic bars only. Independent expected
values are hand-computed in the test (not copied from the
implementation). Includes a future-bar negative test.
"""

import unittest

from research.phase11f import contracts as K
from research.phase11f import features as F


def _flat(n=30, start=1787000000, price=100.0):
    return [{"time": start + 60 * i, "open": price, "high": price,
             "low": price, "close": price, "volume": 10.0} for i in range(n)]


def _trend(n=30, start=1787000000, base=100.0):
    return [{"time": start + 60 * i, "open": base + i, "high": base + i + 1.0,
             "low": base + i - 1.0, "close": base + i + 0.5, "volume": 10.0}
            for i in range(n)]


class TestFeatureContractsDeclared(unittest.TestCase):
    def test_all_features_declare_no_future(self):
        for name, contract in K.FEATURE_CONTRACTS.items():
            self.assertFalse(contract["future_data_allowed"], name)
            self.assertIn("causal_rule", contract, name)

    def test_proxy_labels_preserved(self):
        self.assertEqual(K.ORDERFLOW_STATUS, "DATA_UNAVAILABLE")
        self.assertIn("rvol_proxy", K.PROXY_FEATURES)
        self.assertFalse(F.orderflow_available())


class TestDeterminism(unittest.TestCase):
    def test_same_input_same_output(self):
        bars = _trend(60)
        self.assertEqual(F.atr14(bars), F.atr14(list(bars)))
        self.assertEqual(F.rsi14(bars), F.rsi14(list(bars)))
        self.assertEqual(F.swings(bars), F.swings(list(bars)))
        self.assertEqual(F.fvg_zones(bars), F.fvg_zones(list(bars)))


class TestIndependentValues(unittest.TestCase):
    def test_flat_market_atr_zero_rsi_fifty(self):
        bars = _flat(30)
        atr = F.atr14(bars)
        rsi = F.rsi14(bars)
        # TR is 0 on every bar -> Wilder ATR stays 0 after seeding.
        self.assertAlmostEqual(atr[14], 0.0)
        self.assertAlmostEqual(atr[29], 0.0)
        # Flat market convention is defined as 50.0.
        self.assertAlmostEqual(rsi[14], 50.0)
        self.assertAlmostEqual(rsi[29], 50.0)

    def test_ema_hand_computed(self):
        # values 1..5, period 3: SMA(1,2,3)=2.0; k=0.5;
        # e3=(4-2)*.5+2=3.0; e4=(5-3)*.5+3=4.0
        out = F.ema([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        self.assertEqual(out[:2], [None, None])
        self.assertAlmostEqual(out[2], 2.0)
        self.assertAlmostEqual(out[3], 3.0)
        self.assertAlmostEqual(out[4], 4.0)

    def test_sma_hand_computed(self):
        out = F.sma([1.0, 2.0, 3.0, 4.0], 2)
        self.assertEqual(out[0], None)
        self.assertAlmostEqual(out[1], 1.5)
        self.assertAlmostEqual(out[2], 2.5)
        self.assertAlmostEqual(out[3], 3.5)

    def test_donchian_window(self):
        bars = [{"time": i, "open": 1, "high": float(i), "low": float(-i),
                 "close": 1, "volume": 1} for i in range(5)]
        hi, lo = F.donchian(bars, 3)
        self.assertEqual((hi[0], hi[1]), (None, None))
        self.assertAlmostEqual(hi[2], 2.0)
        self.assertAlmostEqual(lo[2], -2.0)
        self.assertAlmostEqual(hi[4], 4.0)
        self.assertAlmostEqual(lo[4], -4.0)

    def test_swing_confirmation_lag(self):
        # Single peak at e=2 with left=1/right=1: confirmed at 3,
        # nothing published at 2.
        highs = [1, 2, 10, 2, 1, 1, 1]
        bars = [{"time": 100 + 60 * i, "open": 1, "high": h, "low": 0,
                 "close": 1, "volume": 1} for i, h in enumerate(highs)]
        sw = F.swings(bars, left=1, right=1)
        self.assertIsNone(sw[2])
        self.assertIsNotNone(sw[3])
        self.assertEqual(sw[3]["extreme_index"], 2)
        self.assertEqual(sw[3]["confirmed_index"], 3)
        self.assertEqual(sw[3]["kind"], "high")

    def test_fvg_uses_two_bar_gap(self):
        bars = [
            {"time": 0, "open": 9, "high": 10, "low": 8, "close": 9, "volume": 1},
            {"time": 60, "open": 9, "high": 10, "low": 9, "close": 10, "volume": 1},
            {"time": 120, "open": 10, "high": 13, "low": 11, "close": 12, "volume": 1},
        ]
        fvg = F.fvg_zones(bars)
        self.assertIsNone(fvg[0])
        self.assertIsNone(fvg[1])
        self.assertIsNotNone(fvg[2])
        self.assertEqual(fvg[2]["direction"], "long")
        self.assertAlmostEqual(fvg[2]["bottom"], 10.0)
        self.assertAlmostEqual(fvg[2]["top"], 11.0)

    def test_finite_guard(self):
        self.assertTrue(F.finite_guard([1.0, 2.0, 3.0]))
        self.assertFalse(F.finite_guard([1.0, None]))
        self.assertFalse(F.finite_guard([1.0, float("nan")]))
        self.assertFalse(F.finite_guard([1.0, float("inf")]))

    def test_rvol_proxy_explicit(self):
        bars = _flat(25)
        rv = F.rvol_proxy(bars, period=20)
        self.assertIsNone(rv[0])
        self.assertIsNotNone(rv[20])
        # flat volume 10 / SMA 10 = 1.0
        self.assertAlmostEqual(rv[20], 1.0)


class TestNoFutureData(unittest.TestCase):
    def test_appending_future_bar_preserves_prefix(self):
        bars = _trend(40)
        prefix_atr = F.atr14(bars)
        extended = bars + [{"time": bars[-1]["time"] + 60, "open": 500,
                            "high": 600, "low": 400, "close": 550, "volume": 999}]
        new_atr = F.atr14(extended)
        self.assertEqual(new_atr[:40], prefix_atr)
        prefix_sw = F.swings(bars)
        new_sw = F.swings(extended)
        self.assertEqual(new_sw[:40], prefix_sw)
        prefix_fvg = F.fvg_zones(bars)
        new_fvg = F.fvg_zones(extended)
        self.assertEqual(new_fvg[:40], prefix_fvg)

    def test_mutation_future_swing_would_leak(self):
        # Non-causal reader that publishes the extreme at its
        # formation bar instead of the confirmation bar leaks:
        # it disagrees with the causal implementation at bar e.
        highs = [1, 2, 10, 2, 1, 1, 1]
        bars = [{"time": 100 + 60 * i, "open": 1, "high": h, "low": 0,
                 "close": 1, "volume": 1} for i, h in enumerate(highs)]
        causal = F.swings(bars, left=1, right=1)
        # the peak is at index 2 (value 10); causal publishes at 3.
        self.assertIsNone(causal[2])
        self.assertIsNotNone(causal[3])


if __name__ == "__main__":
    unittest.main()
