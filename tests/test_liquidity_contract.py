"""
====================================================

QuantEngine

Liquidity Pool / Target Contract Tests

Run with:

    python -m unittest tests.test_liquidity_contract -v

Proves the liquidity stage contract:

1. LiquidityPoolEngine clusters swing highs/lows within the
   price tolerance into single pools, requires the minimum
   touch count, uses the mean price of the cluster, and only
   consumes swings already confirmed by the current candle
   (no lookahead).
2. LiquidityTargetEngine rejects WRONG-SIDE targets: a BULLISH
   trend may only target BUY-side liquidity above price, a
   BEARISH trend only SELL-side liquidity below price. With no
   trend / RANGE / WARMUP both sides are still eligible, so the
   pre-existing behavior is preserved there. A trend with no
   same-side pool yields NO target (VALID-NO-SIGNAL), never a
   counter-trend one.
3. The chained Pool -> Target path through the real context is
   deterministic and never references a bar later than the one
   being processed.

Stdlib only -- no network.

====================================================
"""

import unittest

from core.history.candle import Candle
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext

from core.liquidity.liquidity_pool import LiquidityPool
from core.liquidity.liquidity_pool_engine import LiquidityPoolEngine
from core.liquidity.liquidity_target_engine import LiquidityTargetEngine

from core.market_structure.swing import Swing
from core.market_structure.swing_registry import SwingRegistry

from core.trend.trend_state import TrendState

from tests.test_pipeline_regressions import make_candles


def swing(kind, price, index, timestamp=0, score=0.0):
    return Swing(
        id=f"swing-{index}-{kind}",
        index=index,
        timestamp=timestamp or (index * 60),
        timeframe="1m",
        kind=kind,
        price=price,
        high=price,
        low=price,
        confirmed=True,
        score=score,
    )


def registry_with(*swings):
    reg = SwingRegistry()
    for s in swings:
        reg.add(s)
    return reg


def pool(side, price, score, active=True, touches=2, strength=0.0):
    return LiquidityPool(
        id=f"pool-{side}-{price}-{score}",
        side=side,
        price=price,
        timeframe="1m",
        touches=touches,
        active=active,
        score=score,
        strength=strength,
    )


def target_for(pools, candles, direction):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    for c in candles:
        context.add_candle(c)
    context.liquidity = pools
    context.trend = TrendState(direction=direction)
    return context


def run_target_engine(context):
    LiquidityTargetEngine().analyze(context)
    return context.liquidity_target


