"""
====================================================

QuantEngine

Setup + Decision Contract Tests

Run with:

    python -m unittest tests.test_setup_decision_contract -v

Proves the setup/decision stage contract:

1. TradeSetupBuilder maps order-block entries/stops/targets
   exactly per direction, skips zero-risk and wrong-side-target
   candidates, grants the +3 FVG bonus only for a matching
   direction, attaches trend/regime/liquidity/order-block, and is
   deterministic.
2. DecisionEngine accepts a candidate only when trend matches the
   setup direction and the setup passes regime (>= 70), risk
   reward (>= 6.0, authoritative config MIN_RISK_REWARD) and
   confidence (>= 80, authoritative config MIN_CONFIDENCE) gates; every other
   combination is rejected with the corresponding reason and the
   rejection list. No candidates -> empty decision (VALID-NO-SIGNAL).
3. Execution picks the highest-scoring accepted setup.
4. No stale state: reusing engine instances across cycles never
   leaks a previous cycle's setups/decisions.

Stdlib only -- no network.

====================================================
"""

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext

from core.setup.trade_setup_builder import TradeSetupBuilder
from core.setup.decision_engine import DecisionEngine
from core.setup.setup_candidate import SetupCandidate
from core.setup.trade_setup_registry import TradeSetupRegistry

from core.execution.execution_engine import ExecutionEngine

from core.order_blocks.order_block import OrderBlock
from core.order_blocks.order_block_registry import OrderBlockRegistry

from core.fvg.fair_value_gap import FairValueGap
from core.fvg.fvg_registry import FVGRegistry

from core.liquidity.liquidity_target import LiquidityTarget

from core.trend.trend_state import TrendState
from core.regime.regime_state import RegimeState


def ob(direction, high, low, index=5, ts=1000, score=80.0):
    if direction == "BULLISH":
        open_, close = high, low
    else:
        open_, close = low, high
    block = OrderBlock(
        index=index,
        timestamp=ts,
        timeframe="1m",
        direction=direction,
        open=open_,
        high=high,
        low=low,
        close=close,
        strength=score,
        displacement_strength=score,
    )
    block.score = score
    return block


def target(side, price, index=5):
    return LiquidityTarget(
        side=side,
        price=price,
        timeframe="1m",
        score=90.0,
        probability=90.0,
        distance=abs(price * 0.01),
        strength=0.9,
        reason="test",
        source_pool=f"pool-{index}",
    )


def fvg(direction, index=5):
    return FairValueGap(
        index=index,
        timestamp=1000,
        timeframe="1m",
        direction=direction,
        upper=120.0 if direction == "BULLISH" else 90.0,
        lower=110.0 if direction == "BULLISH" else 80.0,
        size=10.0,
        displacement_strength=80.0,
    )


def ob_registry(*blocks):
    reg = OrderBlockRegistry()
    for b in blocks:
        reg.add(b)
    return reg


def fvg_registry(*fvgs):
    reg = FVGRegistry()
    for g in fvgs:
        reg.add(g)
    return reg


def setup_context(
    trend_direction="BULLISH",
    regime_score=90.0,
    blocks=(ob("BULLISH", 110.0, 100.0),),
    liquidity=None,
    fvgs=None,
):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")

    context.trend = TrendState(direction=trend_direction)

    regime = RegimeState(
        score=regime_score,
        confidence=regime_score,
        grade="A" if regime_score >= 85 else "B",
        regime="TRENDING" if regime_score >= 70 else "RANGE",
    )
    context.regime = regime

    context.order_blocks = ob_registry(*blocks)
    context.liquidity_target = liquidity or target("BUY", 170.0)
    context.fvgs = fvgs or fvg_registry()

    return context


def run_builder(context, engine=None):
    if engine is None:
        engine = TradeSetupBuilder()
    engine.analyze(context)
    return context.trade_setups


def candidate(
    direction="BULLISH",
    entry=100.0,
    stop=95.0,
    take_profit=130.0,
    confidence=85.0,
    score=85.0,
    trend_direction=None,
    regime=None,
):
    c = SetupCandidate(
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=take_profit,
        risk_reward=(take_profit - entry) / (entry - stop),
        confidence=confidence,
        score=score,
    )
    c.trend = TrendState(direction=trend_direction or direction)
    c.regime = regime or RegimeState(
        score=90.0, confidence=90.0, grade="A", regime="TRENDING"
    )
    return c


