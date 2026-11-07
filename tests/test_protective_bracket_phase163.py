"""Unit tests for ProtectiveBracketIntent and TrailingStopSimulator (Phase 163)."""

from __future__ import annotations

import unittest
from core.execution.protective_bracket import (
    BracketValidationError,
    OrderSide,
    ProtectiveBracketIntent,
    TrailingStopSimulator,
)


class TestProtectiveBracket(unittest.TestCase):
    def test_valid_long_bracket_geometry_and_rr(self):
        bracket = ProtectiveBracketIntent(
            symbol="BTCUSD",
            side=OrderSide.BUY,
            entry_price=80000.0,
            stop_loss_price=79000.0,      # Risk = 1000
            take_profit_price=83000.0,    # Reward = 3000 -> 3:1 R:R
            quantity=1.0,
            client_order_id="bracket_long_001",
        )
        self.assertEqual(bracket.risk_distance, 1000.0)
        self.assertEqual(bracket.reward_distance, 3000.0)
        self.assertAlmostEqual(bracket.risk_reward_ratio, 3.0)

    def test_valid_short_bracket_geometry_and_rr(self):
        bracket = ProtectiveBracketIntent(
            symbol="ETHUSD",
            side=OrderSide.SELL,
            entry_price=2500.0,
            stop_loss_price=2550.0,       # Risk = 50
            take_profit_price=2350.0,     # Reward = 150 -> 3:1 R:R
            quantity=2.0,
            client_order_id="bracket_short_001",
        )
        self.assertEqual(bracket.risk_distance, 50.0)
        self.assertEqual(bracket.reward_distance, 150.0)
        self.assertAlmostEqual(bracket.risk_reward_ratio, 3.0)

    def test_inverted_stop_loss_rejected_fail_closed(self):
        # Long with stop higher than entry
        with self.assertRaises(BracketValidationError):
            ProtectiveBracketIntent(
                symbol="BTCUSD",
                side=OrderSide.BUY,
                entry_price=80000.0,
                stop_loss_price=80500.0,  # Inverted!
                take_profit_price=82000.0,
                quantity=1.0,
                client_order_id="bad_long_01",
            )

        # Short with stop lower than entry
        with self.assertRaises(BracketValidationError):
            ProtectiveBracketIntent(
                symbol="BTCUSD",
                side=OrderSide.SELL,
                entry_price=80000.0,
                stop_loss_price=79500.0,  # Inverted!
                take_profit_price=77000.0,
                quantity=1.0,
                client_order_id="bad_short_01",
            )

    def test_rr_boundary_enforcement(self):
        # Sub-1:1 R:R rejected (Risk = 1000, Reward = 500 -> 0.5:1)
        with self.assertRaises(BracketValidationError) as cm:
            ProtectiveBracketIntent(
                symbol="BTCUSD",
                side=OrderSide.BUY,
                entry_price=80000.0,
                stop_loss_price=79000.0,
                take_profit_price=80500.0,
                quantity=1.0,
                client_order_id="sub_1r_01",
            )
        self.assertIn("below minimum 1.0R", str(cm.exception))

        # Above 20:1 R:R rejected (Risk = 100, Reward = 2500 -> 25:1)
        with self.assertRaises(BracketValidationError) as cm2:
            ProtectiveBracketIntent(
                symbol="BTCUSD",
                side=OrderSide.BUY,
                entry_price=80000.0,
                stop_loss_price=79900.0,
                take_profit_price=82500.0,
                quantity=1.0,
                client_order_id="above_20r_01",
            )
        self.assertIn("exceeds maximum 20.0R", str(cm2.exception))

    def test_trailing_stop_activation_and_ratchet(self):
        bracket = ProtectiveBracketIntent(
            symbol="BTCUSD",
            side=OrderSide.BUY,
            entry_price=80000.0,
            stop_loss_price=79000.0,  # 1R = 1000
            take_profit_price=83000.0,
            quantity=1.0,
            client_order_id="trail_01",
        )
        sim = TrailingStopSimulator(
            bracket,
            activation_r=1.0,       # Activates at +1000 (81000)
            trailing_distance_r=0.5 # Trails 500 behind high
        )

        # Before activation: stop remains initial stop (79000)
        self.assertEqual(sim.update_price(80500.0), 79000.0)
        self.assertFalse(sim.is_activated)

        # Reaches activation (+1R @ 81000): stop moves to 81000 - 500 = 80500
        stop1 = sim.update_price(81000.0)
        self.assertTrue(sim.is_activated)
        self.assertEqual(stop1, 80500.0)

        # Price advances to 82000: stop ratchets to 82000 - 500 = 81500
        stop2 = sim.update_price(82000.0)
        self.assertEqual(stop2, 81500.0)

        # Price pulls back to 81700: stop MUST NOT move down
        stop3 = sim.update_price(81700.0)
        self.assertEqual(stop3, 81500.0)

    def test_latency_simulation_and_slippage_evaluation(self):
        bracket = ProtectiveBracketIntent(
            symbol="BTCUSD",
            side=OrderSide.BUY,
            entry_price=80000.0,
            stop_loss_price=79000.0,
            take_profit_price=83000.0,
            quantity=1.0,
            client_order_id="latency_01",
        )
        sim = TrailingStopSimulator(bracket)

        # Evaluate stop fill at 0ms latency (0 bps slippage)
        res_0ms = sim.evaluate_stop_fill(79000.0, latency_ms=0)
        self.assertEqual(res_0ms["fill_price"], 79000.0)
        self.assertEqual(res_0ms["slippage_bps"], 0.0)
        self.assertEqual(res_0ms["realized_pnl"], -1000.0)

        # Evaluate stop fill under 250ms latency (2.5 bps slippage)
        res_250ms = sim.evaluate_stop_fill(79000.0, latency_ms=250)
        self.assertLess(res_250ms["fill_price"], 79000.0)
        self.assertEqual(res_250ms["slippage_bps"], 2.5)
        self.assertLess(res_250ms["realized_pnl"], -1000.0)


if __name__ == "__main__":
    unittest.main()
