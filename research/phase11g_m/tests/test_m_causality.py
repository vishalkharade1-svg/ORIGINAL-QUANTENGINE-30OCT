"""11G-M causality: feature-level lookahead attacks (MUT-M1/M2), no economics.

Synthetic trades only (in-test fixtures, never a dataset). Appending a
trade strictly AFTER a decision boundary must leave every earlier
feature value identical; flipping aggressor sides must move delta
(positive control that features actually read trades).
"""

import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11g_j.replay.events import RealTrade  # noqa: E402
from research.phase11g_l.runner.context import MarketContext  # noqa: E402


def _trades():
    out = []
    idx = 0
    for minute in range(3):
        base_ms = 1_000_000 + minute * 60_000
        for k in range(10):
            side = "buy" if k < 7 else "sell"  # asymmetric: delta != 0
            out.append(RealTrade(
                event_ms=base_ms + k * 1000, transact_raw=base_ms + k * 1000,
                source_index=idx, symbol="TST", venue="test",
                price=100.0 + minute + k * 0.01, quantity=1.0,
                aggressor_side=side, trade_id="t%d" % idx,
                first_trade_id="t%d" % idx, last_trade_id="t%d" % idx))
            idx += 1
    return out


def _bars():
    return [{"time": (1_000_000 // 60_000) * 60 + m * 60,
             "open": 100.0 + m, "high": 100.0 + m + 0.1,
             "low": 100.0 + m - 0.1, "close": 100.0 + m + 0.05,
             "volume": 10.0} for m in range(3)]


class TestCausalityAttacks(unittest.TestCase):
    def test_mut_m1_future_trade_leak(self):
        bars, ts = _bars(), _trades()
        ref = MarketContext(bars, ts)
        future = RealTrade(
            event_ms=1_000_000 + 2 * 60_000 + 59_000,
            transact_raw=1_000_000 + 2 * 60_000 + 59_000,
            source_index=999, symbol="TST", venue="test",
            price=500.0, quantity=1000.0, aggressor_side="buy",
            trade_id="future", first_trade_id="future",
            last_trade_id="future")
        mut = MarketContext(bars, ts + [future])
        for i in (0, 1):
            self.assertEqual(ref.window_vol(i, 5), mut.window_vol(i, 5))
            self.assertEqual(ref.cvd[i], mut.cvd[i])
            self.assertEqual(ref.min_total[i], mut.min_total[i])

    def test_mut_m2_future_cvd_leak(self):
        bars, ts = _bars(), _trades()
        ref = MarketContext(bars, ts)
        future = RealTrade(
            event_ms=1_000_000 + 2 * 60_000 + 59_000,
            transact_raw=1_000_000 + 2 * 60_000 + 59_000,
            source_index=999, symbol="TST", venue="test",
            price=500.0, quantity=1000.0, aggressor_side="sell",
            trade_id="future", first_trade_id="future",
            last_trade_id="future")
        mut = MarketContext(bars, ts + [future])
        for i in (0, 1):
            self.assertEqual(ref.cvd_slope(i, 60), mut.cvd_slope(i, 60))

    def test_aggressor_sensitivity_positive_control(self):
        bars, ts = _bars(), _trades()
        ref = MarketContext(bars, ts)
        import dataclasses
        flip = [dataclasses.replace(
            t, aggressor_side=("sell" if t.aggressor_side == "buy" else "buy"))
            for t in ts]
        mut = MarketContext(bars, flip)
        rb = ref.window_vol(2, 5)
        mb = mut.window_vol(2, 5)
        self.assertAlmostEqual(rb[3], -mb[3])
        self.assertNotEqual(rb[3], 0.0)


if __name__ == "__main__":
    unittest.main()
