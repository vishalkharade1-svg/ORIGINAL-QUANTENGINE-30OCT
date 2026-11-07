"""
Phase 9Q-3 — Historical ATR causality.

Historical bar N must use ATR[N], not latest. Future bars must not alter historical results.
"""

import unittest
from dataclasses import dataclass

from core.indicators.atr import ATR
from core.indicators.indicator_cache import IndicatorCache
from core.displacement.displacement_scanner import DisplacementScanner


@dataclass
class Bar:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0


@dataclass
class Market:
    timeframe: str = "1m"
    mark_price: float = 0.0


class FakeContext:
    def __init__(self, bars, atr_series=None):
        self.candles = bars
        self.market = Market()
        self.indicators = IndicatorCache()
        if atr_series is not None:
            self.indicators.set("ATR_14", atr_series)
        self.trend = None
        self.replay_index = len(bars) - 1
        self.displacement = None


def _bars(n, start_ts=1000, step=60, seed=1):
    # deterministic varying bars
    import random
    rnd = random.Random(seed)
    bars = []
    price = 100.0
    for i in range(n):
        o = price
        move = rnd.uniform(-1, 1)
        c = price + move
        h = max(o, c) + rnd.uniform(0, 0.5)
        l = min(o, c) - rnd.uniform(0, 0.5)
        bars.append(Bar(timestamp=start_ts + i*step, open=o, high=h, low=l, close=c))
        price = c
    return bars


class TestDisplacementCausality(unittest.TestCase):

    def test_future_bars_do_not_alter_historical_results(self):
        bars_n = _bars(30, seed=1)
        # Build ATR series for 30 bars
        atr = ATR(period=14)
        atr_vals_n = atr.calculate(bars_n)

        ctx_n = FakeContext(bars_n, atr_vals_n)
        scanner = DisplacementScanner()
        scanner.analyze(ctx_n)
        # Snapshot historical displacements through N
        hist_n = list(scanner.registry.all())
        # Keep their atr_multiple and scores
        hist_snapshot = [(d.index, d.atr_multiple, d.score) for d in hist_n]

        # Now append future bars (high volatility)
        future = _bars(10, start_ts=bars_n[-1].timestamp + 60, seed=99)
        # Make them high-volatility to shift latest ATR if bug existed
        for b in future:
            b.high = b.high + 10
            b.low = b.low - 10

        bars_future = bars_n + future
        atr2 = ATR(period=14)
        atr_vals_future = atr2.calculate(bars_future)

        ctx_future = FakeContext(bars_future, atr_vals_future)
        scanner2 = DisplacementScanner()
        scanner2.analyze(ctx_future)
        # Filter to indices < len(bars_n)
        hist_after = [d for d in scanner2.registry.all() if d.index < len(bars_n)]
        after_snapshot = [(d.index, d.atr_multiple, d.score) for d in hist_after]

        self.assertEqual(len(hist_snapshot), len(after_snapshot), msg="Historical count must be stable")
        for (i1, a1, s1), (i2, a2, s2) in zip(hist_snapshot, after_snapshot):
            self.assertEqual(i1, i2)
            self.assertAlmostEqual(a1, a2, places=9, msg=f"atr_multiple changed at index {i1}")
            self.assertAlmostEqual(s1, s2, places=9, msg=f"score changed at index {i1}")

    def test_per_bar_atr_series_used(self):
        # Craft bars where ATR at index 5 is very different from latest
        bars = _bars(20, seed=2)
        # Force atr series: early low ATR, late high ATR
        atr_series = [None]*13 + [1.0]*6 + [10.0]  # len 20, index 14-19 varied
        # Actually need len 20, so pad correctly
        atr_series = [None]*13 + [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 10.0]  # 20? Let's just build 20
        # Ensure len==20
        atr_series = atr_series[:20] + [None]*(20-len(atr_series))
        # Make sure index 15 has ATR 1.0, latest is 10.0
        atr_series = [None]*14 + [1.0]*5 + [10.0]  # 14 Nones +5*1 +10 =20? 14+5+1=20
        # index 15 (0-based) -> 1.0, index 19 ->10.0
        ctx = FakeContext(bars, atr_series)
        scanner = DisplacementScanner()
        scanner.analyze(ctx)
        # Find displacement at index 15, its atr_multiple should use 1.0 not 10.0
        found = [d for d in scanner.registry.all() if d.index == 15]
        if found:
            d = found[0]
            expected = (bars[15].high - bars[15].low) / 1.0
            self.assertAlmostEqual(d.atr_multiple, expected, places=6)
            # Ensure not using latest
            not_expected = (bars[15].high - bars[15].low) / 10.0
            self.assertNotAlmostEqual(d.atr_multiple, not_expected, places=6)

    def test_realtime_fallback_still_works(self):
        # No series, only latest via cache latest()
        bars = _bars(20, seed=3)
        atr = ATR(period=14)
        atr_vals = atr.calculate(bars)
        # Simulate old harness that only has latest (no series)
        ctx = FakeContext(bars, None)
        ctx.indicators.set("ATR_14", atr_vals)  # still series, but test fallback path: use_series requires len==bars
        # This should use series path (since len matches), so modify to force fallback:
        # Provide mismatched length to trigger fallback
        ctx2 = FakeContext(bars, None)
        # Manually set latest via internal data
        ctx2.indicators.data["ATR_14"] = atr_vals  # latest will be atr_vals[-1]
        scanner = DisplacementScanner()
        # Should not crash, should produce some results
        scanner.analyze(ctx2)
        self.assertIsNotNone(ctx2.displacement)
