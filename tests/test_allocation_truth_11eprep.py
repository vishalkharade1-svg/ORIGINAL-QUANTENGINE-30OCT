"""
====================================================

QuantEngine

Phase 11E-Prep — H1 allocation/risk truthfulness.

MAX_ALLOCATION_PER_TRADE is a NOTIONAL cap (maximum
position value, quote currency), enforced identically by
PositionSizer.calculate and PositionManager.audit,
independent of leverage. Final risk fields describe the
final executable position, never the abandoned pre-cap
request.

Paper/offline only. No strategy, parameter, or LIVE changes.

====================================================
"""

import unittest
from types import SimpleNamespace

from core.risk.order_intent import OrderIntent
from core.risk.position_manager import PositionManager
from core.risk.position_sizer import PositionSizer


def sized(balance=2000.0, entry=100.0, stop=99.5, leverage=10.0):
    return PositionSizer().calculate(
        balance=balance,
        entry_price=entry,
        stop_price=stop,
        leverage=leverage,
    )


class TestCapUnitIsNotional11EPrep(unittest.TestCase):
    """H1-A/H1-B: one unit, both layers, any leverage."""

    def test_below_cap_not_clamped(self):
        out = sized(balance=2000.0, entry=100.0, stop=95.0)
        self.assertTrue(out.valid)
        self.assertFalse(out.capped)
        self.assertLess(out.position_value, 500.0)
        self.assertAlmostEqual(out.position_value, 400.0, places=6)

    def test_at_cap_accepted(self):
        # risk 20 / dist 4 = qty 5 -> notional exactly 500.
        out = sized(balance=2000.0, entry=100.0, stop=96.0)
        self.assertTrue(out.valid)
        self.assertFalse(out.capped)
        self.assertAlmostEqual(out.position_value, 500.0, places=6)

    def test_above_cap_clamped_to_notional(self):
        out = PositionSizer().calculate(
            balance=2000.0,
            entry_price=77600.0,
            stop_price=77500.0,
        )
        self.assertTrue(out.valid)
        self.assertTrue(out.capped)
        self.assertLessEqual(out.position_value, 500.0)
        self.assertAlmostEqual(out.position_value, 500.0, places=6)
        self.assertIn("notional", out.cap_reason)

    def test_cap_independent_of_leverage(self):
        lev1 = PositionSizer().calculate(
            balance=2000.0,
            entry_price=77600.0,
            stop_price=77500.0,
            leverage=1.0,
        )
        lev10 = PositionSizer().calculate(
            balance=2000.0,
            entry_price=77600.0,
            stop_price=77500.0,
            leverage=10.0,
        )
        self.assertAlmostEqual(lev1.quantity, lev10.quantity, places=9)
        self.assertAlmostEqual(
            lev1.position_value, lev10.position_value, places=6
        )
        self.assertAlmostEqual(
            lev1.risk_amount, lev10.risk_amount, places=9
        )
        self.assertEqual(lev1.capped, lev10.capped)

    def test_manager_agrees_with_sizer_no_second_clamp(self):
        out = PositionSizer().calculate(
            balance=2000.0,
            entry_price=77600.0,
            stop_price=77500.0,
        )
        order = SimpleNamespace(
            quantity=out.quantity,
            entry=77600.0,
            position_value=out.position_value,
            valid=True,
            reason="",
            symbol="BTC",
        )
        corrected, reasons = PositionManager().audit(order)
        # Agreement means NO second cap: quantities match to
        # the manager's quantity-precision rounding (8dp), and
        # no "(notional limit)" reason fires.
        self.assertAlmostEqual(
            corrected.quantity, out.quantity, places=7
        )
        self.assertFalse(
            any("notional limit" in r for r in reasons),
            msg="second cap fired: %r" % (reasons,),
        )


class TestRiskTruthfulness11EPrep(unittest.TestCase):
    """H1-C/H1-D: risk fields describe the final position."""

    def test_sizer_risk_matches_final_quantity(self):
        out = PositionSizer().calculate(
            balance=2000.0,
            entry_price=77600.0,
            stop_price=77500.0,
        )
        self.assertAlmostEqual(
            out.risk_amount,
            out.quantity * out.stop_distance,
            places=9,
        )
        self.assertAlmostEqual(
            out.actual_risk_percent,
            out.risk_amount / 2000.0,
            places=9,
        )
        self.assertLess(out.actual_risk_percent, out.risk_percent)

    def test_intent_carries_actual_risk_percent(self):
        out = PositionSizer().calculate(
            balance=2000.0,
            entry_price=77600.0,
            stop_price=77500.0,
        )
        intent = OrderIntent(
            direction="BULLISH",
            entry=77600.0,
            stop_loss=77500.0,
            take_profit=78000.0,
            quantity=out.quantity,
            risk_percent=out.risk_percent,
            risk_amount=out.risk_amount,
            actual_risk_percent=out.actual_risk_percent,
            symbol="BTC",
            valid=True,
        )
        self.assertAlmostEqual(
            intent.actual_risk_percent, out.actual_risk_percent
        )
        self.assertLess(intent.actual_risk_percent, intent.risk_percent)

    def test_intent_defaults_backward_compatible(self):
        intent = OrderIntent(symbol="BTC")
        self.assertEqual(intent.actual_risk_percent, 0.0)

    def test_simulator_books_final_quantity_risk(self):
        from core.backtesting.trade_simulator import TradeSimulator

        out = PositionSizer().calculate(
            balance=2000.0,
            entry_price=77600.0,
            stop_price=77500.0,
        )
        order = SimpleNamespace(
            direction="BULLISH",
            entry=77600.0,
            stop_loss=77500.0,
            take_profit=78000.0,
            quantity=out.quantity,
            risk_amount=9999.0,
            commission=0.0,
            slippage=0.0,
            score=0.0,
            confidence=0.0,
            symbol="BTC",
            setup_id="S",
            order_id="O",
            entry_mode="",
            canonical_id="",
            valid=True,
            reason="",
            position_value=out.position_value,
        )
        trade = TradeSimulator().open_trade(order, 1)
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(
            trade.risk_amount,
            trade.quantity * abs(trade.entry - trade.stop_loss),
            places=9,
        )
        self.assertNotEqual(trade.risk_amount, 9999.0)


if __name__ == "__main__":
    unittest.main()
