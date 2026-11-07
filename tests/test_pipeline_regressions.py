"""
====================================================

QuantEngine

Pipeline Regression Tests

Real unittest.TestCase coverage for the specific
contract bugs found and fixed in this codebase, plus an
end-to-end synthetic smoke test of the full institutional
pipeline. Run with:

    python -m unittest tests.test_pipeline_regressions -v

or, from the repo root:

    python -m unittest discover -s tests

These tests use only stdlib + dataclasses -- no pandas,
no httpx, no network -- so they run in any environment,
including CI, without needing exchange connectivity or
historical parquet files.

====================================================
"""

import random
import unittest

from core.history.candle import Candle
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.displacement.displacement import Displacement
from core.displacement.displacement_scanner import DisplacementScanner
from core.displacement.displacement_registry import DisplacementRegistry

from core.fvg.fair_value_gap import FairValueGap
from core.fvg.fvg_scanner import FVGScanner

from core.order_blocks.order_block import OrderBlock

from core.registry.indexed_registry import IndexedRegistry
from core.market_structure.swing_registry import SwingRegistry
from core.market_structure.swing import Swing

from core.market_structure.swing_trend_engine import SwingStructureTrendEngine


# ==========================================================
# Helpers
# ==========================================================

def make_candles(n=400, start_price=60000.0, seed=42):
    """
    Deterministic synthetic OHLCV feed with periodic strong
    impulse candles, so displacement/FVG/OB logic has real
    signal to find. Not a substitute for real market data --
    only meant to exercise every stage of the pipeline without
    crashing and to produce non-trivial (non-zero) output.
    """

    rng = random.Random(seed)

    candles = []
    price = start_price
    ts = 1_700_000_000

    for i in range(n):

        drift = 0.15 if (i // 50) % 2 == 0 else -0.15

        if i % 50 == 25:
            body = price * 0.02 * (1 if drift > 0 else -1)
        else:
            body = (
                price * 0.0015 * rng.uniform(-1, 1)
                + price * 0.0004 * drift
            )

        open_p = price
        close_p = open_p + body

        high_p = max(open_p, close_p) + abs(body) * rng.uniform(0.05, 0.4)
        low_p = min(open_p, close_p) - abs(body) * rng.uniform(0.05, 0.4)

        volume = rng.uniform(50, 500) * (3 if i % 50 == 25 else 1)

        candles.append(
            Candle(
                timestamp=ts + i * 60,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=volume,
            )
        )

        price = close_p

    return candles


# ==========================================================
# Regression: Displacement contract (the "strength" bug)
# ==========================================================

class TestDisplacementContract(unittest.TestCase):
    """
    Regression coverage for the confirmed crash bug:
    DisplacementScanner used to construct Displacement(...,
    strength=0.0), but Displacement (slots=True) has no
    'strength' field -- it uses score/institutional_score.
    """

    def test_displacement_has_no_strength_field(self):
        # Displacement uses slots=True, so this is a real
        # contract assertion, not just documentation: passing
        # an unknown kwarg raises TypeError.
        with self.assertRaises(TypeError):
            Displacement(
                index=0,
                timestamp=0,
                timeframe="1m",
                direction="BULLISH",
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                body=0.0,
                candle_range=0.0,
                atr_multiple=0.0,
                body_ratio=0.0,
                strength=0.0,  # must fail: not a real field
            )

    def test_displacement_scanner_runs_without_strength_kwarg(self):
        # This is the actual fixed construction path.
        candles = make_candles(n=60)

        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")

        for c in candles:
            context.add_candle(c)

        # A minimal indicator cache stub sufficient for the
        # scanner's ATR check, without running the full
        # IndicatorEngine.
        class _StubCache:
            def latest(self, name):
                return 50.0 if name == "ATR_14" else None

        context.indicators = _StubCache()

        scanner = DisplacementScanner()
        scanner.analyze(context)  # must not raise

        self.assertIsInstance(context.displacement, DisplacementRegistry)
        self.assertGreater(context.displacement.count(), 0)

        # Every produced displacement must have a real score
        # field, and no code path should ever try to read
        # `.strength` off it.
        for d in context.displacement.all():
            self.assertTrue(hasattr(d, "score"))
            self.assertFalse(hasattr(d, "strength"))

    def test_liquidity_sweep_and_trend_alignment_are_computed(self):
        # These were hardcoded to False before the fix. This
        # doesn't assert a specific True/False outcome (that
        # depends on the data), just that the fields exist and
        # that at least the trend_alignment logic is reachable
        # and consistent with context.trend when present.
        candles = make_candles(n=120)

        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")

        for c in candles:
            context.add_candle(c)

        class _StubCache:
            def latest(self, name):
                return 50.0 if name == "ATR_14" else None

        context.indicators = _StubCache()

        from core.trend.trend_state import TrendState
        context.trend = TrendState(direction="BULLISH")

        scanner = DisplacementScanner()
        scanner.analyze(context)

        bullish = [
            d for d in context.displacement.all()
            if d.direction == "BULLISH"
        ]

        self.assertTrue(
            all(d.trend_alignment for d in bullish),
            "Every BULLISH displacement should be marked "
            "trend_alignment=True when context.trend is BULLISH.",
        )


# ==========================================================
# Regression: FVG scanner reading event.score, not
# event.strength
# ==========================================================

class TestFVGScannerContract(unittest.TestCase):

    def test_fvg_scanner_does_not_reference_strength(self):
        candles = make_candles(n=120)

        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")

        for c in candles:
            context.add_candle(c)

        class _StubCache:
            def latest(self, name):
                return 50.0 if name == "ATR_14" else None

        context.indicators = _StubCache()

        displacement_scanner = DisplacementScanner()
        displacement_scanner.analyze(context)

        fvg_scanner = FVGScanner()
        fvg_scanner.analyze(context)  # must not raise AttributeError

        for gap in context.fvgs.all():
            self.assertIsInstance(gap, FairValueGap)
            self.assertGreaterEqual(gap.displacement_strength, 0.0)


# ==========================================================
# Regression: TrendEngine name/field collision
# ==========================================================

class TestTrendEngineCollision(unittest.TestCase):
    """
    core.market_structure.swing_trend_engine.
    SwingStructureTrendEngine (formerly named TrendEngine,
    same as the canonical core.trend.trend_engine.TrendEngine)
    must never write to context.trend -- only context.swing_trend.
    """

    def test_swing_structure_trend_engine_does_not_touch_context_trend(self):
        context = PipelineContext()
        context.trend = "SENTINEL"  # canonical trend must survive untouched

        registry = SwingRegistry()

        engine = SwingStructureTrendEngine()
        context.swings = registry
        engine.analyze(context)

        self.assertEqual(
            context.trend,
            "SENTINEL",
            "SwingStructureTrendEngine must not overwrite context.trend.",
        )


# ==========================================================
# Regression: IndexedRegistry vs BaseRegistry semantics
# ==========================================================

class TestIndexedRegistrySemantics(unittest.TestCase):
    """
    IndexedRegistry.remove() takes an id (dict-keyed), unlike
    BaseRegistry.remove() which takes the object itself
    (list-keyed). SwingRegistry depends on id-based removal
    for swing replacement. This test locks that contract in.
    """

    def test_remove_by_id(self):
        registry = IndexedRegistry()

        swing = Swing(
            id="swing-1",
            index=0,
            timestamp=0,
            timeframe="1m",
            kind="HIGH",
            price=100.0,
        )

        registry.add(swing)
        self.assertIsNotNone(registry.get("swing-1"))

        registry.remove("swing-1")
        self.assertIsNone(registry.get("swing-1"))


# ==========================================================
# End-to-end pipeline smoke test
# ==========================================================

class TestFullPipelineSmoke(unittest.TestCase):
    """
    Runs the entire registered InstitutionalPipeline over a
    synthetic candle feed. This is the test that would have
    caught the main.py double-registration bug (a second,
    unconfigured IndicatorEngine silently zeroing out
    context.indicators every candle) if it had existed
    beforehand: it asserts the pipeline actually produces
    non-zero displacement/FVG/order-block output, not just
    that it runs without raising.
    """

    def test_pipeline_runs_and_produces_signal(self):
        InstitutionalPipeline.DEBUG = False

        candles = make_candles(n=400)

        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")

        pipeline = InstitutionalPipeline(context)

        for c in candles:
            context.add_candle(c)
            pipeline.process()  # must not raise on any candle

        self.assertIsNotNone(context.indicators)
        self.assertIsNotNone(context.indicators.latest("ATR_14"))
        self.assertIsNotNone(context.indicators.latest("EMA_20"))

        self.assertGreater(context.displacement.count(), 0)
        self.assertGreater(
            len(context.displacement.strong()),
            0,
            "Expected at least one strong displacement in 400 "
            "synthetic candles with periodic 2% impulse bars. "
            "Zero here is the exact symptom the main.py "
            "double-registration bug used to cause.",
        )


# ==========================================================
# Regression: WARMUP vs RANGE/DEAD misclassification
# ==========================================================

class TestWarmupClassification(unittest.TestCase):
    """
    TrendState used to default direction/regime to "RANGE",
    and RegimeEngine's composite score naturally sits near 0
    during warmup (every sub-score defaults to 0), which fell
    through to the "DEAD" bucket. Neither is a real market
    observation -- both are "we don't have enough history yet".
    """

    def test_trend_state_defaults_to_warmup_not_range(self):
        from core.trend.trend_state import TrendState
        state = TrendState()
        self.assertEqual(state.direction, "WARMUP")
        self.assertEqual(state.regime, "WARMUP")

    def test_trend_engine_reports_warmup_with_insufficient_history(self):
        from core.trend.trend_engine import TrendEngine
        from core.indicators.indicator_cache import IndicatorCache

        engine = TrendEngine()
        cache = IndicatorCache()  # empty: no EMAs yet

        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        context.add_candle(make_candles(n=1)[0])
        context.indicators = cache

        state = engine.analyze(context)

        self.assertEqual(state.direction, "WARMUP")
        self.assertNotEqual(
            state.direction,
            "RANGE",
            "Insufficient history must not be reported as RANGE.",
        )

    def test_regime_engine_does_not_report_dead_during_warmup(self):
        from core.regime.regime_engine import RegimeEngine
        from core.trend.trend_state import TrendState

        engine = RegimeEngine()

        context = PipelineContext()
        context.trend = TrendState()  # default: WARMUP
        context.market_structure = None
        context.indicators = None
        context.displacement = None
        context.fvgs = None
        context.order_blocks = None
        context.breakers = None
        context.mitigations = None

        state = engine.analyze(context)

        self.assertEqual(state.regime, "WARMUP")
        self.assertNotEqual(
            state.regime,
            "DEAD",
            "Insufficient history must not be reported as DEAD.",
        )


# ==========================================================
# Regression: ExecutionEngine -> context.execution_signal
# ==========================================================

class TestExecutionEngineContract(unittest.TestCase):
    """
    ExecutionEngine used to write to context.execution_signal,
    a field PipelineContext (slots=True) never declared --
    an AttributeError on the exact path where a real trade
    signal is about to be produced. backtesting/backtester.py
    already reads this field via getattr(context,
    "execution_signal", None), so the fix declares the field
    rather than renaming the write target.
    """

    def test_pipeline_context_declares_execution_signal(self):
        context = PipelineContext()
        # Must not raise AttributeError (slots=True would
        # reject undeclared attributes).
        context.execution_signal = "sentinel"
        self.assertEqual(context.execution_signal, "sentinel")


if __name__ == "__main__":
    unittest.main()
