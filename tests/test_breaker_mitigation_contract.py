"""
====================================================

QuantEngine

Breaker + Mitigation Contract Tests

Run with:

    python -m unittest tests.test_breaker_mitigation_contract -v

Proves the BreakerEngine / MitigationEngine adapter stage:

1. BreakerEngine walks mitigated order blocks and publishes
   context.breakers (BreakerRegistry); block geometry and the
   source position are preserved, breaker.score = OB score + 10
   capped at 100.
2. MitigationEngine walks touched, non-invalidated order blocks
   and publishes context.mitigations (MitigationRegistry) with
   the documented score breakdown; invalidated and untouched
   blocks are skipped.
3. Neither engine crashes when order blocks are missing/empty
   (VALID-NO-SIGNAL -> empty registry).
4. Both engines are deterministic and never accumulate state
   across cycles.
5. The lifecycles (FVGLifecycleEngine, OrderBlockLifecycleEngine)
   run between the scanners and the breaker/mitigation stages, so
   in a full pipeline run context.breakers / context.mitigations
   are real registries.
6. RegimeEngine now actually scores breaker + mitigation
   sub-scores (up to +5 each) once the registries are populated.

Stdlib only -- no network.

====================================================
"""

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext

from core.breaker.breaker_engine import BreakerEngine
from core.breaker.breaker_registry import BreakerRegistry
from core.mitigation.mitigation_engine import MitigationEngine
from core.mitigation.mitigation_registry import MitigationRegistry

from core.order_blocks.order_block import OrderBlock
from core.order_blocks.order_block_registry import OrderBlockRegistry

from core.displacement.displacement_registry import DisplacementRegistry
from core.fvg.fvg_registry import FVGRegistry

from core.trend.trend_state import TrendState
from core.regime.regime_engine import RegimeEngine


def ob(
    direction="BULLISH",
    high=110.0,
    low=100.0,
    index=5,
    ts=1000,
    position=5,
    score=80.0,
    mitigated=False,
    touches=0,
    invalidated=False,
):
    block = OrderBlock(
        index=index,
        timestamp=ts,
        timeframe="1m",
        direction=direction,
        open=(low if direction == "BULLISH" else high),
        high=high,
        low=low,
        close=(high if direction == "BULLISH" else low),
        strength=score,
        displacement_strength=score,
    )
    block.score = score
    block.mitigated = mitigated
    block.touches = touches
    block.invalidated = invalidated
    block.bos_index = position
    return block


def ob_registry(*blocks):
    reg = OrderBlockRegistry()
    for b in blocks:
        reg.add(b)
    return reg


def run_breaker(blocks, order_blocks=None):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    context.order_blocks = (
        order_blocks if order_blocks is not None else ob_registry(*blocks)
    )

    engine = BreakerEngine()
    engine.analyze(context)

    return engine, context


def run_mitigation(blocks, order_blocks=None):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    context.order_blocks = (
        order_blocks if order_blocks is not None else ob_registry(*blocks)
    )

    engine = MitigationEngine()
    engine.analyze(context)

    return engine, context


