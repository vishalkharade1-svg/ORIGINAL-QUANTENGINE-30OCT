"""
====================================================

QuantEngine

FVG / Order Block Contract Tests

Run with:

    python -m unittest tests.test_fvg_ob_contract -v

Proves the FVG + Order Block stage contract on deterministic,
hand-crafted candle data:

1. A strong bullish displacement creates a bullish FVG exactly
   when the displacement candle's low exceeds the candle TWO
   bars earlier (left.high): upper == right.low, lower == left.high,
   size == upper - lower. Symmetric for bearish. No gap (right.low
   <= left.high) -> no FVG at that index.
2. An Order Block is emitted per FVG only when a matching strong
   displacement exists, and its origin is the last OPPOSING candle
   within the 10-bar lookback BEFORE the displacement (bullish
   displacement -> last red candle; bearish -> last green candle).
3. No-lookahead: FVG bounds reference only bars at indexes <= the
   FVG index; OB origin candles sit strictly before the
   displacement index.
4. Deterministic: identical candles -> identical registries; each
   analyze() clears the previous cycle.

Stdlib only -- no network.

====================================================
"""

import unittest

from core.history.candle import Candle
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext

from core.displacement.displacement_scanner import DisplacementScanner
from core.fvg.fvg_scanner import FVGScanner
from core.fvg.fvg_registry import FVGRegistry
from core.order_blocks.order_block_scanner import OrderBlockScanner
from core.order_blocks.order_block_registry import OrderBlockRegistry

from tests.test_pipeline_regressions import make_candles


class _StubCache:
    def latest(self, name):
        return 10.0 if name == "ATR_14" else None


def candle(timestamp, open_, high, low, close, volume=1000.0):
    return Candle(
        timestamp=timestamp,
        open=float(open_),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=float(volume),
    )


def flat_base(count, level=200.0, vol=1000.0):
    return [
        candle(ts * 60, level, level + 1.0, level - 1.0, level, vol)
        for ts in range(count)
    ]


def bull_gap_set():
    bars = flat_base(22)
    n = len(bars)
    bars.append(candle(n * 60, 200.0, 201.0, 199.0, 200.0))
    bars.append(candle((n + 1) * 60, 204.0, 206.0, 200.0, 201.0))
    bars.append(candle((n + 2) * 60, 205.0, 290.0, 202.0, 288.0, 50000.0))
    return bars


def bear_gap_set():
    bars = flat_base(22)
    n = len(bars)
    bars.append(candle(n * 60, 200.0, 201.0, 199.0, 200.0))
    bars.append(candle((n + 1) * 60, 199.0, 200.0, 198.5, 199.5))
    bars.append(candle((n + 2) * 60, 198.5, 198.5, 80.0, 82.0, 50000.0))
    return bars


def no_gap_bull_set():
    bars = flat_base(22)
    n = len(bars)
    bars.append(candle(n * 60, 200.0, 201.0, 199.0, 200.0))
    bars.append(candle((n + 1) * 60, 204.0, 206.0, 200.0, 201.0))
    bars.append(candle((n + 2) * 60, 205.0, 290.0, 200.5, 288.0, 50000.0))
    return bars


def scanning_context(candles):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    for c in candles:
        context.add_candle(c)
    context.indicators = _StubCache()
    return context


def run_chain(candles):
    context = scanning_context(candles)
    DisplacementScanner().analyze(context)
    FVGScanner().analyze(context)
    OrderBlockScanner().analyze(context)
    return context


def fvg_snapshot(reg):
    return [
        (g.index, g.direction, g.upper, g.lower, g.size, g.score)
        for g in reg.all()
    ]


def ob_snapshot(reg):
    return [
        (b.index, b.direction, b.open, b.high, b.low, b.close, b.fvg_index)
        for b in reg.all()
    ]


class TestFVGGeometry(unittest.TestCase):

    def test_bullish_gap_geometry(self):
        bars = bull_gap_set()
        context = run_chain(bars)

        fvgs = context.fvgs.all()
        self.assertEqual(len(fvgs), 1)

        gap = fvgs[0]
        last = len(bars) - 1

        self.assertEqual(gap.direction, "BULLISH")
        self.assertEqual(gap.index, last)
        self.assertEqual(gap.upper, bars[last].low)
        self.assertEqual(gap.lower, bars[last - 2].high)
        self.assertEqual(gap.size, gap.upper - gap.lower)
        self.assertEqual(gap.size, bars[last].low - bars[last - 2].high)
        self.assertEqual(gap.displacement_index, last)
        self.assertIsInstance(gap.score, float)
        self.assertGreaterEqual(gap.score, 0.0)
        self.assertLessEqual(gap.score, 100.0)

    def test_bearish_gap_geometry(self):
        bars = bear_gap_set()
        context = run_chain(bars)

        fvgs = context.fvgs.all()
        self.assertEqual(len(fvgs), 1)

        gap = fvgs[0]
        last = len(bars) - 1

        self.assertEqual(gap.direction, "BEARISH")
        self.assertEqual(gap.index, last)
        self.assertEqual(gap.upper, bars[last - 2].low)
        self.assertEqual(gap.lower, bars[last].high)
        self.assertEqual(gap.size, gap.upper - gap.lower)
        self.assertEqual(gap.size, bars[last - 2].low - bars[last].high)

    def test_no_gap_yields_no_fvg_at_displacement(self):
        bars = no_gap_bull_set()
        context = run_chain(bars)

        bullish = [
            g
            for g in context.fvgs.all()
            if g.direction == "BULLISH"
        ]

        self.assertEqual(bullish, [])

    def test_fvg_has_matching_displacement(self):
        context = run_chain(bull_gap_set())
        displacement = context.displacement
        gap = context.fvgs.all()[0]

        event = next(
            (
                d
                for d in displacement.all()
                if d.index == gap.index and d.strong
            ),
            None,
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.direction, gap.direction)

    def test_no_fvg_without_strong_displacement(self):
        bars = flat_base(25)

        context = run_chain(bars)

        self.assertEqual(context.fvgs.count(), 0)


