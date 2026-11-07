"""Phase-13 P0: ONE paper economics authority (deterministic, offline).

Proves the paper split-brain is closed on the canonical path:

  1. configured paper fee is actually consumed by fills;
  2. configured slippage is actually consumed by fills;
  3. zero means explicit zero (EXPLICIT_ZERO, gate-vacuous);
  4. missing means unknown (require_known fails closed);
  5. economics affect the realized result exactly once;
  6. no double subtraction;
  7. LONG/SHORT symmetry;
  8. fills cannot silently diverge from paper_cost_profile();
  9. legacy paper defaults stay explicitly non-evidence.

The authority object is core.risk.costs.paper_cost_profile(); the
entry-point paper path (BrokerEngine dry-run) re-mints fill costs
from it. Stdlib only. No network.
"""

from __future__ import annotations

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.costs import CostSpec
from core.risk.order_intent import OrderIntent


class Candle:
    def __init__(self, high, low, close, timestamp):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


class FakePipeline:
    def __init__(self, script=None):
        self.script = script or {}
        self._idx = 0
        self.reset()

    def reset(self):
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST", timeframe="1m")
        self._idx = 0

    def on_candle(self, event):
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.context.order = self.script.get(self._idx, None)
        self._idx += 1


class FakeExecutor:
    def positions(self):
        return []

    def balance(self):
        return {}


def paper_order(direction="BULLISH", entry=100.0, stop=90.0, tp=170.0,
                quantity=2.0):
    return OrderIntent(
        direction=direction, entry=entry, stop_loss=stop,
        take_profit=tp, quantity=quantity, risk_amount=20.0,
        commission=0.0, slippage=0.0, confidence=85.0, score=85.0,
        symbol="TEST", valid=True,
    )


def dry_run_engine(script, candles, paper_spec):
    import core.live.broker_engine as broker_mod
    from core.live.broker_engine import BrokerEngine

    pipeline = FakePipeline(script)
    engine = BrokerEngine(pipeline, event_bus=None,
                          executor=FakeExecutor())
    original = broker_mod.paper_cost_profile
    broker_mod.paper_cost_profile = lambda: paper_spec
    try:
        for candle in candles:
            engine.run_candle(candle)
    finally:
        broker_mod.paper_cost_profile = original
    return engine


SAFE = dict(high=105.0, low=99.0, close=102.0)
WIN = dict(high=175.0, low=99.0, close=172.0)