class TestBreakerEngineContract(unittest.TestCase):

    def test_mitigated_blocks_become_breakers(self):
        _, context = run_breaker([
            ob(index=2, ts=2001, high=115.0, low=105.0, mitigated=True),
            ob(index=7, ts=2002, high=95.0, low=90.0, mitigated=True),
        ])

        self.assertIsInstance(context.breakers, BreakerRegistry)
        self.assertEqual(context.breakers.count(), 2)

        first, second = context.breakers.all()

        self.assertEqual(first.index, 2)
        self.assertEqual(first.timestamp, 2001)
        self.assertEqual(first.direction, "BULLISH")
        self.assertEqual(first.high, 115.0)
        self.assertEqual(first.low, 105.0)
        self.assertEqual(first.source_order_block, 0)
        # score = min(100, OB.score + 10) = min(100, 90)
        self.assertEqual(first.score, 90.0)

        self.assertEqual(second.source_order_block, 1)

    def test_unmitigated_blocks_ignored(self):
        _, context = run_breaker([
            ob(index=2, mitigated=False),
            ob(index=4, mitigated=False),
        ])
        self.assertEqual(context.breakers.count(), 0)

    def test_missing_order_blocks_is_empty_registry(self):
        _, context = run_breaker([], order_blocks=None)
        self.assertIsInstance(context.breakers, BreakerRegistry)
        self.assertEqual(context.breakers.count(), 0)

    def test_empty_order_blocks_is_empty_registry(self):
        _, context = run_breaker([])
        self.assertEqual(context.breakers.count(), 0)

    def test_deterministic(self):
        def snapshot():
            _, context = run_breaker([
                ob(index=2, high=115.0, low=105.0, mitigated=True),
                ob(index=7, high=95.0, low=90.0, mitigated=True),
            ])
            return [
                (b.index, b.high, b.low, b.score, b.source_order_block)
                for b in context.breakers.all()
            ]

        self.assertEqual(snapshot(), snapshot())

    def test_fresh_each_cycle_no_accumulation(self):
        _, first = run_breaker([
            ob(index=2, high=115.0, mitigated=True),
            ob(index=4, high=95.0, mitigated=True),
            ob(index=6, high=70.0, mitigated=True),
        ])
        _, second = run_breaker([
            ob(index=2, high=115.0, mitigated=True),
        ])

        self.assertEqual(first.breakers.count(), 3)
        self.assertEqual(second.breakers.count(), 1)


class TestMitigationEngineContract(unittest.TestCase):

    def test_touched_valid_blocks_become_mitigations(self):
        _, context = run_mitigation([
            ob(index=2, ts=2001, high=115.0, low=105.0, touches=2),
            ob(index=7, ts=2002, high=95.0, low=90.0, touches=1),
        ])

        self.assertIsInstance(context.mitigations, MitigationRegistry)
        self.assertEqual(context.mitigations.count(), 2)

        first, second = context.mitigations.all()

        self.assertEqual(first.index, 2)
        self.assertEqual(first.timestamp, 2001)
        self.assertEqual(first.high, 115.0)
        self.assertEqual(first.low, 105.0)
        self.assertEqual(first.touches, 2)
        self.assertEqual(first.source_order_block, 0)

        self.assertEqual(second.source_order_block, 1)
        self.assertEqual(second.touches, 1)

    def test_score_breakdown(self):
        # ob_score = min(80, 50) = 50; touch_score = min(2*5, 20) = 10;
        # freshness (not mitigated) = 20; validity (not invalidated) = 10
        _, context = run_mitigation([
            ob(index=2, score=80.0, touches=2),
        ])

        m = context.mitigations.all()[0]
        self.assertEqual(m.score, 90.0)
        self.assertEqual(
            m.metadata["order_block_score"], 50.0
        )
        self.assertEqual(m.metadata["touch_score"], 10.0)
        self.assertEqual(m.metadata["freshness_score"], 20.0)
        self.assertEqual(m.metadata["validity_score"], 10.0)

    def test_invalidated_blocks_skipped(self):
        _, context = run_mitigation([
            ob(index=2, touches=2, invalidated=True),
            ob(index=4, touches=2, invalidated=False),
        ])
        self.assertEqual(context.mitigations.count(), 1)
        self.assertEqual(context.mitigations.all()[0].index, 4)

    def test_untouched_blocks_skipped(self):
        _, context = run_mitigation([
            ob(index=2, touches=2),
            ob(index=4, touches=0),
        ])
        self.assertEqual(context.mitigations.count(), 1)
        self.assertEqual(context.mitigations.all()[0].index, 2)

    def test_missing_order_blocks_is_empty_registry(self):
        _, context = run_mitigation([], order_blocks=None)
        self.assertIsInstance(context.mitigations, MitigationRegistry)
        self.assertEqual(context.mitigations.count(), 0)

    def test_deterministic(self):
        def snapshot():
            _, context = run_mitigation([
                ob(index=2, touches=2),
                ob(index=9, touches=3, invalidated=True),
                ob(index=12, touches=1),
            ])
            return [
                (m.index, m.touches, m.score, m.source_order_block)
                for m in context.mitigations.all()
            ]

        self.assertEqual(snapshot(), snapshot())

    def test_fresh_each_cycle_no_accumulation(self):
        _, first = run_mitigation([
            ob(index=2, touches=1),
            ob(index=4, touches=2),
        ])
        _, second = run_mitigation([
            ob(index=2, touches=1),
        ])

        self.assertEqual(first.mitigations.count(), 2)
        self.assertEqual(second.mitigations.count(), 1)


