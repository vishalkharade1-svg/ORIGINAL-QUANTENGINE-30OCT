"""
====================================================

QuantEngine

Regime Engine Contract Tests

Run with:

    python -m unittest tests.test_regime_contract -v

Proves the regime stage contract:

1. Deterministic: identical context inputs -> identical
   RegimeState. A fresh analyze() never leaks a previous cycle's
   state (self.state is recreated every call).
2. Composition: score == sum of trend + structure + momentum +
   volatility + liquidity + displacement + fvg + order block +
   breaker + mitigation sub-scores; confidence == score.
3. Warmup gate: a WARMUP / missing trend short-circuits to
   grade "N/A" / regime "WARMUP" so an empty history is never
   misread as a "DEAD" market.
4. Grade buckets match score (A+ >= 95 ... F < 40).
5. Documented wiring gap: no pipeline stage produces
   context.breakers / context.mitigations, so those two sub-score
   blocks are VALID-NO-SIGNAL (0.0) until a producer is wired,
   never a crash.

Stdlib only -- no network.

====================================================
"""

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline

from core.regime.regime_engine import RegimeEngine
from core.regime.regime_state import RegimeState

from core.trend.trend_state import TrendState

from tests.test_pipeline_regressions import make_candles


class _MS:
    def __init__(self, bos=False, choch=False):
        self.bos = bos
        self.choch = choch
        self.signals = []
        self.last_bos = None
        self.last_structure = None


class _Reg:
    def __init__(self, strong=0, active=0, count=0):
        self._strong = [object() for _ in range(strong)]
        self._active = [object() for _ in range(active)]
        self._count = count

    def strong(self):
        return self._strong

    def active(self):
        return self._active

    def count(self):
        return self._count


class _Ind:
    def __init__(self, adx=None, atr=None):
        self._adx = adx
        self._atr = atr

    def latest(self, name):
        if name == "ADX_14":
            return self._adx
        if name == "ATR_14":
            return self._atr
        return None


def regime_context(
    direction="BULLISH",
    adx=40.0,
    atr=5.0,
    bos=True,
    choch=True,
    strong=6,
    fvg_active=4,
    ob_active=3,
):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")

    context.trend = TrendState(direction=direction)
    context.indicators = _Ind(adx=adx, atr=atr)
    context.market_structure = _MS(bos=bos, choch=choch)
    context.displacement = _Reg(strong=strong)
    context.fvgs = _Reg(active=fvg_active)
    context.order_blocks = _Reg(active=ob_active)
    context.breakers = None
    context.mitigations = None

    return context


def run(context, engine=None):
    if engine is None:
        engine = RegimeEngine()
    engine.analyze(context)
    return context.regime


