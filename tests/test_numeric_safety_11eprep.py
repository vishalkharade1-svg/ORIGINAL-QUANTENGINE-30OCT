"""
====================================================

QuantEngine

Phase 11E-Prep — C1 adversarial numeric safety.

Non-finite numerics (NaN, +Inf, -Inf) must fail closed at
every trading boundary: sizer, position audit, trade
simulator, P&L classification, historical candle loading.

Paper/offline only. No strategy, parameter, or LIVE changes.

====================================================
"""

import math
import unittest
from types import SimpleNamespace

from core.backtesting.accounting import classify_pnl
from core.backtesting.trade_simulator import TradeSimulator
from core.risk.position_manager import PositionManager
from core.risk.position_sizer import PositionSizer

NAN = float("nan")
INF = float("inf")
NINF = float("-inf")


class TestSizerFiniteInputs11EPrep(unittest.TestCase):
    """C1-A: every non-finite sizer input is invalid."""

    def _sizer(self):
        return PositionSizer()

    def test_non_finite_balance_rejected(self):
        for bad in (NAN, INF, NINF):
            out = self._sizer().calculate(
                balance=bad,
                entry_price=77600.0,
                stop_price=77500.0,
            )
            self.assertFalse(out.valid, msg="balance=%r" % (bad,))
            self.assertEqual(out.quantity, 0)
            self.assertIn("balance", out.reason.lower())

    def test_non_finite_entry_rejected(self):
        for bad in (NAN, INF, NINF):
            out = self._sizer().calculate(
                balance=2000.0,
                entry_price=bad,
                stop_price=77500.0,
            )
            self.assertFalse(out.valid, msg="entry=%r" % (bad,))
            self.assertEqual(out.quantity, 0)

    def test_non_finite_stop_rejected(self):
        for bad in (NAN, INF, NINF):
            out = self._sizer().calculate(
                balance=2000.0,
                entry_price=77600.0,
                stop_price=bad,
            )
            self.assertFalse(out.valid, msg="stop=%r" % (bad,))
            self.assertEqual(out.quantity, 0)

    def test_non_finite_risk_factor_rejected(self):
        out = self._sizer().calculate(
            balance=2000.0,
            entry_price=77600.0,
            stop_price=77500.0,
            confidence=NAN,
        )
        self.assertFalse(out.valid)
        self.assertEqual(out.quantity, 0)

    def test_non_finite_leverage_coerced_like_non_positive(self):
        out = self._sizer().calculate(
            balance=2000.0,
            entry_price=100.0,
            stop_price=99.5,
            leverage=NAN,
        )
        self.assertTrue(out.valid)
        self.assertEqual(out.leverage, 1.0)

    def test_finite_inputs_still_size(self):
        out = self._sizer().calculate(
            balance=2000.0,
            entry_price=77600.0,
            stop_price=77500.0,
        )
        self.assertTrue(out.valid)
        self.assertTrue(math.isfinite(out.quantity))
        self.assertGreater(out.quantity, 0)


class TestAuditFiniteQuantity11EPrep(unittest.TestCase):
    """C1-B: non-finite audit quantity is zeroed, never kept."""

    def _audit(self, quantity, entry=77600.0):
        manager = PositionManager()
        order = SimpleNamespace(
            quantity=quantity,
            entry=entry,
            position_value=quantity * entry
            if math.isfinite(quantity) and math.isfinite(entry)
            else 0.0,
            valid=True,
            reason="",
            symbol="BTC",
        )
        return manager.audit(order)

    def test_non_finite_quantity_zeroed(self):
        for bad in (NAN, INF, NINF):
            corrected, reasons = self._audit(bad)
            self.assertEqual(corrected.quantity, 0.0)
            self.assertTrue(
                any("non-finite" in r for r in reasons),
                msg="reasons=%r" % (reasons,),
            )

    def test_non_finite_quantity_invalidates_dataclass_order(self):
        from core.risk.order_intent import OrderIntent

        manager = PositionManager()
        for bad in (NAN, INF, NINF):
            order = OrderIntent(
                direction="BULLISH",
                entry=77600.0,
                stop_loss=77500.0,
                take_profit=78000.0,
                quantity=bad,
                symbol="BTC",
                valid=True,
            )
            corrected, _ = manager.audit(order)
            self.assertEqual(corrected.quantity, 0.0)
            self.assertFalse(corrected.valid)

    def test_non_finite_entry_zeroes_quantity(self):
        for bad in (NAN, INF):
            corrected, reasons = self._audit(0.01, entry=bad)
            self.assertEqual(corrected.quantity, 0.0)
            self.assertTrue(
                any("invalid entry" in r for r in reasons)
            )

    def test_finite_quantity_flows_through(self):
        corrected, _ = self._audit(0.001, entry=100.0)
        self.assertGreater(corrected.quantity, 0)