class TestSetupBuilderContract(unittest.TestCase):

    def setUp(self):
        self.block = ob("BULLISH", 110.0, 100.0, score=80.0)

    def test_bullish_maps_entry_stop_target(self):
        setups = run_builder(setup_context())
        self.assertEqual(len(setups), 1)

        s = setups[0]
        self.assertEqual(s.direction, "BULLISH")
        self.assertEqual(s.entry, 110.0)
        self.assertEqual(s.stop_loss, 100.0)
        self.assertEqual(s.take_profit, 170.0)
        self.assertAlmostEqual(s.risk_reward, 6.0, places=6)
        self.assertEqual(s.score, 80.0)
        self.assertEqual(s.confidence, 80.0)

    def test_bearish_maps_entry_stop_target(self):
        block = ob("BEARISH", 110.0, 100.0, score=80.0)
        setups = run_builder(
            setup_context(
                trend_direction="BEARISH",
                blocks=(block,),
                liquidity=target("SELL", 90.0),
            )
        )
        self.assertEqual(len(setups), 1)

        s = setups[0]
        self.assertEqual(s.direction, "BEARISH")
        self.assertEqual(s.entry, 100.0)
        self.assertEqual(s.stop_loss, 110.0)
        self.assertEqual(s.take_profit, 90.0)
        self.assertAlmostEqual(s.risk_reward, 1.0, places=6)

    def test_target_below_entry_bullish_skipped(self):
        self.assertEqual(
            run_builder(
                setup_context(liquidity=target("BUY", 105.0))
            ),
            [],
        )

    def test_target_above_entry_bearish_skipped(self):
        block = ob("BEARISH", 110.0, 100.0)
        self.assertEqual(
            run_builder(
                setup_context(
                    trend_direction="BEARISH",
                    blocks=(block,),
                    liquidity=target("SELL", 105.0),
                )
            ),
            [],
        )

    def test_zero_risk_block_skipped(self):
        block = ob("BULLISH", 110.0, 110.0)
        self.assertEqual(
            run_builder(setup_context(blocks=(block,))),
            [],
        )

    def test_missing_inputs_yield_no_setups(self):
        for field in ("trend", "regime", "order_blocks", "liquidity_target"):
            with self.subTest(field=field):
                context = setup_context()
                setattr(context, field, None)

                self.assertEqual(run_builder(context), [])

    def test_fvg_bonus_only_matching_direction(self):
        fvgs = fvg_registry(fvg("BULLISH"))
        setups = run_builder(setup_context(fvgs=fvgs))

        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].score, 83.0)
        self.assertIsNotNone(setups[0].fvg)

    def test_no_fvg_bonus_for_wrong_direction(self):
        fvgs = fvg_registry(fvg("BEARISH"))
        setups = run_builder(setup_context(fvgs=fvgs))

        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0].score, 80.0)
        self.assertIsNone(setups[0].fvg)

    def test_attachments(self):
        context = setup_context()
        setups = run_builder(context)

        s = setups[0]
        self.assertIs(s.trend, context.trend)
        self.assertIs(s.regime, context.regime)
        self.assertIs(s.liquidity, context.liquidity_target)
        self.assertIs(s.order_block, context.order_blocks.active()[0])

    def test_deterministic_same_inputs_same_setups(self):
        def snapshot(setups):
            return [
                (
                    s.direction,
                    s.entry,
                    s.stop_loss,
                    s.take_profit,
                    s.risk_reward,
                    s.score,
                )
                for s in setups
            ]

        a = snapshot(run_builder(setup_context()))
        b = snapshot(run_builder(setup_context()))

        self.assertEqual(a, b)