class TestRegimeContract(unittest.TestCase):

    def test_warmup_gate(self):
        context = regime_context(direction="WARMUP")
        state = run(context)

        self.assertEqual(state.regime, "WARMUP")
        self.assertEqual(state.grade, "N/A")
        self.assertIs(context.regime, state)

    def test_missing_trend_uses_warmup_gate(self):
        context = regime_context(direction="BULLISH")

        context.trend = TrendState()

        state = run(context)

        self.assertEqual(state.regime, "WARMUP")
        self.assertEqual(state.grade, "N/A")

    def test_empty_signals_read_dead(self):
        context = regime_context(
            direction="BULLISH",
            adx=None,
            atr=None,
            bos=False,
            choch=False,
            strong=0,
            fvg_active=0,
            ob_active=0,
        )
        context.market_structure = _MS(bos=False, choch=False)
        context.indicators = _Ind(adx=None, atr=None)

        state = run(context)

        self.assertEqual(state.score, 15.0)
        self.assertEqual(state.grade, "F")
        self.assertEqual(state.regime, "DEAD")

    def test_full_signals_compose_to_score_100(self):
        state = run(regime_context())

        self.assertEqual(state.trend_score, 15.0)
        self.assertEqual(state.structure_score, 15.0)
        self.assertEqual(state.momentum_score, 15.0)
        self.assertEqual(state.volatility_score, 10.0)
        self.assertEqual(state.liquidity_score, 10.0)
        self.assertEqual(state.displacement_score, 15.0)
        self.assertEqual(state.fvg_score, 10.0)
        self.assertEqual(state.order_block_score, 10.0)

        expected = (
            state.trend_score
            + state.structure_score
            + state.momentum_score
            + state.volatility_score
            + state.liquidity_score
            + state.displacement_score
            + state.fvg_score
            + state.order_block_score
            + state.breaker_score
            + state.mitigation_score
        )

        self.assertEqual(state.score, expected)
        self.assertEqual(state.confidence, state.score)
        self.assertEqual(state.grade, "A+")
        self.assertEqual(state.regime, "INSTITUTIONAL_TREND")

    def test_score_is_sum_of_sub_scores_invariant(self):
        for _ in range(5):
            state = run(regime_context())

            total = (
                state.trend_score
                + state.structure_score
                + state.momentum_score
                + state.volatility_score
                + state.liquidity_score
                + state.displacement_score
                + state.fvg_score
                + state.order_block_score
                + state.breaker_score
                + state.mitigation_score
            )

            self.assertEqual(state.score, total)

    def test_publishes_same_state_to_context(self):

        context = regime_context()

        state = run(context)

        self.assertTrue(context.regime is state)

    def test_grade_bucket_thresholds(self):
        cases = [
            (
                dict(adx=10.0, choch=False, strong=0, fvg_active=0, ob_active=0),
                40.0,
                "D",
                "RANGE",
            ),
            (
                dict(adx=10.0, choch=True, strong=0, fvg_active=1, ob_active=0),
                55.0,
                "C",
                "TRANSITION",
            ),
            (
                dict(adx=25.0, choch=False, strong=1, fvg_active=3, ob_active=2),
                70.0,
                "B",
                "TRENDING",
            ),
            (
                dict(adx=35.0, choch=True, strong=0, fvg_active=4, ob_active=3),
                85.0,
                "A",
                "STRONG_TREND",
            ),
        ]

        for params, expected_score, grade, regime_name in cases:
            with self.subTest(expected=expected_score):
                state = run(regime_context(**params))

                self.assertEqual(state.score, expected_score)
                self.assertEqual(state.grade, grade)
                self.assertEqual(state.regime, regime_name)

    def test_breaker_and_mitigation_scores_zero_by_default(self):
        state = run(regime_context())

        self.assertEqual(state.breaker_score, 0.0)
        self.assertEqual(state.mitigation_score, 0.0)

    def test_breaker_provider_would_contribute(self):
        context = regime_context()
        context.breakers = _Reg(count=3)
        context.mitigations = _Reg(count=2)

        state = run(context)

        self.assertEqual(state.breaker_score, 5.0)
        self.assertEqual(state.mitigation_score, 4.0)

    def test_adx_momentum_buckets(self):
        cases = [
            (10.0, 2.0, "WEAK"),
            (20.0, 6.0, "MODERATE"),
            (25.0, 10.0, "STRONG"),
            (35.0, 15.0, "VERY_STRONG"),
        ]

        for adx, score, label in cases:
            with self.subTest(adx=adx):
                context = regime_context(
                    adx=adx,
                    atr=None,
                    bos=False,
                    choch=False,
                    strong=0,
                    fvg_active=0,
                    ob_active=0,
                )
                state = run(context)

                self.assertEqual(state.momentum_score, score)
                self.assertEqual(state.momentum, label)

    def test_range_trend_scores_8(self):
        context = regime_context(
            direction="RANGE",
            adx=None,
            atr=None,
            bos=False,
            choch=False,
            strong=0,
            fvg_active=0,
            ob_active=0,
        )
        state = run(context)

        self.assertEqual(state.trend_score, 8.0)

    def test_deterministic_same_inputs_same_state(self):
        a = run(regime_context())
        b = run(regime_context())

        def snapshot(s):
            return (
                s.score,
                s.confidence,
                s.grade,
                s.regime,
                s.trend_score,
                s.structure_score,
            )

        self.assertEqual(snapshot(a), snapshot(b))

    def test_same_engine_instance_no_stale_state(self):
        engine = RegimeEngine()

        first = run(regime_context(), engine)

        depleted = regime_context(
            adx=None,
            atr=None,
            bos=False,
            choch=False,
            strong=0,
            fvg_active=0,
            ob_active=0,
        )
        second = run(depleted, engine)

        self.assertEqual(first.score, 100.0)
        self.assertEqual(second.score, 15.0)
        self.assertEqual(second.regime, "DEAD")

    def test_reset_restores_fresh_state(self):
        engine = RegimeEngine()
        run(regime_context(), engine)

        engine.reset()

        self.assertIsInstance(engine.state, RegimeState)
        self.assertEqual(engine.state.score, 0.0)
        self.assertEqual(engine.state.regime, "UNKNOWN")


class TestRegimePipelineContract(unittest.TestCase):

    def test_pipeline_publishes_deterministic_regime(self):
        candles = list(make_candles(n=120))

        def run_pipeline():
            context = PipelineContext()
            context.market = MarketState(symbol="TEST", timeframe="1m")
            pipeline = InstitutionalPipeline(context)
            for c in candles:
                context.add_candle(c)
                pipeline.process()
            return context.regime

        a = run_pipeline()
        b = run_pipeline()

        self.assertIsInstance(a, RegimeState)
        self.assertEqual(a.regime, b.regime)
        self.assertEqual(a.grade, b.grade)
        self.assertEqual(a.score, b.score)

        total = (
            a.trend_score
            + a.structure_score
            + a.momentum_score
            + a.volatility_score
            + a.liquidity_score
            + a.displacement_score
            + a.fvg_score
            + a.order_block_score
            + a.breaker_score
            + a.mitigation_score
        )
        self.assertEqual(a.score, total)


if __name__ == "__main__":
    unittest.main()