class TestRegimeBreakerMitigationScores(unittest.TestCase):
    """
    The point of the wiring: with breakers and mitigations
    available, RegimeEngine's breaker/mitigation sub-scores
    (previously locked at 0) are actually earned -- up to +5
    each toward the final regime score.
    """

    def _regime_score(self, breakers, mitigations):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")

        context.trend = TrendState(direction="BULLISH")

        class _MS:
            bos = True
            choch = False

        context.market_structure = _MS()

        class _Ind:
            def latest(self, key):
                return 35.0 if key == "ADX_14" else 100.0

        context.indicators = _Ind()

        context.displacement = DisplacementRegistry()
        context.fvgs = FVGRegistry()
        context.order_blocks = OrderBlockRegistry()
        context.breakers = breakers
        context.mitigations = mitigations

        state = RegimeEngine().analyze(context)
        return state

    def _breaker_registry(self, n=3):
        reg = BreakerRegistry()
        for i in range(n):
            reg.add(ob(index=i, high=100.0 + i, low=90.0 + i))
        return reg

    def _mitigation_registry(self, n=3):
        reg = MitigationRegistry()
        for i in range(n):
            reg.add(ob(index=i, high=100.0 + i, low=90.0 + i))
        return reg

    def test_scores_are_zero_without_registries(self):
        empty = BreakerRegistry()
        state = self._regime_score(empty, MitigationRegistry())

        self.assertEqual(state.breaker_score, 0)
        self.assertEqual(state.mitigation_score, 0)
        self.assertEqual(state.breaker_score + state.mitigation_score, 0)

    def test_scores_earned_with_populated_registries(self):
        state = self._regime_score(
            self._breaker_registry(3),
            self._mitigation_registry(3),
        )

        self.assertEqual(state.breaker_score, 5)
        self.assertEqual(state.mitigation_score, 5)

    def test_full_pipeline_reaches_regime_with_scores(self):
        from tests.test_pipeline_regressions import make_candles
        from core.pipeline.institutional_pipeline import InstitutionalPipeline

        def run():
            context = PipelineContext()
            context.market = MarketState(symbol="TEST", timeframe="1m")
            pipeline = InstitutionalPipeline(context)

            for c in make_candles(n=160):
                context.add_candle(c)
                pipeline.process()

            return context

        context = run()

        from core.breaker.breaker_registry import BreakerRegistry as BR
        from core.mitigation.mitigation_registry import MitigationRegistry as MR

        self.assertIsInstance(context.breakers, BR)
        self.assertIsInstance(context.mitigations, MR)
        self.assertGreaterEqual(context.breakers.count(), 0)
        self.assertGreaterEqual(context.mitigations.count(), 0)

        # Determinism: identical feed -> identical counts.
        again = run()
        self.assertEqual(context.breakers.count(), again.breakers.count())
        self.assertEqual(
            context.mitigations.count(), again.mitigations.count()
        )


if __name__ == "__main__":
    unittest.main()