class TestDecisionEngineContract(unittest.TestCase):

    def _decision(self, candidates):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        context.trade_setups = candidates

        engine = DecisionEngine()
        context.decision = None
        engine.analyze(context)

        return engine, context

    def test_accepts_fully_qualified_candidate(self):
        engine, context = self._decision([candidate()])

        self.assertEqual(len(context.decision.all()), 1)
        self.assertEqual(context.decision.all()[0].quality_score, 100)
        self.assertEqual(engine.rejected, [])
        self.assertEqual(engine.acceptance_rate, 100.0)

    def test_rejects_trend_filter(self):
        c = candidate()
        c.trend = TrendState(direction="BEARISH")

        engine, context = self._decision([c])

        self.assertEqual(context.decision.all(), [])
        self.assertEqual(engine.rejected[0].reasons, ["Trend Filter"])

    def test_rejects_missing_trend(self):
        c = candidate()
        c.trend = None

        engine, _ = self._decision([c])

        self.assertEqual(engine.rejected[0].reasons, ["Missing Trend"])

    def test_rejects_missing_regime(self):
        c = candidate()
        c.regime = None

        engine, _ = self._decision([c])

        self.assertEqual(engine.rejected[0].reasons, ["Missing Regime"])

    def test_rejects_weak_market(self):
        c = candidate()
        c.regime = RegimeState(score=60.0, confidence=60.0)

        engine, _ = self._decision([c])

        self.assertEqual(engine.rejected[0].reasons, ["Weak Market"])

    def test_rejects_low_risk_reward(self):
        c = candidate(entry=100.0, stop=90.0, take_profit=105.0)

        engine, _ = self._decision([c])

        self.assertEqual(engine.rejected[0].reasons, ["Risk Reward"])

    def test_rejects_low_confidence(self):
        c = candidate(confidence=60.0, score=60.0)

        engine, _ = self._decision([c])

        self.assertEqual(engine.rejected[0].reasons, ["Confidence"])

    def test_quality_score_bounded(self):
        high = candidate()
        low = candidate(confidence=60.0, score=60.0, take_profit=110.0)
        low.regime = RegimeState(score=60.0, confidence=60.0)

        engine, context = self._decision([high, low])

        accepted = context.decision.all()
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].quality_score, 100)

        for r in engine.rejected:
            self.assertGreaterEqual(r.candidate.quality_score, 0)
            self.assertLessEqual(r.candidate.quality_score, 100)

    def test_no_candidates_is_valid_no_signal(self):
        engine, context = self._decision([])

        self.assertEqual(context.decision.all(), [])
        self.assertEqual(engine.rejected, [])

    def test_no_stale_state_across_cycles(self):
        engine = DecisionEngine()

        c_ok = PipelineContext()
        c_ok.market = MarketState(symbol="TEST", timeframe="1m")
        c_ok.trade_setups = [candidate()]
        engine.analyze(c_ok)
        self.assertEqual(len(c_ok.decision.all()), 1)

        c_bad = PipelineContext()
        c_bad.market = MarketState(symbol="TEST", timeframe="1m")
        bad = candidate()
        bad.trend = None
        c_bad.trade_setups = [bad]
        engine.analyze(c_bad)

        self.assertEqual(c_bad.decision.all(), [])

    def test_decision_is_registry_type(self):
        _, context = self._decision([candidate()])

        self.assertIsInstance(context.decision, TradeSetupRegistry)


class TestSetupDecisionExecutionChain(unittest.TestCase):

    def test_chain_accepts_and_executes_best(self):
        trend = TrendState(direction="BULLISH")
        regime = RegimeState(
            score=90.0, confidence=90.0, grade="A", regime="TRENDING"
        )

        block_a = ob("BULLISH", 110.0, 100.0, index=3, score=80.0)
        block_b = ob("BULLISH", 120.0, 118.0, index=4, score=88.0)

        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        context.trend = trend
        context.regime = regime
        context.order_blocks = ob_registry(block_a, block_b)
        context.liquidity_target = target("BUY", 135.0, index=6)
        context.fvgs = fvg_registry()

        TradeSetupBuilder().analyze(context)
        DecisionEngine().analyze(context)
        ExecutionEngine().analyze(context)

        signal = context.execution_signal

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "BULLISH")
        self.assertEqual(signal.order_block.index, 4)
        self.assertEqual(signal.score, 88.0)

    def test_chain_no_signal_without_acceptance(self):
        trend = TrendState(direction="BEARISH")

        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        context.trend = trend
        context.regime = RegimeState(
            score=90.0, confidence=90.0, grade="A", regime="TRENDING"
        )
        context.order_blocks = ob_registry(ob("BULLISH", 110.0, 100.0))
        context.liquidity_target = target("BUY", 130.0)
        context.fvgs = fvg_registry()

        TradeSetupBuilder().analyze(context)
        DecisionEngine().analyze(context)
        ExecutionEngine().analyze(context)

        self.assertIsNone(context.execution_signal)


if __name__ == "__main__":
    unittest.main()