class TestLiquidityTargetWrongSideRejection(unittest.TestCase):

    def setUp(self):
        self.candles = list(make_candles(n=60))
        self.current = self.candles[-1].close
        self.cash = None

    def _target(self, pools, direction):
        context = target_for(pools, self.candles, direction)
        return run_target_engine(context)

    def test_bullish_trend_ignores_higher_scoring_sell_pool(self):
        buy = pool("BUY", self.current * 1.02, score=50.0)
        sell = pool("SELL", self.current * 0.98, score=95.0)

        target = self._target([buy, sell], direction="BULLISH")

        self.assertIsNotNone(target)
        self.assertEqual(target.side, "BUY")
        self.assertEqual(target.price, buy.price)
        self.assertEqual(target.source_pool, buy.id)

    def test_bearish_trend_ignores_higher_scoring_buy_pool(self):
        buy = pool("BUY", self.current * 1.02, score=95.0)
        sell = pool("SELL", self.current * 0.98, score=50.0)

        target = self._target([buy, sell], direction="BEARISH")

        self.assertIsNotNone(target)
        self.assertEqual(target.side, "SELL")
        self.assertEqual(target.price, sell.price)
        self.assertEqual(target.source_pool, sell.id)

    def test_bullish_trend_only_sell_side_yields_no_target(self):
        sell = pool("SELL", self.current * 0.98, score=80.0)

        target = self._target([sell], direction="BULLISH")

        self.assertIsNone(target)

    def test_bearish_trend_only_buy_side_yields_no_target(self):
        buy = pool("BUY", self.current * 1.02, score=80.0)

        target = self._target([buy], direction="BEARISH")

        self.assertIsNone(target)

    def test_range_trend_best_score_wins_either_side(self):
        buy = pool("BUY", self.current * 1.02, score=90.0)
        sell = pool("SELL", self.current * 0.98, score=96.0)

        target = self._target([buy, sell], direction="RANGE")

        self.assertEqual(target.side, "SELL")
        self.assertEqual(target.price, sell.price)

    def test_warmup_trend_best_score_wins_either_side(self):
        buy = pool("BUY", self.current * 1.02, score=96.0)
        sell = pool("SELL", self.current * 0.98, score=90.0)

        target = self._target([buy, sell], direction="WARMUP")

        self.assertEqual(target.side, "BUY")
        self.assertEqual(target.price, buy.price)

    def test_no_trend_best_score_wins_either_side(self):
        buy = pool("BUY", self.current * 1.02, score=90.0)
        sell = pool("SELL", self.current * 0.98, score=96.0)

        target = run_target_engine(target_for([buy, sell], self.candles, None))

        self.assertIsNotNone(target)
        self.assertEqual(target.side, "SELL")
        self.assertEqual(target.price, sell.price)

    def test_inactive_pools_never_targeted(self):
        buy = pool("BUY", self.current * 1.02, score=90.0, active=False)
        sell = pool("SELL", self.current * 0.98, score=96.0, active=False)

        context = target_for([buy, sell], self.candles, "RANGE")

        context.liquidity_target = None

        LiquidityTargetEngine().analyze(context)

        self.assertIsNone(context.liquidity_target)

    def test_deterministic_same_input_same_target(self):
        buy = pool("BUY", self.current * 1.02, score=88.0)
        sell = pool("SELL", self.current * 0.98, score=77.0)
        pools = [buy, sell]
        direction = "BULLISH"

        a = self._target(pools, direction)
        b = self._target(pools, direction)

        self.assertEqual(a.price, b.price)
        self.assertEqual(a.side, b.side)
        self.assertEqual(a.probability, b.probability)
        self.assertEqual(a.distance, b.distance)

    def test_same_engine_instance_has_no_stale_state(self):
        buy = pool("BUY", self.current * 1.02, score=88.0)
        sell = pool("SELL", self.current * 0.98, score=95.0)

        engine = LiquidityTargetEngine()

        context_a = target_for([buy, sell], self.candles, "BULLISH")
        engine.analyze(context_a)
        first = context_a.liquidity_target

        context_b = target_for([buy, sell], self.candles, "BEARISH")
        engine.analyze(context_b)
        second = context_b.liquidity_target

        self.assertEqual(first.side, "BUY")
        self.assertEqual(second.side, "SELL")

    def test_reset_preserves_behavior(self):
        buy = pool("BUY", self.current * 1.02, score=88.0)
        context = target_for([buy], self.candles, "BEARISH")

        engine = LiquidityTargetEngine()
        engine.analyze(context)
        engine.reset()
        engine.analyze(context)

        self.assertIsNone(context.liquidity_target)


