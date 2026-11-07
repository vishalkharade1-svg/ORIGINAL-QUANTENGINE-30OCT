"""11G-J feature tests on golden fixtures (hand-computed expectations)."""

import unittest

from research.phase11g_j.replay import engine as ENG
from research.phase11g_j.tests import fixtures as FX

REV = ENG.TradeReplay(FX.GOLDEN)


class TestDelta(unittest.TestCase):
    def test_window_values(self):
        d = REV.delta(FX.T0 + 3, window="prefix")
        self.assertAlmostEqual(d["buy_volume"], FX.GOLDEN_BUY)
        self.assertAlmostEqual(d["sell_volume"], FX.GOLDEN_SELL)
        self.assertAlmostEqual(d["delta"], FX.GOLDEN_DELTA)
        self.assertAlmostEqual(d["total_volume"], FX.GOLDEN_TOTAL)
        self.assertAlmostEqual(d["delta_pct"], FX.GOLDEN_DELTA / FX.GOLDEN_TOTAL)

    def test_empty_window(self):
        d = REV.delta(FX.T0 - 1, window="1m")
        self.assertEqual(d["total_volume"], 0.0)
        self.assertEqual(d["delta"], 0.0)

    def test_bad_window_rejected(self):
        with self.assertRaises(ValueError):
            REV.delta(FX.T0, window="1h")


class TestCVD(unittest.TestCase):
    def test_series(self):
        series = REV.cvd()
        self.assertEqual([v for _, v in series], [1.0, 3.0, 1.5, 2.0, -1.0])
        self.assertEqual(series[-1][1], FX.GOLDEN_DELTA)

    def test_matches_one_pass(self):
        from research.phase11g_j.replay.engine import cvd_series
        self.assertEqual(REV.cvd(), cvd_series(FX.GOLDEN))

    def test_end_bound(self):
        self.assertEqual(REV.cvd(end_ms=FX.T0 + 1)[-1][1], 1.5)


class TestFootprint(unittest.TestCase):
    def test_levels(self):
        fp = REV.footprint(FX.T0, FX.T0 + 10)
        lv = fp["levels"]
        self.assertAlmostEqual(lv[100.0]["buy"], 1.5)
        self.assertAlmostEqual(lv[100.0]["sell"], 0.0)
        self.assertAlmostEqual(lv[100.01]["buy"], 2.0)
        self.assertAlmostEqual(lv[100.02]["sell"], 1.5)
        self.assertAlmostEqual(lv[99.99]["sell"], 3.0)
        self.assertEqual(fp["n_trades"], 5)

    def test_empty_bucket(self):
        fp = REV.footprint(FX.T0 + 100, FX.T0 + 200)
        self.assertEqual(fp["levels"], {})
        self.assertEqual(fp["n_trades"], 0)


class TestImbalance(unittest.TestCase):
    def test_trade_imbalance(self):
        imb = REV.imbalance(FX.T0 + 3, window="prefix")
        self.assertAlmostEqual(imb["trade_imbalance"],
                               FX.GOLDEN_DELTA / FX.GOLDEN_TOTAL)
        self.assertNotIn("book", str(imb).lower().replace("trade_imbalance", ""))


class TestAbsorptionAggression(unittest.TestCase):
    def test_absorption_shape(self):
        out = REV.absorption(FX.T0 + 3, window="1m")
        self.assertIn(out["classification"], ("DERIVED_FROM_REAL",))
        self.assertIn("present", out)
        self.assertIn("resting-order proof", out["note"])

    def test_aggression_shape(self):
        out = REV.aggression_event(FX.T0 + 3, window="1m")
        self.assertIn(out["classification"], ("DERIVED_FROM_REAL",))
        self.assertNotIn("sweep", str(out).lower().replace("liquidity", ""))


if __name__ == "__main__":
    unittest.main()
