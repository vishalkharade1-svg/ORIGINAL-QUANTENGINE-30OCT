"""
====================================================

QuantEngine

Incremental Scan Contract Tests (STATUS 90)

Run with:

    python -m unittest tests.test_incremental_scan -v

Proves the incremental O(window) -> O(new-bar) scan
memoization (SwingEngine fractal + DisplacementScanner
window fields) is behavior-identical to a full rescan:

1. SwingEngine.scan with the memo produces the same swings
   (index/kind/price/score) as a fresh engine over the same
   bars -- determinism of the cache.
2. The fractal memo does not leak across reset(): scanning a
   different bar set after reset() yields a state consistent
   with a brand-new engine (no stale absolute-index hits).
3. DisplacementScanner window fields (volume_ratio,
   liquidity_sweep) match a reference rescan that recomputes
   every value from raw windows, including the rule that a bar
   whose lookback window is partially dropped (relative
   position < LOOKBACK) reports the field as 0/False.

Stdlib only -- no network, no pipeline.

====================================================
"""

import unittest

from core.market_structure.swing_engine import SwingEngine
from core.displacement.displacement_scanner import DisplacementScanner

from tests.test_pipeline_regressions import make_candles


class _Bar:

    def __init__(self, timestamp, open, high, low, close, volume):
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


def _make_bars(n, start_price=60000.0, seed=7):
    return make_candles(n=n, start_price=start_price, seed=seed)


class TestSwingScanIncremental(unittest.TestCase):

    def test_memo_scan_matches_full_rescan(self):
        bars = _make_bars(n=200)

        fresh = SwingEngine().scan(list(bars), start_index=0)

        engine = SwingEngine()
        # Prime the memo with a small prefix, then scan the full set.
        engine.scan(list(bars[:60]), start_index=0)
        incremental = engine.scan(list(bars), start_index=0)

        self.assertEqual(len(fresh.all()), len(incremental.all()))

        for x, y in zip(fresh.all(), incremental.all()):
            self.assertEqual(x.index, y.index)
            self.assertEqual(x.kind, y.kind)
            self.assertEqual(x.price, y.price)
            self.assertEqual(x.score, y.score)

    def test_reset_clears_fractal_memo(self):
        bars_a = _make_bars(n=120, start_price=60000.0)
        bars_b = _make_bars(n=120, start_price=61000.0)

        engine = SwingEngine()

        engine.scan(list(bars_a), start_index=0)

        engine.reset()

        # After reset, scanning different data must behave like a
        # brand-new engine: no stale absolute-index cache hits.
        reference = SwingEngine().scan(list(bars_b), start_index=0)

        after_reset = engine.scan(list(bars_b), start_index=0)

        self.assertEqual(len(reference.all()), len(after_reset.all()))

        for x, y in zip(reference.all(), after_reset.all()):
            self.assertEqual(x.index, y.index)
            self.assertEqual(x.kind, y.kind)
            self.assertEqual(x.price, y.price)


class TestDisplacementScanIncremental(unittest.TestCase):

    def _field_extract(self, registry, name):
        return {d.index: getattr(d, name) for d in registry.all()}

    def test_volume_ratio_and_liquidity_sweep_match_recompute(self):
        bars = _make_bars(n=120)

        reference = DisplacementScanner()

        # Standalone recompute mirrors the scanner's raw windows.
        atr = None
        volumes = [c.volume for c in bars]

        ref_volume = {}
        ref_sweep = {}

        lo = reference.LIQUIDITY_LOOKBACK

        for i, candle in enumerate(bars):
            vratio = 0.0
            if i >= 20:
                avg = sum(volumes[i-20:i]) / 20
                if avg > 0:
                    vratio = candle.volume / avg
            ref_volume[i] = vratio

            sweep = False
            if i >= lo:
                window = bars[i - lo:i]
                direction = "BULLISH" if candle.close >= candle.open else "BEARISH"
                if direction == "BULLISH":
                    prior_low = min(b.low for b in window)
                    sweep = candle.low < prior_low and candle.close > prior_low
                else:
                    prior_high = max(b.high for b in window)
                    sweep = candle.high > prior_high and candle.close < prior_high
            ref_sweep[i] = sweep

        scanner = DisplacementScanner()

        # analyze needs a context, so exercise the real code path
        # through a context-shaped object.
        scanner.analyze(_ContextBars(bars))

        got_volume = self._field_extract(scanner.registry, "volume_ratio")
        got_sweep = self._field_extract(scanner.registry, "liquidity_sweep")

        self.assertEqual(got_volume, ref_volume)
        self.assertEqual(got_sweep, ref_sweep)

    def test_reset_clears_window_memo(self):
        scanner = DisplacementScanner()

        bars_a = _make_bars(n=120, start_price=60000.0)
        ctx_a = _Ctx(bars_a)
        scanner.analyze(ctx_a)
        count_a = scanner.registry.count()

        scanner.reset()

        bars_b = _make_bars(n=120, start_price=64000.0)
        ctx_b = _Ctx(bars_b)
        scanner.analyze(ctx_b)
        count_b = scanner.registry.count()

        # Same geometry: both feeds produce registries of equal size
        # only if the memo was cleared (no stale hits inflating
        # intermediate state). Also verify scan resumed cleanly.
        reference = DisplacementScanner()
        reference.analyze(_Ctx(bars_b))
        self.assertEqual(reference.registry.count(), count_b)


class _IndicatorHolder:

    def __init__(self, atr):
        self._atr = atr

    def latest(self, name):
        if name == "ATR_14":
            return self._atr
        return None


class _Ctx:

    def __init__(self, bars):
        self.candles = list(bars)
        self.market = _ContextBars._market()
        self.replay_index = len(bars)
        self.trend = None
        self.indicators = _IndicatorHolder(atr=100.0)


class _ContextBars:

    class _market:
        timeframe = "1m"

    def __init__(self, bars):
        self.candles = list(bars)
        self.market = self._market()
        self.replay_index = len(self.candles)
        self.trend = None
        self.indicators = _IndicatorHolder(atr=100.0)


if __name__ == "__main__":
    unittest.main()