"""Phase 100: policy-authority guard — no hidden 6R minimum may return.

Every executable R:R gate must derive its minimum from the authoritative
trading policy (global default or exact-instrument override). The frozen
research threshold (settings 6.0) is governance data only and must never
govern a fill path.

Discriminator value 7.0 is used throughout: it is neither the 1.0 default
nor the removed 6.0 floor, so a boundary that follows 7.0 proves a live
configuration read.
"""
import unittest
from pathlib import Path
from unittest import mock

from config import risk_settings
from tests.test_breakout_policy_erosion_phase99 import drive_breakout

ROOT = Path(__file__).resolve().parents[1]
PROD_DIRS = (ROOT / "core", ROOT / "backtesting")
# Value-access spellings that would reintroduce a settings-driven floor.
# (Bare prose mentions in comments, e.g. "config MIN_RISK_REWARD", are
# not value reads and are intentionally allowed.)
import re as _re
FORBIDDEN_RES = (
    _re.compile(r"risk_settings\s*\.\s*MIN_RISK_REWARD"),
    _re.compile(r"getattr\([^)]*MIN_RISK_REWARD"),
)


def prod_sources():
    for base in PROD_DIRS:
        for path in sorted(base.rglob("*.py")):
            yield path


class TestNoSettingsFloorInProduction(unittest.TestCase):
    def test_no_settings_min_read_in_fill_paths(self):
        hits = []
        for path in prod_sources():
            for lineno, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.split("#", 1)[0]
                for rx in FORBIDDEN_RES:
                    if rx.search(stripped):
                        hits.append("%s:%d" % (path.name, lineno))
        self.assertEqual(hits, [])

    def test_research_threshold_intact_but_unconsumed(self):
        # The frozen research threshold still exists as governed data...
        self.assertTrue(
        1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0,
        "frozen-era constant kept for audit"
    )
        # ...but no production gate reads it (covered above).


class PolicyOverrideCase(unittest.TestCase):
    SYMBOL = "TEST100"

    def setUp(self):
        from core.risk.trading_policy import trading_policy_manager
        self._manager = trading_policy_manager()
        self._previous_overrides = {
            key: values
            for key, values in self._manager.snapshot()["instruments"].items()
            if self._manager._key(key) == self._manager._key(self.SYMBOL)
        }
        # The tests assert the default policy before applying their override.
        self._manager.reset_instrument(self.SYMBOL)

    def tearDown(self):
        self._manager.reset_instrument(self.SYMBOL)
        for key, values in self._previous_overrides.items():
            self._manager.set_instrument(key, values)

    def set_min(self, minimum):
        from core.risk.trading_policy import trading_policy_manager
        trading_policy_manager().set_instrument(
            self.SYMBOL, {"min_rr": float(minimum)})

    def test_default_minimum_is_one(self):
        from core.risk.trading_policy import trading_policy
        self.assertEqual(trading_policy(self.SYMBOL).min_rr, 1.0)
        self.assertEqual(trading_policy("UNKNOWN-SYM").min_rr, 1.0)

    def test_gross_gate_follows_override(self):
        from core.backtesting.accounting import risk_reward_allowed
        # RR 6.5: accepted under default 1R, refused under min 7R.
        # Refusal at 6.5 with min 7R proves the live read (a hardcoded
        # 6R floor would accept 6.5).
        self.assertTrue(risk_reward_allowed(6.5, symbol=self.SYMBOL))
        self.set_min(7.0)
        self.assertFalse(risk_reward_allowed(6.5, symbol=self.SYMBOL))
        self.assertTrue(risk_reward_allowed(7.0, symbol=self.SYMBOL))
        self.assertFalse(risk_reward_allowed(6.99, symbol=self.SYMBOL))

    def test_post_cost_gate_follows_override(self):
        from core.risk.costs import post_cost_rr
        # Entry 100/stop 90/target 165, zero costs: RR 6.5.
        kwargs = dict(direction="BULLISH", entry=100.0, stop=90.0,
                      target=165.0, quantity=1.0, commission=0.0,
                      slippage=0.0, symbol=self.SYMBOL)
        self.assertTrue(post_cost_rr(**kwargs).allowed)
        self.set_min(7.0)
        verdict = post_cost_rr(**kwargs)
        self.assertFalse(verdict.allowed)
        self.assertIn("below minimum", verdict.reason)

    def test_registry_erosion_follows_override(self):
        # Setup 110/100/130, fill open 104 -> actual RR ~= 6.5.
        # Default policy fills; min-7R override refuses; order rides.
        sim, order = drive_breakout(
            entry=110.0, stop=100.0, target=130.0,
            fill_open=104.0, fill_high=106.0, fill_low=102.0,
            symbol=self.SYMBOL)
        self.assertEqual(order.status, "FILLED")
        self.assertIsNotNone(sim.current_trade)
        self.set_min(7.0)
        sim2, order2 = drive_breakout(
            entry=110.0, stop=100.0, target=130.0,
            fill_open=104.0, fill_high=106.0, fill_low=102.0,
            symbol=self.SYMBOL)
        self.assertIsNone(sim2.current_trade)
        self.assertEqual(order2.status, "PENDING")

    def test_legacy_path_follows_override(self):
        # Same-candle legacy fill (no registry order): RR 2.0 fills
        # by default, refused under min 7R.
        from backtesting.backtester import Backtester
        from core.backtesting.trade_simulator import TradeSimulator
        from core.risk.order_intent import OrderIntent
        from tests.test_breakout_policy_erosion_phase99 import (
            NamespaceDriven, SimpleCandle)
        for minimum, expect_fill in ((None, True), (7.0, False)):
            if minimum is not None:
                self.set_min(minimum)
            pipeline = NamespaceDriven()
            simulator = TradeSimulator()
            backtester = Backtester(pipeline, None, simulator)
            context = pipeline.context
            context.order = OrderIntent(
                direction="BULLISH", entry=100.0, stop_loss=90.0,
                take_profit=120.0, quantity=1.0, commission=0.0,
                slippage=0.0, confidence=85.0, score=85.0,
                symbol=self.SYMBOL, valid=True, setup_id="LEG-1")
            context.replay_index = 1
            bar = SimpleCandle(open_=100.0, high=105.0, low=99.0,
                               close=104.0, timestamp=1)
            with mock.patch.object(
                risk_settings, "ACTIVE_ENTRY_MODES", ("LIMIT_RETEST",),
            ):
                backtester._execute_signal(bar)
            if expect_fill:
                self.assertIsNotNone(simulator.current_trade)
            else:
                self.assertIsNone(simulator.current_trade)
                self.assertEqual(simulator.registry.count(), 0)
            from core.risk.trading_policy import trading_policy_manager
            trading_policy_manager().reset_instrument(self.SYMBOL)


if __name__ == "__main__":
    unittest.main()
