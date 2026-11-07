"""
====================================================

QuantEngine

Indicator Cache / Pipeline Data Contract Tests

Run with:

    python -m unittest tests.test_indicator_contract -v

These tests prove the data -> cache -> context -> pipeline
contract that every downstream stage depends on:

1. context.indicators is ALWAYS the same object as the
   IndicatorEngine's shared cache (never detached/replaced).
2. Cache keys are never emptied once bars exist.
3. Every indicator series is exactly aligned with the bar
   window (same length, warm-up Nones, then real floats).
4. Indicators are deterministic: same input -> same output.
5. reset() re-links the shared cache instead of leaving
   context.indicators as None.
6. An IndicatorEngine accidentally registered as a pipeline
   engine can no longer publish an empty/detached cache into
   context (the historical "Cache keys = []" failure).

Stdlib + dataclasses only -- no network, no pandas.

====================================================
"""

import unittest

from core.history.candle import Candle
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.indicators.indicator_engine import IndicatorEngine
from core.indicators.indicator_cache import IndicatorCache
from core.indicators.ema import EMA

from tests.test_pipeline_regressions import make_candles


CACHE_KEYS = {
    "EMA_20",
    "EMA_50",
    "EMA_200",
    "ATR_14",
    "ADX_14",
    "RSI_14",
}


def build_pipeline_and_feed(n=50):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")

    pipeline = InstitutionalPipeline(context)

    candles = make_candles(n=n)

    for c in candles:
        context.add_candle(c)
        pipeline.process()

    return context, pipeline, candles


# ==========================================================
# Data -> Cache -> Context -> Pipeline
# ==========================================================

class TestIndicatorDataPipelineContract(unittest.TestCase):

    def test_cache_identity_is_stable_every_candle(self):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")

        pipeline = InstitutionalPipeline(context)

        # Initially linked at construction.
        self.assertIs(
            context.indicators,
            pipeline.indicators.cache,
        )

        for i in range(1, 51):
            context.add_candle(make_candles(n=i)[-1])
            pipeline.process()

            self.assertIs(
                context.indicators,
                pipeline.indicators.cache,
                f"context.indicators detached from the shared "
                f"cache on candle {i}.",
            )

    def test_cache_keys_never_empty_once_bars_exist(self):
        context, pipeline, candles = build_pipeline_and_feed(n=1)

        self.assertIsInstance(context.indicators, IndicatorCache)
        self.assertEqual(set(context.indicators.data.keys()), CACHE_KEYS)

        for step in (10, 100, 400):
            context, pipeline, candles = build_pipeline_and_feed(n=step)
            self.assertEqual(
                set(context.indicators.data.keys()),
                CACHE_KEYS,
                f"Cache key set changed at {step} candles.",
            )
            self.assertNotEqual(
                list(context.indicators.data.keys()),
                [],
                "Cache key list must never be empty once a bar "
                "has been processed.",
            )

    def test_series_aligned_with_bar_window(self):
        for n in (1, 20, 100, 400):
            context, pipeline, candles = build_pipeline_and_feed(n=n)

            self.assertEqual(len(context.candles), n)

            for name in CACHE_KEYS:
                values = context.indicators.get(name)
                self.assertEqual(
                    len(values),
                    n,
                    f"{name} length {len(values)} != bars {n}.",
                )

    def test_warmup_nones_then_real_values(self):
        candles = make_candles(n=200)
        bars = list(candles)

        engine = InstitutionalPipeline(PipelineContext()).indicators
        cache = engine.update(list(bars))

        # EMA_20: first value at bar index 19.
        self.assertIsNone(cache.get("EMA_20")[19 - 1])
        self.assertIsInstance(cache.get("EMA_20")[19], float)

        # ATR_14: first value at bar index 13.
        self.assertIsNone(cache.get("ATR_14")[12])
        self.assertIsInstance(cache.get("ATR_14")[13], float)

        # RSI_14: first value at bar index 14.
        self.assertIsNone(cache.get("RSI_14")[13])
        self.assertIsInstance(cache.get("RSI_14")[14], float)

        # ADX_14 needs 2*period = 28 bars before first value.
        self.assertIsNone(cache.get("ADX_14")[26])
        self.assertIsInstance(cache.get("ADX_14")[27], float)

        # EMA_200 needs 200 bars.
        self.assertIsNone(cache.get("EMA_200")[198])
        self.assertIsInstance(cache.get("EMA_200")[199], float)

    def test_latest_returns_float_after_full_warmup(self):
        context, pipeline, candles = build_pipeline_and_feed(n=400)

        for name in CACHE_KEYS:
            self.assertIsNotNone(
                context.indicators.latest(name),
                f"{name}.latest() is None after 400 candles.",
            )
            self.assertNotIsInstance(
                context.indicators.latest(name),
                bool,
            )

    def test_same_input_same_output(self):
        candles = make_candles(n=300)
        bars = list(candles)

        first = InstitutionalPipeline(
            PipelineContext(),
        ).indicators.update(bars)

        second = InstitutionalPipeline(
            PipelineContext(),
        ).indicators.update(bars)

        for name in CACHE_KEYS:
            self.assertEqual(
                first.get(name),
                second.get(name),
                f"{name} is not deterministic across identical input.",
            )

    def test_update_empty_bars_preserves_cache(self):
        context, pipeline, candles = build_pipeline_and_feed(n=100)

        before = {
            name: context.indicators.latest(name)
            for name in CACHE_KEYS
        }

        returned = pipeline.indicators.update([])

        self.assertIs(returned, pipeline.indicators.cache)
        self.assertEqual(
            set(pipeline.indicators.cache.data.keys()),
            CACHE_KEYS,
        )

        after = {
            name: pipeline.indicators.cache.latest(name)
            for name in CACHE_KEYS
        }

        self.assertEqual(before, after)

    def test_reset_relinks_shared_cache(self):
        context, pipeline, candles = build_pipeline_and_feed(n=200)

        pipeline.reset()

        # The indicator cache must never stay detached: after a
        # full reset, context.indicators is the (emptied) shared
        # cache, never None, and never a different object.
        self.assertIsInstance(context.indicators, IndicatorCache)
        self.assertIs(context.indicators, pipeline.indicators.cache)
        self.assertIsNone(context.indicators.latest("EMA_20"))

        # Feeding candles after reset restores live values on
        # the same shared cache object.
        context, pipeline, candles = build_pipeline_and_feed(
            n=300,
        )

        self.assertIs(context.indicators, pipeline.indicators.cache)
        self.assertIsNotNone(context.indicators.latest("ATR_14"))