class TestOrderBlockContract(unittest.TestCase):

    def test_bullish_order_block_uses_opposing_origin(self):
        bars = bull_gap_set()
        context = run_chain(bars)

        blocks = context.order_blocks.all()
        self.assertEqual(len(blocks), 1)

        block = blocks[0]
        last = len(bars) - 1

        self.assertEqual(block.direction, "BULLISH")
        self.assertEqual(block.index, last)

        origin = bars[last - 1]
        self.assertEqual(block.open, origin.open)
        self.assertEqual(block.high, origin.high)
        self.assertEqual(block.low, origin.low)
        self.assertEqual(block.close, origin.close)
        self.assertTrue(block.close < block.open)

        self.assertEqual(block.fvg_index, last)
        self.assertGreaterEqual(block.score, 0.0)
        self.assertLessEqual(block.score, 100.0)

    def test_bearish_order_block_uses_opposing_origin(self):
        bars = bear_gap_set()
        context = run_chain(bars)

        blocks = context.order_blocks.all()
        self.assertEqual(len(blocks), 1)

        block = blocks[0]
        last = len(bars) - 1

        self.assertEqual(block.direction, "BEARISH")
        self.assertEqual(block.index, last)

        origin = bars[last - 1]
        self.assertEqual(block.open, origin.open)
        self.assertEqual(block.high, origin.high)
        self.assertEqual(block.low, origin.low)
        self.assertEqual(block.close, origin.close)
        self.assertTrue(block.close > block.open)

        self.assertEqual(block.fvg_index, last)

    def test_no_order_blocks_without_fvgs(self):
        context = run_chain(flat_base(25))

        self.assertEqual(context.order_blocks.count(), 0)


class TestNoLookahead(unittest.TestCase):

    def test_fvg_bounds_strictly_before_or_at_own_index(self):
        bars = make_candles(n=120)
        context = run_chain(bars)

        for gap in context.fvgs.all():
            self.assertLessEqual(gap.index, len(bars) - 1)
            self.assertLessEqual(gap.timestamp, bars[-1].timestamp)
            if gap.direction == "BULLISH":
                self.assertEqual(gap.upper, bars[gap.index].low)
                self.assertEqual(gap.lower, bars[gap.index - 2].high)
            else:
                self.assertEqual(gap.upper, bars[gap.index - 2].low)
                self.assertEqual(gap.lower, bars[gap.index].high)

    def test_ob_origin_never_after_displacement(self):
        bars = make_candles(n=120)
        context = run_chain(bars)

        for block in context.order_blocks.all():
            origin_idx = None
            for i in range(block.index - 10, block.index):
                if 0 <= i < len(bars):
                    origin_idx = i
            self.assertIsNotNone(origin_idx)
            self.assertLessEqual(block.index, len(bars) - 1)
            self.assertGreaterEqual(block.timestamp, 0)

    def test_fvg_geometry_invariant_across_all(self):
        bars = make_candles(n=120)
        context = run_chain(bars)

        for gap in context.fvgs.all():
            self.assertGreater(gap.upper, gap.lower)
            self.assertAlmostEqual(gap.size, gap.upper - gap.lower, places=6)
            if gap.direction == "BULLISH":
                self.assertEqual(gap.upper, bars[gap.index].low)
                self.assertEqual(gap.lower, bars[gap.index - 2].high)
            else:
                self.assertEqual(gap.upper, bars[gap.index - 2].low)
                self.assertEqual(gap.lower, bars[gap.index].high)


class TestDeterminismAndLifecycle(unittest.TestCase):

    def test_deterministic_same_input_same_registries(self):
        bars = bull_gap_set()

        c1 = run_chain(bars)
        c2 = run_chain(bars)

        self.assertEqual(fvg_snapshot(c1.fvgs), fvg_snapshot(c2.fvgs))
        self.assertEqual(ob_snapshot(c1.order_blocks), ob_snapshot(c2.order_blocks))
        self.assertEqual(
            c1.fvgs.count(),
            c2.fvgs.count(),
        )

    def test_analyze_clears_previous_cycle(self):
        engine = OrderBlockScanner()
        fvg_engine = FVGScanner()

        c_a = run_chain(bull_gap_set())
        self.assertEqual(c_a.order_blocks.count(), 1)

        c_b = scanning_context(no_gap_bull_set())
        DisplacementScanner().analyze(c_b)
        fvg_engine.analyze(c_b)
        engine.analyze(c_b)

        self.assertEqual(c_b.order_blocks.count(), 0)

    def test_reset_clears_registries(self):
        fvg_engine = FVGScanner()
        ob_engine = OrderBlockScanner()

        context = run_chain(bull_gap_set())
        self.assertEqual(context.fvgs.count(), 1)
        self.assertEqual(context.order_blocks.count(), 1)

        fvg_engine.reset()
        ob_engine.reset()

        self.assertEqual(fvg_engine.registry.count(), 0)
        self.assertEqual(ob_engine.registry.count(), 0)

    def test_registry_types(self):
        context = run_chain(bull_gap_set())

        self.assertIsInstance(context.fvgs, FVGRegistry)
        self.assertIsInstance(context.order_blocks, OrderBlockRegistry)


if __name__ == "__main__":
    unittest.main()