class TestPaperEconomicsUnified(unittest.TestCase):
    def test_configured_fee_and_slippage_consumed(self):
        # Authority: 1.0 per-trade + 50bps rate + 20bps slippage.
        # Notional 200 -> commission 1+200*0.005=2.0, slippage
        # 2*200*0.002=0.8. The dry-run fill must carry exactly that.
        spec = CostSpec(per_trade=1.0, rate=0.005, slippage_bps=20.0)
        engine = dry_run_engine(
            {0: paper_order()}, [Candle(**SAFE, timestamp=1)], spec)
        trade = engine.current_trade
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.commission, 2.0, places=9)
        self.assertAlmostEqual(trade.slippage, 0.8, places=9)

    def test_fills_cannot_silently_diverge_from_authority(self):
        # Whatever paper_cost_profile() resolves to, the fill books
        # exactly compute(position_value) — same object semantics.
        import os
        from unittest.mock import patch

        from core.risk.costs import paper_cost_profile

        spec = CostSpec(per_trade=2.5, rate=0.001, slippage_bps=7.0)
        engine = dry_run_engine(
            {0: paper_order()}, [Candle(**SAFE, timestamp=1)], spec)
        trade = engine.current_trade
        self.assertIsNotNone(trade)
        expected_commission, expected_slippage = spec.compute(200.0)
        self.assertAlmostEqual(trade.commission, expected_commission,
                               places=9)
        self.assertAlmostEqual(trade.slippage, expected_slippage,
                               places=9)
        # And the default authority resolves to explicit zero when
        # no operator PAPER_* configuration is present.
        clean = {k: v for k, v in os.environ.items()
                 if not k.startswith("QE_PAPER_")}
        with patch.dict(os.environ, clean, clear=True):
            self.assertEqual(paper_cost_profile(),
                             CostSpec(per_trade=0.0, rate=0.0,
                                      slippage_bps=0.0))

    def test_zero_means_explicit_zero(self):
        from core.risk.costs import EXPLICIT_ZERO, describe

        spec = CostSpec(per_trade=0.0, rate=0.0, slippage_bps=0.0)
        self.assertEqual(describe(spec), EXPLICIT_ZERO)
        engine = dry_run_engine(
            {0: paper_order()}, [Candle(**SAFE, timestamp=1)], spec)
        trade = engine.current_trade
        self.assertIsNotNone(trade)
        self.assertEqual(trade.commission, 0.0)
        self.assertEqual(trade.slippage, 0.0)

    def test_missing_means_unknown(self):
        from core.risk.costs import UNKNOWN, describe, require_known

        self.assertEqual(describe(None), UNKNOWN)
        with self.assertRaises(ValueError):
            require_known(None)

    def test_single_subtraction_and_symmetry(self):
        # LONG gross (170-100)*2=140, SHORT gross (100-30)*2=140;
        # same spec -> same net, subtracted exactly once at close.
        spec = CostSpec(per_trade=1.0, rate=0.0, slippage_bps=0.0)
        long_engine = dry_run_engine(
            {0: paper_order(direction="BULLISH", entry=100.0,
                            stop=90.0, tp=170.0)},
            [Candle(**WIN, timestamp=1)], spec)
        short_engine = dry_run_engine(
            {0: paper_order(direction="BEARISH", entry=100.0,
                            stop=110.0, tp=30.0)},
            [Candle(high=102.0, low=28.0, close=29.0, timestamp=1)],
            spec)
        long_closed = long_engine.simulator.registry.all()
        short_closed = short_engine.simulator.registry.all()
        self.assertEqual(len(long_closed), 1)
        self.assertEqual(len(short_closed), 1)
        # Each: gross 140 - 1.0 commission - 0 slippage = 139.
        self.assertAlmostEqual(long_closed[0].pnl, 139.0, places=6)
        self.assertAlmostEqual(short_closed[0].pnl, 139.0, places=6)

    def test_post_cost_gate_applies_to_paper_fills(self):
        # Costs that erode post-cost RR below the configured runtime
        # minimum refuse the fixed-target paper fill.
        spec = CostSpec(per_trade=30.0, rate=0.0, slippage_bps=0.0)
        from core.risk.trading_policy import trading_policy_manager, TradingPolicy
        manager = trading_policy_manager()
        saved = manager._global
        manager._global = TradingPolicy(
            min_rr=saved.min_rr, max_rr=saved.max_rr, trailing_enabled=False,
            trailing_activation_r=saved.trailing_activation_r,
            trailing_distance_r=saved.trailing_distance_r,
            auto_exit_on_opposite_signal=saved.auto_exit_on_opposite_signal,
        )
        try:
            engine = dry_run_engine(
                {0: paper_order(entry=100.0, stop=90.0, tp=112.0,
                                quantity=10.0)},
                [Candle(**SAFE, timestamp=1)], spec)
        finally:
            manager._global = saved
        self.assertIsNone(engine.current_trade)


    def test_feed_paper_engine_consumes_paper_cost_profile(self):
        from unittest.mock import patch
        from core.paper_trading.paper_trading_engine import PaperTradingEngine

        spec = CostSpec(per_trade=1.0, rate=0.005, slippage_bps=20.0)
        pipeline = FakePipeline({0: paper_order()})
        engine = PaperTradingEngine(pipeline, event_bus=None)
        with patch("core.paper_trading.paper_trading_engine.paper_cost_profile",
                   return_value=spec):
            engine.run_candle(Candle(**SAFE, timestamp=1))
        trade = engine.current_trade
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.commission, 2.0, places=9)
        self.assertAlmostEqual(trade.slippage, 0.8, places=9)

    def test_feed_paper_engine_costs_can_block_post_cost_rr(self):
        from unittest.mock import patch
        from core.paper_trading.paper_trading_engine import PaperTradingEngine

        spec = CostSpec(per_trade=30.0, rate=0.0, slippage_bps=0.0)
        pipeline = FakePipeline({0: paper_order(entry=100.0, stop=90.0, tp=112.0, quantity=10.0)})
        engine = PaperTradingEngine(pipeline, event_bus=None)
        from core.risk.trading_policy import trading_policy_manager, TradingPolicy
        manager = trading_policy_manager()
        saved = manager._global
        manager._global = TradingPolicy(
            min_rr=saved.min_rr, max_rr=saved.max_rr, trailing_enabled=False,
            trailing_activation_r=saved.trailing_activation_r,
            trailing_distance_r=saved.trailing_distance_r,
            auto_exit_on_opposite_signal=saved.auto_exit_on_opposite_signal,
        )
        try:
            with patch("core.paper_trading.paper_trading_engine.paper_cost_profile",
                       return_value=spec):
                engine.run_candle(Candle(**SAFE, timestamp=1))
        finally:
            manager._global = saved
        self.assertIsNone(engine.current_trade)

    def test_legacy_paper_defaults_are_explicitly_non_evidence(self):
        # The default paper authority is explicit-zero and the
        # readiness authority refuses to certify it as evidence.
        # This documents the residual limitation honestly: default
        # paper is logic-validation only, never performance
        # evidence.
        from core.paper_trading.readiness import assess_paper_readiness

        readiness = assess_paper_readiness()
        self.assertFalse(readiness.ready)
        self.assertEqual(readiness.status, "NOT_EVIDENCE_READY")


if __name__ == "__main__":
    unittest.main()