# ==========================================================
# Detachment guards (the historical "Cache keys = []" bug)
# ==========================================================

class TestIndicatorEngineDetachmentGuard(unittest.TestCase):

    def test_bare_indicator_engine_analyze_refuses(self):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")

        for c in make_candles(n=20):
            context.add_candle(c)

        sentinel = IndicatorCache()
        context.indicators = sentinel

        engine = IndicatorEngine()  # nothing registered

        result = engine.analyze(context)

        self.assertIsNone(result)
        self.assertIs(
            context.indicators,
            sentinel,
            "A bare IndicatorEngine must not replace "
            "context.indicators with an empty cache.",
        )

    def test_registering_extra_indicator_engine_is_ignored(self):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")

        pipeline = InstitutionalPipeline(context)

        added = IndicatorEngine()
        pipeline.register(added)

        self.assertNotIn(
            added,
            pipeline.engines,
            "IndicatorEngine must never be allowed into the "
            "engine registry.",
        )

        for c in make_candles(n=120):
            context.add_candle(c)
            pipeline.process()

        # The old main.py double-registration failure mode:
        # a second, unconfigured IndicatorEngine publishing an
        # empty cache. context must still hold the real shared
        # cache, fully populated.
        self.assertIs(context.indicators, pipeline.indicators.cache)
        self.assertEqual(
            set(context.indicators.data.keys()),
            CACHE_KEYS,
        )
        self.assertIsNotNone(context.indicators.latest("ATR_14"))

    def test_unregister_removes_cache_entry(self):
        engine = IndicatorEngine()

        ema = EMA(20)
        engine.register(ema)

        bars = list(make_candles(n=100))

        cache = engine.update(bars)

        self.assertIn("EMA_20", cache.data)

        engine.unregister(ema)

        self.assertNotIn(
            "EMA_20",
            engine.cache.data,
            "unregister() must drop the indicator's cache "
            "entry, otherwise stale series linger forever.",
        )


# ==========================================================

class TestIndicatorCacheAPI(unittest.TestCase):

    def test_latest_none_for_missing_and_warmup(self):
        cache = IndicatorCache()

        self.assertIsNone(cache.get("NOPE"))
        self.assertIsNone(cache.latest("NOPE"))

        cache.set("X", [None, None, 1.5])

        # latest() returns the final element exactly once it
        # becomes a real value (warm-up Nones are still Nones).
        self.assertEqual(cache.latest("X"), 1.5)

    def test_clear(self):
        cache = IndicatorCache()
        cache.set("X", [1.0])

        cache.clear()

        self.assertEqual(cache.data, {})


if __name__ == "__main__":
    unittest.main()