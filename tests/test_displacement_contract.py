"""
====================================================

QuantEngine

Displacement Scanner Contract Tests

Run with:

    python -m unittest tests.test_displacement_contract -v

Proves the displacement stage contract:

1. The scanner populates a valid DisplacementRegistry for any
   history with >= 2 candles and a positive ATR: every entry has
   a score in [0, 100], a grade from the fixed set, a consistent
   `strong` flag, a monotonic index/timestamp, and the declared
   timeframe.
2. Deterministic: identical bars produce the identical registry;
   each analyze() clears the previous cycle (no stale entries).
3. Current-bar correctness (no lookahead at the decision point):
   the latest entry's metrics match a manual calculation from
   prior bars + the current bar; liquidity-sweep flags require
   the current bar to trade through the PRIOR lookback window's
   extreme and close back inside, never a future bar.
4. The full canonical pipeline publishes a current-bar-consistent
   registry and re-runs deterministically.

Stdlib only -- no network.

====================================================
"""

import unittest

from core.history.candle import Candle
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.displacement.displacement_scanner import DisplacementScanner
from core.displacement.displacement_registry import DisplacementRegistry

from tests.test_pipeline_regressions import make_candles

GRADES = ("ELITE", "STRONG", "MODERATE", "WEAK")


class _StubCache:
    def latest(self, name):
        return 50.0 if name == "ATR_14" else None


def candle(timestamp, open_, high, low, close, volume=1000.0):
    return Candle(
        timestamp=timestamp,
        open=open_,
        high=float(high),
        low=float(low),
        close=float(close),
        volume=float(volume),
    )


def scanning_context(candles, market_timeframe="1m"):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe=market_timeframe)
    for c in candles:
        context.add_candle(c)
    context.indicators = _StubCache()
    return context


def run_scanner(candles, market_timeframe="1m"):
    context = scanning_context(candles, market_timeframe)
    DisplacementScanner().analyze(context)
    return context


