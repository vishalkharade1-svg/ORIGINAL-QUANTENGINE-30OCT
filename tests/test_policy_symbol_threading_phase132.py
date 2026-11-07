"""Phase132-C: policy symbol-threading regression (deterministic, offline).

Defect: TradeSimulator FIXED branch and BrokerEngine post-cost route dropped
`symbol` (and exit_mode), so per-instrument overrides were bypassed at the
fill choke. Paper/Broker gross gates duplicated bounds instead of using the
single authority. economics.recheck_rr dropped symbol (dormant).

These tests FAIL before the fix (global fallback allows what the override
refuses) and PASS after.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass


@dataclass
class Order132:
    direction: str = "BULLISH"
    entry: float = 100.0
    stop_loss: float = 90.0
    take_profit: float = 130.0  # gross RR 3.0
    quantity: float = 2.0
    risk_amount: float = 20.0
    commission: float = 0.0
    slippage: float = 0.0
    symbol: str = "PHASE132-SYM"
    setup_id: str = "P132-1"
    order_id: str = ""
    entry_mode: str = "LIMIT_RETEST"
    canonical_id: str = "P132-1"
    score: float = 80.0
    confidence: float = 85.0
    valid: bool = True
    reason: str = ""
    position_value: float = 0.0
    status: str = "NEW"
    exit_mode: str = "FIXED_TARGET"
    trailing_enabled: bool = False
    trailing_activation_r: float = 0.0
    trailing_distance_r: float = 0.0


class TestPolicySymbolThreading132(unittest.TestCase):
    def setUp(self):
        from core.risk.trading_policy import trading_policy_manager
        self.mgr = trading_policy_manager()
        # Isolate: remember prior override for our symbol (should be none)
        self.sym = "PHASE132-SYM"
        try:
            self.mgr.reset_instrument(self.sym)
        except Exception:
            pass

    def tearDown(self):
        try:
            self.mgr.reset_instrument(self.sym)
        except Exception:
            pass
        try:
            self.mgr.reset_instrument("PHASE132-SYM-2")
        except Exception:
            pass

    def test_simulator_fixed_respects_instrument_override(self):
        from core.backtesting.trade_simulator import TradeSimulator
        # Override min to 6R for this symbol only; RR 3.0 must refuse.
        self.mgr.set_instrument(self.sym, {
            "min_rr": 6.0, "max_rr": 20.0,
            "trailing_enabled": False,
            "trailing_activation_r": 1.0,
            "trailing_distance_r": 0.5,
            "auto_exit_on_opposite_signal": True,
        })
        sim = TradeSimulator()
        # Small nonzero costs keep post-cost RR ~2.9 (still <6, >1 global).
        order = Order132()
        trade = sim.open_trade(order, 1000, quantity=2.0,
                               commission=1.0, slippage=1.0)
        self.assertIsNone(trade, "FIXED fill must respect per-symbol min_rr=6")

    def test_simulator_fixed_allows_when_override_satisfied(self):
        from core.backtesting.trade_simulator import TradeSimulator
        self.mgr.set_instrument(self.sym, {
            "min_rr": 1.0, "max_rr": 20.0,
            "trailing_enabled": False,
            "trailing_activation_r": 1.0,
            "trailing_distance_r": 0.5,
            "auto_exit_on_opposite_signal": True,
        })
        sim = TradeSimulator()
        order = Order132()  # RR 3.0
        trade = sim.open_trade(order, 1000, quantity=2.0,
                               commission=1.0, slippage=1.0)
        self.assertIsNotNone(trade)

    def test_broker_post_cost_respects_override(self):
        # BrokerEngine._route post-cost must thread symbol; test the
        # underlying authority path directly via post_cost_rr with symbol
        # (broker delegates here). Before fix broker called without symbol.
        from core.risk.costs import post_cost_rr
        self.mgr.set_instrument(self.sym, {
            "min_rr": 6.0, "max_rr": 20.0,
            "trailing_enabled": False,
            "trailing_activation_r": 1.0,
            "trailing_distance_r": 0.5,
            "auto_exit_on_opposite_signal": True,
        })
        verdict = post_cost_rr(direction="BULLISH", entry=100.0, stop=90.0,
                               target=130.0, quantity=2.0,
                               commission=1.0, slippage=1.0,
                               exit_mode="FIXED_TARGET", symbol=self.sym)
        self.assertFalse(verdict.allowed)
        # Global would allow (RR~2.9 >=1.0); override refuses.
        verdict_global = post_cost_rr(direction="BULLISH", entry=100.0,
                                      stop=90.0, target=130.0, quantity=2.0,
                                      commission=1.0, slippage=1.0,
                                      exit_mode="FIXED_TARGET", symbol=None)
        self.assertTrue(verdict_global.allowed)

    def test_max_bound_enforced(self):
        from core.backtesting.accounting import risk_reward_allowed
        # 20R passes, 20.1 fails (inclusive max).
        self.assertTrue(risk_reward_allowed(20.0, exit_mode="FIXED_TARGET"))
        self.assertFalse(risk_reward_allowed(20.1, exit_mode="FIXED_TARGET"))
        self.assertTrue(risk_reward_allowed(2.0, exit_mode="FIXED_TARGET"))
        self.assertFalse(risk_reward_allowed(0.5, exit_mode="FIXED_TARGET"))

    def test_trailing_targetless_refuses(self):
        from core.risk.costs import post_cost_trailing
        v = post_cost_trailing(direction="BULLISH", entry=100.0, stop=90.0,
                               quantity=2.0, commission=1.0, slippage=1.0,
                               target=0.0, symbol=None)
        self.assertFalse(v.allowed)

    def test_recheck_rr_threads_symbol(self):
        from core.execution.economics import recheck_rr
        self.mgr.set_instrument("PHASE132-SYM-2", {
            "min_rr": 6.0, "max_rr": 20.0,
            "trailing_enabled": True,
            "trailing_activation_r": 1.0,
            "trailing_distance_r": 0.5,
            "auto_exit_on_opposite_signal": True,
        })
        # RR 3.0 geometry via actual_entry; global allows, override refuses.
        # recheck_rr must accept optional symbol and enforce it.
        try:
            refused = recheck_rr(entry=100.0, stop=90.0, target=130.0,
                                 actual_entry=100.0, direction="BULLISH",
                                 symbol="PHASE132-SYM-2")
        except TypeError:
            self.fail("recheck_rr must accept symbol kwarg (Phase132 fix)")
        self.assertFalse(refused.allowed)


if __name__ == "__main__":
    unittest.main()
