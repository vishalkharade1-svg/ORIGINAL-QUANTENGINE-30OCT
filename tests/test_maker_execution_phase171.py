"""
Phase 171 Test Suite: Maker Execution, Friction Hurdle, and Queue Dynamics

Tests maker fee decomposition, post-only boundary guards, queue fill modeling,
and friction-aware decision hurdle gating.
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from pathlib import Path

from core.execution.maker_execution_model import (
    calculate_leg_fee,
    calculate_round_trip,
    compare_styles,
    ExecutionStyle,
    DEFAULT_GST_RATE,
    TAKER_BASE_RATE,
    MAKER_BASE_RATE,
    REBATE_BASE_RATE,
)
from core.research.queue_dynamics import (
    validate_post_only,
    evaluate_queue_dynamics,
)
from core.execution.friction_hurdle_gate import (
    evaluate_friction_hurdle,
)

ROOT = Path(__file__).resolve().parents[1]


class TestMakerExecutionModel(unittest.TestCase):
    def test_calculate_leg_fee_decomposition(self):
        # 1 contract BTCUSD @ 82,000, notional = 82.00 USD
        notional = Decimal("82.00")
        decomp = calculate_leg_fee(notional, TAKER_BASE_RATE, DEFAULT_GST_RATE, ExecutionStyle.TAKER)
        
        # Base fee = 82.00 * 0.0005 = 0.04100000 USD
        expected_base = Decimal("0.04100000")
        self.assertEqual(decomp.base_fee, expected_base)
        
        # GST = 0.04100000 * 0.18 = 0.00738000 USD
        expected_gst = Decimal("0.00738000")
        self.assertEqual(decomp.gst, expected_gst)
        
        # Total fee = 0.04838000 USD
        expected_total = expected_base + expected_gst
        self.assertEqual(decomp.total_fee, expected_total)
        self.assertEqual(decomp.effective_rate_bps, Decimal("5.90"))

    def test_maker_fee_savings_exact(self):
        ep = Decimal("82000.00")
        xp = Decimal("82100.00")
        qty = Decimal("1")
        cm = Decimal("0.001")
        
        taker = calculate_round_trip(ep, xp, qty, cm, ExecutionStyle.TAKER)
        maker = calculate_round_trip(ep, xp, qty, cm, ExecutionStyle.MAKER)
        
        # Maker base rate (0.0002) is 40% of Taker base rate (0.0005) -> 60% savings
        savings = taker.total_fees - maker.total_fees
        savings_pct = (savings / taker.total_fees) * Decimal("100")
        self.assertAlmostEqual(float(savings_pct), 60.0, places=2)
        self.assertTrue(maker.net_pnl > taker.net_pnl)

    def test_rebate_vip_produces_negative_fees(self):
        ep = Decimal("82000.00")
        xp = Decimal("82050.00")
        qty = Decimal("1")
        cm = Decimal("0.001")
        
        rebate = calculate_round_trip(ep, xp, qty, cm, ExecutionStyle.REBATE_VIP)
        self.assertTrue(rebate.total_fees < Decimal("0"))
        # Trader receives rebate, so net PnL > gross PnL
        self.assertTrue(rebate.net_pnl > rebate.gross_pnl)


class TestQueueDynamicsAndPostOnly(unittest.TestCase):
    def test_post_only_allows_passive_resting_quotes(self):
        bb = Decimal("670.00")
        ba = Decimal("671.00")
        
        # BUY at 670.00 rests at best bid
        res_buy = validate_post_only("BUY", Decimal("670.00"), bb, ba)
        self.assertTrue(res_buy.allowed)
        self.assertIsNone(res_buy.rejection_reason)
        
        # SELL at 671.00 rests at best ask
        res_sell = validate_post_only("SELL", Decimal("671.00"), bb, ba)
        self.assertTrue(res_sell.allowed)
        self.assertIsNone(res_sell.rejection_reason)

    def test_post_only_rejects_crossing_spread(self):
        bb = Decimal("670.00")
        ba = Decimal("671.00")
        
        # BUY at 671.00 would cross ask -> REJECT
        res_cross_buy = validate_post_only("BUY", Decimal("671.00"), bb, ba)
        self.assertFalse(res_cross_buy.allowed)
        self.assertIn("crosses best ask", res_cross_buy.rejection_reason)
        
        # SELL at 670.00 would cross bid -> REJECT
        res_cross_sell = validate_post_only("SELL", Decimal("670.00"), bb, ba)
        self.assertFalse(res_cross_sell.allowed)
        self.assertIn("crosses best bid", res_cross_sell.rejection_reason)

    def test_queue_dynamics_metrics(self):
        qd = evaluate_queue_dynamics(
            queue_depth_ahead=Decimal("50"),
            order_size=Decimal("1"),
            volume_rate_per_sec=Decimal("10"),
            horizon_seconds=Decimal("5"),
            notional_usd=Decimal("100.00"),
            fee_savings_usd=Decimal("0.05"),
            adverse_selection_bps=Decimal("1.5"),
        )
        self.assertEqual(qd.expected_wait_seconds, Decimal("5.00"))
        self.assertTrue(Decimal("0.5") < qd.fill_probability < Decimal("1.0"))
        self.assertTrue(qd.adverse_selection_cost_usd > Decimal("0"))


class TestFrictionHurdleGate(unittest.TestCase):
    def test_scalp_rejected_under_taker_friction(self):
        # 4.5-point BTCUSD scalp on 1 contract
        verdict = evaluate_friction_hurdle(
            entry_price=Decimal("82015.50"),
            target_price=Decimal("82020.00"),
            stop_price=Decimal("82010.00"),
            quantity=Decimal("1"),
            contract_multiplier=Decimal("0.001"),
            execution_style=ExecutionStyle.TAKER,
        )
        self.assertFalse(verdict.allowed)
        self.assertIn("exceeding max allowed", verdict.rejection_reason)
        self.assertTrue(verdict.fee_to_target_pct > Decimal("100"))

    def test_wide_target_passes_hurdle(self):
        # 750-point BTCUSD swing target with 250-point stop
        verdict = evaluate_friction_hurdle(
            entry_price=Decimal("82000.00"),
            target_price=Decimal("82750.00"),
            stop_price=Decimal("81750.00"),
            quantity=Decimal("1"),
            contract_multiplier=Decimal("0.001"),
            execution_style=ExecutionStyle.TAKER,
            max_fee_ratio_pct=Decimal("40.0"),
            min_post_fee_rr=Decimal("1.25"),
        )
        self.assertTrue(verdict.allowed)
        self.assertIsNone(verdict.rejection_reason)
        self.assertTrue(verdict.fee_to_target_pct < Decimal("40.0"))
        self.assertTrue(verdict.post_fee_rr >= Decimal("1.25"))


if __name__ == "__main__":
    unittest.main()