class TestDisplacementScannerContract(unittest.TestCase):

    def setUp(self):
        self.candles = list(make_candles(n=120))

    def test_short_history_yields_empty_registry(self):
        context = run_scanner(self.candles[:1])

        self.assertIsInstance(context.displacement, DisplacementRegistry)
        self.assertEqual(context.displacement.count(), 0)

    def test_registry_valid_for_full_history(self):
        context = run_scanner(self.candles)
        reg = context.displacement

        self.assertIsInstance(reg, DisplacementRegistry)
        self.assertGreater(reg.count(), 0)
        self.assertEqual(reg.count(), len(self.candles))

        for i, d in enumerate(reg.all()):
            self.assertEqual(d.index, i)
            self.assertEqual(d.timeframe, "1m")
            self.assertIn(d.direction, {"BULLISH", "BEARISH"})
            self.assertIn(d.grade, GRADES)
            self.assertEqual(d.strong, d.score >= 75)
            self.assertEqual(
                d.grade,
                (
                    "ELITE"
                    if d.score >= 90
                    else "STRONG"
                    if d.score >= 75
                    else "MODERATE"
                    if d.score >= 60
                    else "WEAK"
                ),
            )

    def test_scores_bounded_0_100(self):
        reg = run_scanner(self.candles).displacement

        self.assertTrue(
            all(0.0 <= d.score <= 100.0 for d in reg.all())
        )

    def test_indices_and_timestamps_monotonic(self):
        reg = run_scanner(self.candles).displacement

        for a, b in zip(reg.all(), reg.all()[1:]):
            self.assertLess(a.index, b.index)
            self.assertLess(a.timestamp, b.timestamp)

    def test_deterministic_same_input_same_registry(self):
        a = run_scanner(self.candles).displacement
        b = run_scanner(self.candles).displacement

        def snapshot(reg):
            return [
                (d.index, d.direction, d.score, d.grade, d.strong)
                for d in reg.all()
            ]

        self.assertEqual(snapshot(a), snapshot(b))

    def test_analyze_clears_previous_cycle(self):
        long = list(make_candles(n=80))
        short = list(make_candles(n=40))

        engine = DisplacementScanner()
        context_a = scanning_context(long)
        engine.analyze(context_a)

        context_b = scanning_context(short)
        engine.analyze(context_b)

        reg = context_b.displacement
        self.assertEqual(reg.count(), len(short))
        self.assertTrue(
            all(d.index < len(short) for d in reg.all())
        )

    def test_reset_clears_registry(self):
        engine = DisplacementScanner()
        context = scanning_context(self.candles)
        engine.analyze(context)

        self.assertGreater(context.displacement.count(), 0)

        engine.reset()

        self.assertEqual(engine.registry.count(), 0)

    def test_latest_bar_metrics_match_manual_calc(self):
        bars = self.candles
        atr = 50.0

        context = run_scanner(bars)
        latest = context.displacement.latest()
        i = len(bars) - 1
        c = bars[i]

        self.assertEqual(latest.index, i)

        candle_range = c.high - c.low
        body = abs(c.close - c.open)

        self.assertAlmostEqual(latest.body, body, places=6)
        self.assertAlmostEqual(latest.candle_range, candle_range, places=6)
        self.assertAlmostEqual(latest.body_ratio, body / candle_range, places=6)
        self.assertAlmostEqual(latest.atr_multiple, candle_range / atr, places=6)

        expected_direction = (
            "BULLISH" if c.close >= c.open else "BEARISH"
        )
        self.assertEqual(latest.direction, expected_direction)

        if c.close >= c.open:
            expected_position = (c.close - c.low) / candle_range
        else:
            expected_position = (c.high - c.close) / candle_range
        self.assertAlmostEqual(
            latest.close_position, expected_position, places=6
        )

        prev = bars[i - 1]
        self.assertEqual(latest.broke_previous_high, c.high > prev.high)
        self.assertEqual(latest.broke_previous_low, c.low < prev.low)

        volume_window = [b.volume for b in bars[i - 20:i]]
        avg = sum(volume_window) / 20
        self.assertAlmostEqual(
            latest.volume_ratio, c.volume / avg, places=6
        )

    def test_liquidity_sweep_requires_prior_window_extreme(self):
        ts = 0
        bars = [
            candle(ts + j * 60, 100.0, 102.0, 98.0, 101.0)
            for j in range(21)
        ]

        bars[21 - 1] = candle(
            bars[21-1].timestamp,
            100.0,
            105.0,
            96.0,
            104.0,
        )

        context = run_scanner(bars)
        latest = context.displacement.latest()

        self.assertTrue(latest.liquidity_sweep)

    def test_no_sweep_when_no_extreme_break(self):
        bars = [
            candle(j * 60, 100.0, 102.0, 98.0, 101.0)
            for j in range(21)
        ]

        context = run_scanner(bars)
        latest = context.displacement.latest()

        self.assertFalse(latest.liquidity_sweep)

    def test_volume_ratio_uses_prior_window_only(self):
        bars = [
            candle(j * 60, 100.0, 101.0, 99.0, 100.0, volume=500.0)
            for j in range(21)
        ]
        bars[20] = candle(
            bars[20].timestamp,
            100.0,
            101.0,
            99.0,
            100.0,
            volume=5000.0,
        )

        context = run_scanner(bars)
        latest = context.displacement.latest()

        self.assertAlmostEqual(latest.volume_ratio, 10.0, places=6)


class TestDisplacementPipelineContract(unittest.TestCase):

    def test_pipeline_displacement_consistent_and_deterministic(self):
        candles = list(make_candles(n=120))

        def run():
            context = PipelineContext()
            context.market = MarketState(symbol="TEST", timeframe="1m")
            pipeline = InstitutionalPipeline(context)
            for c in candles:
                context.add_candle(c)
                pipeline.process()
            return context

        c1 = run()
        c2 = run()

        self.assertIsInstance(c1.displacement, DisplacementRegistry)
        self.assertEqual(c1.displacement.count(), len(candles))
        self.assertEqual(c1.displacement.latest().index, len(candles) - 1)

        snapshot1 = [
            (d.index, d.direction, d.score, d.grade)
            for d in c1.displacement.all()
        ]
        snapshot2 = [
            (d.index, d.direction, d.score, d.grade)
            for d in c2.displacement.all()
        ]

        self.assertEqual(snapshot1, snapshot2)


if __name__ == "__main__":
    unittest.main()