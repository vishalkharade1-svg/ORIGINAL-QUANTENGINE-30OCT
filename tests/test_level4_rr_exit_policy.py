import unittest


class TestLevel4RRPolicy(unittest.TestCase):
    def test_fixed_target_one_to_one_is_allowed(self):
        from core.backtesting.accounting import risk_reward_allowed
        self.assertTrue(risk_reward_allowed(1.0))

    def test_fixed_target_twenty_is_allowed(self):
        from core.backtesting.accounting import risk_reward_allowed
        self.assertTrue(risk_reward_allowed(20.0))

    def test_fixed_target_policy_is_runtime_1_to_20(self):
        from types import SimpleNamespace
        from core.setup.decision_engine import DecisionEngine
        from core.pipeline.pipeline_context import PipelineContext
        from core.market_state import MarketState
        from core.regime.regime_state import RegimeState
        from core.trend.trend_state import TrendState
        from core.setup.setup_candidate import SetupCandidate

        def decide(target):
            c = SetupCandidate(direction="BULLISH", entry=100.0,
                               stop_loss=90.0, take_profit=target,
                               risk_reward=(target - 100.0) / 10.0,
                               confidence=90.0, score=90.0,
                               trend=SimpleNamespace(direction="BULLISH"),
                               regime=SimpleNamespace(score=90.0))
            ctx = PipelineContext(); ctx.market = MarketState(symbol="TEST", timeframe="1m")
            ctx.trade_setups = [c]
            DecisionEngine().analyze(ctx)
            return ctx.decision.all()

        self.assertEqual(len(decide(110.0)), 1)
        self.assertEqual(len(decide(300.0)), 1)
        self.assertEqual(len(decide(301.0)), 0)

    def test_fixed_target_above_twenty_is_rejected(self):
        from core.backtesting.accounting import risk_reward_allowed
        self.assertFalse(risk_reward_allowed(20.000001))

    def test_fixed_target_below_one_is_rejected(self):
        from core.backtesting.accounting import risk_reward_allowed
        self.assertFalse(risk_reward_allowed(0.999999))

    def test_trailing_mode_is_not_admitted_by_fixed_rr_gate(self):
        from core.backtesting.accounting import risk_reward_allowed
        self.assertFalse(risk_reward_allowed(10.0, "TRAILING_STOP"))

    def test_post_cost_max_boundary(self):
        from core.risk.costs import post_cost_rr
        self.assertTrue(post_cost_rr(
            direction="BULLISH", entry=100.0, stop=90.0, target=300.0,
            quantity=1.0, commission=0.0, slippage=0.0
        ).allowed)
        self.assertFalse(post_cost_rr(
            direction="BULLISH", entry=100.0, stop=90.0, target=301.0,
            quantity=1.0, commission=0.0, slippage=0.0
        ).allowed)

    def test_post_cost_trailing_requires_initial_stop_survival(self):
        from core.risk.costs import post_cost_trailing
        ok = post_cost_trailing(direction="BULLISH", entry=100.0, stop=95.0,
                                target=150.0, quantity=1.0, commission=2.0,
                                slippage=0.0, symbol="TEST")
        self.assertTrue(ok.allowed)
        still_valid = post_cost_trailing(direction="BULLISH", entry=100.0, stop=99.0,
                                         target=150.0, quantity=1.0, commission=40.0,
                                         slippage=0.0, symbol="TEST")
        self.assertTrue(still_valid.allowed)
        self.assertGreater(still_valid.risk, ok.risk)

    def test_costed_targetless_trailing_fails_closed(self):
        from core.risk.costs import post_cost_trailing
        verdict = post_cost_trailing(direction="BULLISH", entry=100.0, stop=95.0,
                                     quantity=1.0, commission=2.0, slippage=0.0)
        self.assertFalse(verdict.allowed)
        self.assertIn("cannot be certified", verdict.reason)

    def test_costed_trailing_plan_must_keep_post_cost_target_rr(self):
        from core.risk.costs import post_cost_trailing
        # Gross plan is exactly 1R, but costs erode it below the active 1R
        # floor. A trailing exit must not bypass planned-target qualification.
        verdict = post_cost_trailing(
            direction="BULLISH", entry=100.0, stop=90.0, target=110.0,
            quantity=1.0, commission=2.0, slippage=0.0, symbol="TEST",
        )
        self.assertFalse(verdict.allowed)
        self.assertIn("trailing plan qualification failed", verdict.reason)
        # A viable costed plan reports planned-target R:R, not a fabricated 0R.
        accepted = post_cost_trailing(
            direction="BULLISH", entry=100.0, stop=90.0, target=170.0,
            quantity=2.0, commission=2.0, slippage=0.0, symbol="TEST",
        )
        self.assertTrue(accepted.allowed)
        self.assertGreater(accepted.rr, 1.0)
        self.assertIn("realized trailing R is not guaranteed", accepted.reason)

    def test_trailing_geometry_allows_no_target_but_requires_stop(self):
        from core.backtesting.accounting import directional_geometry_ok
        self.assertTrue(directional_geometry_ok("BULLISH", 100, 95, 0, "TRAILING_STOP"))
        self.assertTrue(directional_geometry_ok("BEARISH", 100, 105, 0, "TRAILING_STOP"))
        self.assertFalse(directional_geometry_ok("BULLISH", 100, 105, 0, "TRAILING_STOP"))