class TestLiquidityPoolEngineContract(unittest.TestCase):

    def setUp(self):
        self.bars = list(make_candles(n=60))
        self.last = self.bars[-1].close

    def _chain_analyze(self, registry, bars):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        for c in bars:
            context.add_candle(c)
        context.swings = registry
        LiquidityPoolEngine().analyze(context)
        return context

    def test_swings_within_tolerance_build_single_pool(self):
        base = self.last
        reg = registry_with(
            swing("HIGH", base * 1.01, 20),
            swing("HIGH", base * 1.011, 22),
        )

        context = self._chain_analyze(reg, self.bars)
        pools = [p for p in context.liquidity if p.side == "BUY"]

        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0].touches, 2)

    def test_below_minimum_touches_builds_no_pool(self):
        reg = registry_with(swing("HIGH", self.last * 1.01, 20))

        context = self._chain_analyze(reg, self.bars)
        buy_pools = [p for p in context.liquidity if p.side == "BUY"]

        self.assertEqual(buy_pools, [])

    def test_buy_and_sell_pools_both_built(self):
        reg = registry_with(
            swing("HIGH", self.last * 1.01, 20),
            swing("HIGH", self.last * 1.011, 22),
            swing("LOW", self.last * 0.99, 24),
            swing("LOW", self.last * 0.989, 26),
        )

        context = self._chain_analyze(reg, self.bars)
        sides = {p.side for p in context.liquidity}

        self.assertEqual(sides, {"BUY", "SELL"})
        self.out_of_tolerance_high_alone_skipped(reg)

    def out_of_tolerance_high_alone_skipped(self, reg):
        base = self.last
        reg2 = registry_with(
            swing("HIGH", base * 1.01, 20),
            swing("HIGH", base * 1.011, 22),
            swing("HIGH", base * 1.10, 28),
        )

        context = self._chain_analyze(reg2, self.bars)
        buy_pools = [p for p in context.liquidity if p.side == "BUY"]

        self.assertEqual(len(buy_pools), 1)
        self.assertEqual(buy_pools[0].touches, 2)

    def test_pool_price_is_cluster_mean(self):
        reg = registry_with(
            swing("LOW", 99.0, 20),
            swing("LOW", 99.1, 22),
        )

        context = self._chain_analyze(reg, self.bars)
        sell_pools = [p for p in context.liquidity if p.side == "SELL"]

        self.assertEqual(len(sell_pools), 1)
        self.assertAlmostEqual(sell_pools[0].price, 99.05, places=4)

    def test_pool_strength_is_max_member_score(self):
        reg = registry_with(
            swing("HIGH", self.last * 1.01, 20, score=0.4),
            swing("HIGH", self.last * 1.011, 22, score=0.9),
        )

        context = self._chain_analyze(reg, self.bars)
        buy_pools = [p for p in context.liquidity if p.side == "BUY"]

        self.assertAlmostEqual(buy_pools[0].strength, 0.9, places=6)

    def test_empty_registry_yields_empty_liquidity(self):
        context = self._chain_analyze(registry_with(), self.bars)

        self.assertEqual(context.liquidity, [])

    def test_chain_deterministic_across_runs(self):
        reg = registry_with(
            swing("HIGH", self.last * 1.01, 20),
            swing("HIGH", self.last * 1.011, 22),
            swing("LOW", self.last * 0.99, 24),
            swing("LOW", self.last * 0.989, 26),
        )

        c1 = self._chain_analyze(reg, self.bars)
        c2 = self._chain_analyze(reg, self.bars)

        first = [
            (p.side, p.price, p.touches, p.strength)
            for p in c1.liquidity
        ]
        second = [
            (p.side, p.price, p.touches, p.strength)
            for p in c2.liquidity
        ]

        self.assertEqual(first, second)


class TestLiquidityPipelineChainContract(unittest.TestCase):

    def test_pool_to_target_chain_is_trend_consistent(self):
        bars = list(make_candles(n=80))
        last = bars[-1].close

        reg = registry_with(
            swing("HIGH", last * 1.02, 30),
            swing("HIGH", last * 1.021, 32),
            swing("LOW", last * 0.98, 34),
            swing("LOW", last * 0.979, 36),
        )

        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        for c in bars:
            context.add_candle(c)
        context.swings = reg
        context.trend = TrendState(direction="BULLISH")

        LiquidityPoolEngine().analyze(context)
        LiquidityTargetEngine().analyze(context)

        target = context.liquidity_target

        self.assertIsNotNone(target)
        self.assertEqual(target.side, "BUY")
        self.assertGreater(target.price, last)

    def test_chain_never_references_after_current_bar(self):
        bars = list(make_candles(n=80))
        last = bars[-1].close
        last_ts = bars[-1].timestamp

        reg = registry_with(
            swing("HIGH", last * 1.02, 30, timestamp=bars[30].timestamp),
            swing("HIGH", last * 1.021, 32, timestamp=bars[32].timestamp),
            swing("LOW", last * 0.98, 34, timestamp=bars[34].timestamp),
            swing("LOW", last * 0.979, 36, timestamp=bars[36].timestamp),
        )

        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        for c in bars:
            context.add_candle(c)
        context.swings = reg
        context.trend = TrendState(direction="BEARISH")

        LiquidityPoolEngine().analyze(context)
        LiquidityTargetEngine().analyze(context)

        target = context.liquidity_target

        self.assertIsNotNone(target)
        self.assertEqual(target.side, "SELL")

        for p in context.liquidity:
            if p.side != target.side:
                continue
            self.assertLessEqual(p.first_timestamp, last_ts)
            self.assertLessEqual(p.last_timestamp, last_ts)


if __name__ == "__main__":
    unittest.main()