class TestSimulatorFiniteTrade11EPrep(unittest.TestCase):
    """C1-C: the simulator cannot create a non-finite trade."""

    def _order(self, **overrides):
        base = {
            "direction": "BULLISH",
            "entry": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
            "quantity": 1.0,
            "risk_amount": 2.0,
            "commission": 0.0,
            "slippage": 0.0,
            "score": 0.0,
            "confidence": 0.0,
            "symbol": "T",
            "setup_id": "S",
            "order_id": "O",
            "entry_mode": "",
            "canonical_id": "",
            "valid": True,
            "reason": "",
            "position_value": 100.0,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_non_finite_quantity_creates_no_trade(self):
        for bad in (NAN, INF, NINF):
            sim = TradeSimulator()
            self.assertIsNone(sim.open_trade(self._order(quantity=bad), 1))
            self.assertIsNone(sim.current_trade)

    def test_non_finite_entry_creates_no_trade(self):
        for bad in (NAN, INF):
            sim = TradeSimulator()
            self.assertIsNone(sim.open_trade(self._order(entry=bad), 1))

    def test_non_finite_stop_creates_no_trade(self):
        sim = TradeSimulator()
        self.assertIsNone(sim.open_trade(self._order(stop_loss=NAN), 1))

    def test_zero_quantity_creates_no_trade(self):
        sim = TradeSimulator()
        self.assertIsNone(sim.open_trade(self._order(quantity=0.0), 1))

    def test_valid_order_still_opens(self):
        sim = TradeSimulator()
        trade = sim.open_trade(self._order(), 1)
        self.assertIsNotNone(trade)
        self.assertTrue(math.isfinite(trade.quantity))


class TestClassifyFinite11EPrep(unittest.TestCase):
    """C1-D: non-finite P&L is unclassifiable — never a result."""

    def test_nan_raises(self):
        with self.assertRaises(ValueError):
            classify_pnl(NAN)

    def test_inf_raises(self):
        with self.assertRaises(ValueError):
            classify_pnl(INF)

    def test_neg_inf_raises(self):
        with self.assertRaises(ValueError):
            classify_pnl(NINF)

    def test_finite_still_classifies(self):
        self.assertEqual(classify_pnl(5.0), "WIN")
        self.assertEqual(classify_pnl(-5.0), "LOSS")
        self.assertEqual(classify_pnl(0.0), "BREAKEVEN")


class TestCandleHistoryFinite11EPrep(unittest.TestCase):
    """C1-E: bulk and streaming candle paths agree on finiteness."""

    def _bar(self, **overrides):
        bar = {
            "time": 1700000000,
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 10.0,
        }
        bar.update(overrides)
        return bar

    def test_non_finite_ohlc_rejected_per_field(self):
        from data.candle_builder import CandleBuilder

        for field in ("open", "high", "low", "close"):
            for bad in (NAN, INF, NINF):
                builder = CandleBuilder(timeframe="1m")
                with self.assertRaises(
                    ValueError, msg="%s=%r" % (field, bad)
                ):
                    builder.load_history([self._bar(**{field: bad})])
                self.assertEqual(builder.count(), 0)

    def test_streaming_path_agrees(self):
        from data.candle_builder import CandleBuilder

        builder = CandleBuilder(timeframe="1m")
        self.assertIsNone(builder.update(1700000000, NAN))
        self.assertIsNone(builder.update(1700000000, INF))
        self.assertEqual(builder.count(), 0)
        self.assertGreaterEqual(builder.rejected_ticks, 2)

    def test_finite_history_still_loads(self):
        from data.candle_builder import CandleBuilder

        builder = CandleBuilder(timeframe="1m")
        builder.load_history([self._bar(), self._bar()])
        self.assertEqual(builder.count(), 2)


class TestPhantomTradeEndToEnd11EPrep(unittest.TestCase):
    """§23: invalid numerics cannot become financially meaningful."""

    def test_nan_through_sizer_audit_simulator_books_nothing(self):
        from core.risk.account import Account

        account = Account(starting_balance=2000.0)
        sim = TradeSimulator()

        # Corrupt upstream sizing result.
        sized = PositionSizer().calculate(
            balance=NAN, entry_price=77600.0, stop_price=77500.0
        )
        self.assertFalse(sized.valid)

        # Even a directly corrupted order dies at both gates.
        order = SimpleNamespace(
            direction="BULLISH",
            entry=NAN,
            stop_loss=98.0,
            take_profit=104.0,
            quantity=NAN,
            risk_amount=NAN,
            commission=0.0,
            slippage=0.0,
            score=0.0,
            confidence=0.0,
            symbol="T",
            setup_id="S",
            order_id="O",
            entry_mode="",
            canonical_id="",
            valid=True,
            reason="",
            position_value=0.0,
        )
        corrected, _ = PositionManager().audit(order)
        self.assertEqual(corrected.quantity, 0.0)
        self.assertIsNone(sim.open_trade(order, 1))
        self.assertEqual(sim.registry.count(), 0)

        # Nothing booked, balance untouched and finite.
        self.assertEqual(account.balance, 2000.0)
        self.assertTrue(math.isfinite(account.balance))
        self.assertTrue(math.isfinite(account.equity))

    def test_inf_pnl_cannot_book_as_win(self):
        with self.assertRaises(ValueError):
            classify_pnl(INF)


class TestAccountingFiniteInvariants11EPrep(unittest.TestCase):
    """§24: every value on a valid trade is finite."""

    def test_valid_trade_carries_only_finite_values(self):
        sim = TradeSimulator()
        order = SimpleNamespace(
            direction="BULLISH",
            entry=100.0,
            stop_loss=98.0,
            take_profit=104.0,
            quantity=1.0,
            risk_amount=2.0,
            commission=0.0,
            slippage=0.0,
            score=0.0,
            confidence=0.0,
            symbol="T",
            setup_id="S",
            order_id="O",
            entry_mode="",
            canonical_id="",
            valid=True,
            reason="",
            position_value=100.0,
        )
        trade = sim.open_trade(order, 1)
        for name in (
            "quantity",
            "entry",
            "stop_loss",
            "take_profit",
            "risk_amount",
            "commission",
            "slippage",
        ):
            self.assertTrue(
                math.isfinite(float(getattr(trade, name))),
                msg=name,
            )


if __name__ == "__main__":
    unittest.main()
