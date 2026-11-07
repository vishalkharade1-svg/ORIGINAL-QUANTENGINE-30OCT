"""
====================================================

QuantEngine

Trend Engine Contract Tests

Run with:

    python -m unittest tests.test_trend_engine_contract -v

Proves the trend stage contract:

1. Never reports BULLISH/BEARISH/RANGE from missing/malformed
   upstream indicators -- always WARMUP / INSUFFICIENT_DATA.
2. BULLISH and BEARISH trends of equal strength score
   identically (no directional bias).
3. Greatest possible alignment tops out at 100 in EITHER
   direction; missing ADX lowers but does not zero the trend.
4. strength/confidence are populated (score/100), never a
   permanent 0.0.
5. RANGE is a real observation, distinct from WARMUP.

Stdlib + dataclasses only -- no network, no pipeline needed.

====================================================
"""

import unittest

from core.history.candle import Candle
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.trend.trend_engine import TrendEngine


def make_candle(close):
    return Candle(
        timestamp=0,
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=100,
    )


class StubCache:
    def __init__(self, values):
        self._values = values

    def latest(self, name):
        return self._values.get(name)


def run_trend(close, values):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    context.add_candle(make_candle(close))
    context.indicators = StubCache(values)
    return TrendEngine().analyze(context)


class TestTrendDirectionalScoring(unittest.TestCase):

    def test_perfect_bullish_scores_100(self):
        state = run_trend(
            close=100,
            values={
                "EMA_20": 90,
                "EMA_50": 80,
                "EMA_200": 70,
                "ADX_14": 30,
                "RSI_14": 60,
                "ATR_14": 5,
            },
        )

        self.assertEqual(state.direction, "BULLISH")
        self.assertEqual(state.regime, "TREND")
        self.assertTrue(state.ema_alignment)
        self.assertTrue(state.adx_confirmed)
        self.assertTrue(state.momentum)
        self.assertTrue(state.price_above_ema20)
        self.assertTrue(state.price_above_ema200)
        self.assertFalse(state.price_below_ema20)
        self.assertEqual(state.score, 100)

    def test_perfect_bearish_scores_100_symmetric(self):
        state = run_trend(
            close=100,
            values={
                "EMA_20": 110,
                "EMA_50": 120,
                "EMA_200": 130,
                "ADX_14": 30,
                "RSI_14": 40,
                "ATR_14": 5,
            },
        )

        self.assertEqual(state.direction, "BEARISH")
        self.assertEqual(state.regime, "TREND")
        self.assertTrue(state.ema_alignment)
        self.assertTrue(state.adx_confirmed)
        self.assertTrue(state.momentum)
        self.assertTrue(state.price_below_ema20)
        self.assertTrue(state.price_below_ema200)
        self.assertFalse(state.price_above_ema20)
        self.assertEqual(
            state.score,
            100,
            "Equal-strength bearish trend must score exactly "
            "like the bullish one -- no directional bias.",
        )

    def test_bearish_without_confirmation_scores_70(self):
        state = run_trend(
            close=100,
            values={
                "EMA_20": 110,
                "EMA_50": 120,
                "EMA_200": 130,
                "ADX_14": 20,  # below the 25 threshold
                "RSI_14": 60,  # not bearish momentum
                "ATR_14": 5,
            },
        )

        self.assertEqual(state.direction, "BEARISH")
        self.assertFalse(state.adx_confirmed)
        self.assertFalse(state.momentum)
        self.assertEqual(
            state.score,
            70,  # 35 alignment + 35 price-position
        )

    def test_strength_and_confidence_are_populated(self):
        state = run_trend(
            close=100,
            values={
                "EMA_20": 90,
                "EMA_50": 80,
                "EMA_200": 70,
                "ADX_14": 30,
                "RSI_14": 60,
                "ATR_14": 5,
            },
        )

        self.assertAlmostEqual(state.strength, 1.0)
        self.assertAlmostEqual(state.confidence, 1.0)
        self.assertAlmostEqual(state.strength, state.score / 100.0)

    def test_missing_adx_does_not_zero_trend(self):
        state = run_trend(
            close=100,
            values={
                "EMA_20": 90,
                "EMA_50": 80,
                "EMA_200": 70,
                "ADX_14": None,
                "RSI_14": 60,
                "ATR_14": 5,
            },
        )

        self.assertEqual(state.direction, "BULLISH")
        self.assertFalse(state.adx_confirmed)
        self.assertEqual(state.score, 80)  # 35 + (10,10,15) + 10


class TestTrendRangeAndWarmup(unittest.TestCase):

    def test_range_is_a_real_observation(self):
        state = run_trend(
            close=100,
            values={
                "EMA_20": 99.5,
                "EMA_50": 100.5,
                "EMA_200": 100.0,
                "ADX_14": 14,
                "RSI_14": 50,
                "ATR_14": 1,
            },
        )

        self.assertEqual(state.direction, "RANGE")
        self.assertEqual(state.regime, "RANGE")
        self.assertFalse(state.ema_alignment)
        self.assertEqual(state.score, 0)

    def test_warmup_when_any_ema_missing(self):
        state = run_trend(
            close=100,
            values={
                "EMA_20": 90,
                "EMA_50": None,
                "EMA_200": 70,
                "ADX_14": 30,
                "RSI_14": 60,
                "ATR_14": 5,
            },
        )

        self.assertEqual(state.direction, "WARMUP")
        self.assertEqual(state.regime, "WARMUP")
        self.assertNotIn(
            state.direction,
            ("BULLISH", "BEARISH", "RANGE"),
            "Missing EMA values must never fabricate a trend.",
        )

    def test_warmup_when_no_indicators(self):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        context.add_candle(make_candle(100))
        context.indicators = None

        state = TrendEngine().analyze(context)

        self.assertEqual(state.direction, "WARMUP")
        self.assertEqual(state.score, 0)

    def test_warmup_when_no_candles(self):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        context.indicators = StubCache(
            {
                "EMA_20": 90,
                "EMA_50": 80,
                "EMA_200": 70,
            },
        )

        state = TrendEngine().analyze(context)

        self.assertEqual(state.direction, "WARMUP")
        self.assertEqual(state.regime, "WARMUP")


if __name__ == "__main__":
    unittest.main()