if __name__ == "__main__":
    unittest.main()

class TestLevel4TrailingSimulation(unittest.TestCase):
    def test_trailing_stop_moves_only_in_favorable_direction_and_closes(self):
        from types import SimpleNamespace
        from config import risk_settings
        from core.backtesting.trade_simulator import TradeSimulator
        old = risk_settings.TRAILING_STOP_ENABLED
        risk_settings.TRAILING_STOP_ENABLED = True
        try:
            setup = SimpleNamespace(
                direction="BULLISH", entry=100.0, stop_loss=95.0,
                take_profit=0.0, quantity=1.0, risk_amount=5.0,
                exit_mode="TRAILING_STOP", trailing_activation_r=1.0,
                trailing_distance_r=0.5, score=80.0, confidence=80.0,
                symbol="TEST", setup_id="L4-TRAIL", order_id="",
                entry_mode="", canonical_id="",
            )
            sim = TradeSimulator()
            trade = sim.open_trade(setup, 1)
            self.assertIsNotNone(trade)
            # Close 106 activates the trail: 106 - 2.5 = 103.5.
            sim.update(SimpleNamespace(timestamp=2, open=100, high=108, low=99, close=106))
            self.assertEqual(trade.stop_loss, 103.5)
            # A later favorable close raises the stop; it never loosens.
            sim.update(SimpleNamespace(timestamp=3, open=106, high=110, low=104, close=109))
            self.assertEqual(trade.stop_loss, 106.5)
            # Next candle breaches the active stop.
            sim.update(SimpleNamespace(timestamp=4, open=109, high=110, low=106, close=106.5))
            self.assertEqual(trade.status, "CLOSED")
            self.assertEqual(trade.exit_price, 106.5)
        finally:
            risk_settings.TRAILING_STOP_ENABLED = old

class TestTrailingTargetAndSignalExit(unittest.TestCase):
    def test_trailing_trade_can_book_target(self):
        from types import SimpleNamespace
        from core.backtesting.trade_simulator import TradeSimulator
        setup = SimpleNamespace(
            direction="BULLISH", entry=100.0, stop_loss=95.0,
            take_profit=110.0, quantity=1.0, risk_amount=5.0,
            exit_mode="TRAILING_STOP", trailing_enabled=True,
            trailing_activation_r=1.0, trailing_distance_r=0.5,
            score=80.0, confidence=80.0, symbol="TEST",
            setup_id="TRAIL-TP", order_id="", entry_mode="", canonical_id="",
        )
        sim = TradeSimulator()
        trade = sim.open_trade(setup, 1)
        self.assertIsNotNone(trade)
        sim.update(SimpleNamespace(timestamp=2, open=100, high=111, low=99, close=108))
        self.assertEqual(trade.status, "CLOSED")
        self.assertEqual(trade.exit_price, 110.0)
        self.assertEqual(trade.result, "WIN")

    def test_explicit_signal_exit_books_observed_close(self):
        from types import SimpleNamespace
        from core.backtesting.trade_simulator import TradeSimulator
        setup = SimpleNamespace(
            direction="BULLISH", entry=100.0, stop_loss=95.0,
            take_profit=120.0, quantity=1.0, risk_amount=5.0,
            exit_mode="TRAILING_STOP", trailing_enabled=True,
            trailing_activation_r=1.0, trailing_distance_r=0.5,
            score=80.0, confidence=80.0, symbol="TEST",
            setup_id="TRAIL-EXIT", order_id="", entry_mode="", canonical_id="",
        )
        sim = TradeSimulator()
        trade = sim.open_trade(setup, 1)
        self.assertTrue(sim.request_exit(2, 107.0, "BOOK_PROFIT"))
        self.assertEqual(trade.status, "CLOSED")
        self.assertEqual(trade.exit_price, 107.0)
        self.assertEqual(trade.exit_reason, "BOOK_PROFIT")
