"""
Phase 9Q-2 — ATR Wilder RMA correctness.

Tests required by prompt:
1. known TR sequence
2. known ATR sequence
3. seed correctness
4. incremental == batch
5. reset correctness
6. warmup behavior
7. repeated updates
8. no NaN corruption
9. realistic candle sequence
"""

import math
import unittest
from dataclasses import dataclass

from core.indicators.atr import ATR


@dataclass
class Bar:
    timestamp: int
    open: float
    high: float
    low: float
    close: float


def _bars_from_ohlc(ohlc_list, start_ts=1000, step=60):
    out = []
    for i, (o, h, l, c) in enumerate(ohlc_list):
        out.append(Bar(timestamp=start_ts + i * step, open=o, high=h, low=l, close=c))
    return out


class TestATRWilder(unittest.TestCase):

    def test_known_tr_sequence(self):
        # TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
        bars = _bars_from_ohlc([
            (10, 12, 9, 11),   # TR = 12-9=3
            (11, 13, 10, 12),  # TR = max(3, |13-11|=2, |10-11|=1)=3
            (12, 15, 11, 14),  # TR = max(4, |15-12|=3, |11-12|=1)=4
        ])
        atr = ATR(period=2)
        atr.calculate(bars)
        # trs = [3,3,4]
        self.assertEqual(atr._trs, [3, 3, 4])

    def test_seed_correctness(self):
        # period=3, TRs [2,4,6,8] → seed = (2+4+6)/3=4.0 at index 2
        bars = _bars_from_ohlc([
            (0, 2, 0, 1),   # TR 2
            (1, 5, 1, 3),   # TR max(4, |5-1|=4, |1-1|=0)=4
            (3, 9, 3, 4),   # TR max(6, |9-3|=6, |3-3|=0)=6
            (4, 12, 4, 5),  # TR max(8, |12-4|=8, |4-4|=0)=8
        ])
        atr = ATR(period=3)
        vals = atr.calculate(bars)
        self.assertIsNone(vals[0])
        self.assertIsNone(vals[1])
        self.assertAlmostEqual(vals[2], 4.0, places=6)
        # Wilder: ATR[3] = ((4*(2)) + 8)/3 = 16/3 ≈5.333333
        self.assertAlmostEqual(vals[3], 16/3, places=6)

    def test_known_atr_sequence(self):
        # Hand-computed Wilder sequence for period=3
        # TRs: [3,3,4,5] → seed (3+3+4)/3=3.333..., ATR3 = ((3.333*2)+5)/3=3.888...
        bars = _bars_from_ohlc([
            (0, 3, 0, 2),   # TR 3
            (2, 5, 2, 3),   # TR max(3, |5-2|=3, |2-2|=0)=3
            (3, 7, 3, 4),   # TR max(4, |7-3|=4, |3-3|=0)=4
            (4, 9, 4, 5),   # TR max(5, |9-4|=5, |4-4|=0)=5
        ])
        atr = ATR(period=3)
        vals = atr.calculate(bars)
        self.assertAlmostEqual(vals[2], (3+3+4)/3, places=6)
        self.assertAlmostEqual(vals[3], (( (3+3+4)/3 *2 +5)/3), places=6)

    def test_incremental_equals_batch(self):
        ohlc = [(i, i+5, i, i+2) for i in range(20)]
        bars = _bars_from_ohlc(ohlc)
        # Batch
        atr_batch = ATR(period=5)
        batch_vals = atr_batch.calculate(bars)

        # Incremental: feed one by one via update
        atr_inc = ATR(period=5)
        inc_vals = None
        for i in range(len(bars)):
            window = bars[: i+1]
            if i == 0:
                inc_vals = atr_inc.calculate(window)
            else:
                inc_vals = atr_inc.update(window)

        self.assertEqual(len(batch_vals), len(inc_vals))
        for a, b in zip(batch_vals, inc_vals):
            if a is None and b is None:
                continue
            self.assertAlmostEqual(a, b, places=9)

    def test_incremental_sliding_window(self):
        # At deque cap, window slides (n == _n). Verify sliding does not crash
        # and maintains deterministic Wilder state (values match full-history batch sliced).
        ohlc = [(i, i+3, i-1, i+1) for i in range(30)]
        bars_all = _bars_from_ohlc(ohlc)
        atr = ATR(period=5)
        max_n = 10
        for i in range(len(bars_all)):
            window = bars_all[max(0, i - max_n + 1): i+1]
            if i == 0:
                atr.calculate(window)
            else:
                atr.update(window)
            # Values length must match window, no None corruption after warmup
            self.assertEqual(len(atr.values), len(window))
            # After warmup, values should be real numbers (not None) for window >= period
            if len(window) >= 5:
                self.assertIsNotNone(atr.values[-1], msg=f"i={i}")
                self.assertFalse(atr.values[-1] is None)
        # Full-history batch for final window must equal fresh calculate (sliced history loses Wilder memory, so we only verify incremental vs batch on full history)
        full = ATR(period=5)
        full_vals = full.calculate(bars_all)
        # Incremental's last value should equal full batch last value (both have full history)
        self.assertAlmostEqual(atr.values[-1], full_vals[-1], places=6)

    def test_reset_correctness(self):
        bars = _bars_from_ohlc([(i, i+3, i, i+1) for i in range(10)])
        atr = ATR(period=3)
        atr.calculate(bars)
        atr.clear()
        self.assertEqual(atr.values, [])
        self.assertEqual(atr._trs, [])
        self.assertIsNone(atr._atr)
        self.assertIsNone(atr._prev_close)
        self.assertEqual(atr._n, 0)
        self.assertIsNone(atr._last_ts)
        # Recalculate must be deterministic
        vals1 = list(atr.calculate(bars))
        atr.clear()
        vals2 = list(atr.calculate(bars))
        self.assertEqual(vals1, vals2)

    def test_warmup_behavior(self):
        # period=5, fewer bars than period → all None
        bars = _bars_from_ohlc([(i, i+2, i, i+1) for i in range(3)])
        atr = ATR(period=5)
        vals = atr.calculate(bars)
        self.assertEqual(vals, [None, None, None])
        # Exactly period bars → last is seed
        bars2 = _bars_from_ohlc([(i, i+2, i, i+1) for i in range(5)])
        vals2 = atr.calculate(bars2)
        self.assertIsNone(vals2[0])
        self.assertIsNone(vals2[3])
        self.assertIsNotNone(vals2[4])
        # period=1 → every bar has ATR = TR
        bars3 = _bars_from_ohlc([(0, 2, 0, 1), (1, 3, 1, 2)])
        atr1 = ATR(period=1)
        vals3 = atr1.calculate(bars3)
        # TRs: [2, max(2,|3-1|=2,|1-1|=0)=2] → ATRs [2,2]
        self.assertAlmostEqual(vals3[0], 2.0)
        self.assertAlmostEqual(vals3[1], 2.0)

    def test_repeated_updates(self):
        bars = _bars_from_ohlc([(i, i+4, i-1, i+2) for i in range(10)])
        atr = ATR(period=4)
        atr.calculate(bars)
        # Repeatedly update with same window should recompute, not append incorrectly
        vals_before = list(atr.values)
        # Feed same window again (not continuation — same timestamp)
        atr.update(bars)
        # _is_continuation should be False for same window, so it recalculates
        # Values should be identical
        self.assertEqual(atr.values, vals_before)
        # Now extend by one bar and update
        bars2 = bars + [_bars_from_ohlc([(10, 14, 9, 12)], start_ts=bars[-1].timestamp+60)[0]]
        atr.update(bars2)
        # Now last value should be new Wilder step
        self.assertEqual(len(atr.values), len(bars2))

    def test_no_nan_corruption(self):
        bars = _bars_from_ohlc([(i, i+5, i, i+2) for i in range(20)])
        atr = ATR(period=5)
        vals = atr.calculate(bars)
        for v in vals:
            if v is not None:
                self.assertFalse(math.isnan(v), msg=f"NaN in {v}")
                self.assertFalse(math.isinf(v), msg=f"Inf in {v}")
        # Incremental too
        atr2 = ATR(period=5)
        for i in range(len(bars)):
            window = bars[: i+1]
            if i == 0:
                atr2.calculate(window)
            else:
                atr2.update(window)
            for v in atr2.values:
                if v is not None:
                    self.assertFalse(math.isnan(v))
                    self.assertFalse(math.isinf(v))

    def test_realistic_candle_sequence(self):
        # Simulate BTC-like candles with varying TR
        import random
        random.seed(42)
        ohlc = []
        price = 50000
        for i in range(50):
            move = random.uniform(-200, 200)
            open_p = price
            close = price + move
            high = max(open_p, close) + random.uniform(0, 80)
            low = min(open_p, close) - random.uniform(0, 80)
            ohlc.append((open_p, high, low, close))
            price = close
        bars = _bars_from_ohlc(ohlc)
        atr = ATR(period=14)
        vals = atr.calculate(bars)
        # First 13 None
        self.assertEqual(vals[:13], [None]*13)
        self.assertIsNotNone(vals[13])
        # All subsequent not None
        for v in vals[13:]:
            self.assertIsNotNone(v)
            self.assertGreater(v, 0)
        # Incremental parity on realistic
        atr2 = ATR(period=14)
        for i in range(len(bars)):
            w = bars[: i+1]
            if i == 0:
                atr2.calculate(w)
            else:
                atr2.update(w)
        for a, b in zip(vals, atr2.values):
            if a is None and b is None:
                continue
            self.assertAlmostEqual(a, b, places=6)

    def test_empty_and_single_bar(self):
        atr = ATR(period=14)
        vals = atr.calculate([])
        self.assertEqual(vals, [])
        bars = _bars_from_ohlc([(0, 1, 0, 0.5)])
        vals = atr.calculate(bars)
        self.assertEqual(vals, [None])
        # update with empty should not crash
        atr2 = ATR(period=3)
        atr2.calculate([])
        vals = atr2.update([])
        self.assertEqual(vals, [])

    def test_missing_data_none_fields(self):
        # Bars with zero range
        bars = _bars_from_ohlc([(100, 100, 100, 100) for _ in range(10)])
        atr = ATR(period=3)
        vals = atr.calculate(bars)
        # TRs all 0 -> ATR 0
        for v in vals[2:]:
            self.assertAlmostEqual(v, 0.0, places=9)
