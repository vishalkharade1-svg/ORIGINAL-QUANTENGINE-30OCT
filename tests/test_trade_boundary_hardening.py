"""
====================================================

QuantEngine

Trade Boundary & Invariant Hardening Tests
Phase 163 Independent Audit Implementation

====================================================
"""

import math
import unittest
from dataclasses import asdict

from core.backtesting.trade import Trade
from core.backtesting.trade_simulator import TradeSimulator
from core.monitoring.api_server import _json_safe
from core.setup.setup_candidate import SetupCandidate


class DummyCandle:
    def __init__(self, high: float, low: float, close: float, timestamp: int):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp


class TestTradeBoundaryHardening(unittest.TestCase):
    """Execution-boundary validation and invariant verification for Trade."""

    def test_partial_instantiation_unblocked(self):
        """Constructing partial Trade instances (e.g. test fixtures, stubs)

        must succeed without triggering execution-boundary validation.
        """
        empty = Trade()
        self.assertEqual(empty.direction, "")
        self.assertEqual(empty.entry, 0.0)
        self.assertEqual(empty.status, "OPEN")
        self.assertEqual(empty.setup_score, 0.0)

        partial = Trade(direction="SIDEWAYS", entry=0.0, stop_loss=10.0, setup_score=73.5)
        self.assertEqual(partial.direction, "SIDEWAYS")
        self.assertEqual(partial.setup_score, 73.5)

    def test_slots_true_contract(self):
        """Trade must have __slots__ and prohibit undeclared attributes."""
        t = Trade()
        self.assertTrue(hasattr(Trade, "__slots__"))
        self.assertFalse(hasattr(t, "__dict__"))
        with self.assertRaises(AttributeError):
            t.unrecognized_dynamic_attribute = 42

    def test_validate_executable_valid(self):
        """Valid BULLISH and BEARISH trades pass validate_executable()."""
        bull = Trade(
            direction="BULLISH",
            entry=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            quantity=10.0,
            risk_amount=50.0,
        )
        self.assertIs(bull.validate_executable(), bull)

        bear = Trade(
            direction="BEARISH",
            entry=100.0,
            stop_loss=105.0,
            take_profit=90.0,
            quantity=5.0,
            risk_amount=25.0,
        )
        self.assertIs(bear.validate_executable(), bear)

    def test_invalid_direction_rejected(self):
        """Invalid directions must be rejected so update() side selection

        cannot silently fall back to treating them as bearish.
        """
        for bad_dir in ["", "SIDEWAYS", "LONG", "SHORT", "NEUTRAL", "bullish"]:
            t = Trade(
                direction=bad_dir,
                entry=100.0,
                stop_loss=95.0,
                quantity=1.0,
            )
            with self.assertRaises(ValueError) as ctx:
                t.validate_executable()
            self.assertIn("Trade.direction must be BULLISH or BEARISH", str(ctx.exception))

        # Simulator open_trade fails closed for invalid direction
        sim = TradeSimulator()
        bad_setup = SetupCandidate(
            direction="SIDEWAYS",
            entry=100.0,
            stop_loss=95.0,
            take_profit=110.0,
        )
        opened = sim.open_trade(bad_setup, timestamp=1)
        self.assertIsNone(opened)
        self.assertIsNone(sim.current_trade)

    def test_invalid_exit_mode_rejected(self):
        """Invalid exit modes must be rejected at execution boundary."""
        t = Trade(
            direction="BULLISH",
            entry=100.0,
            stop_loss=95.0,
            quantity=1.0,
            exit_mode="INVALID_MODE",
        )
        with self.assertRaises(ValueError) as ctx:
            t.validate_executable()
        self.assertIn("Trade.exit_mode must be FIXED_TARGET or TRAILING_STOP", str(ctx.exception))

    def test_non_finite_and_non_positive_numeric_values_rejected(self):
        """Non-finite or non-positive prices and quantities must raise ValueError."""
        # Entry
        for bad_entry in [0.0, -10.0, float("nan"), float("inf"), float("-inf")]:
            t = Trade(direction="BULLISH", entry=bad_entry, stop_loss=95.0, quantity=1.0)
            with self.assertRaises(ValueError):
                t.validate_executable()

        # Stop loss
        for bad_sl in [0.0, -5.0, float("nan"), float("inf"), float("-inf")]:
            t = Trade(direction="BULLISH", entry=100.0, stop_loss=bad_sl, quantity=1.0)
            with self.assertRaises(ValueError):
                t.validate_executable()

        # Quantity
        for bad_qty in [0.0, -1.0, float("nan"), float("inf")]:
            t = Trade(direction="BULLISH", entry=100.0, stop_loss=95.0, quantity=bad_qty)
            with self.assertRaises(ValueError):
                t.validate_executable()

        # Risk amount
        for bad_risk in [-1.0, float("nan"), float("inf")]:
            t = Trade(
                direction="BULLISH",
                entry=100.0,
                stop_loss=95.0,
                quantity=1.0,
                risk_amount=bad_risk,
            )
            with self.assertRaises(ValueError):
                t.validate_executable()

        # Take profit
        for bad_tp in [-1.0, float("nan"), float("inf")]:
            t = Trade(
                direction="BULLISH",
                entry=100.0,
                stop_loss=95.0,
                quantity=1.0,
                take_profit=bad_tp,
            )
            with self.assertRaises(ValueError):
                t.validate_executable()

    def test_zero_risk_distance_trailing_stop_rejected(self):
        """Zero stop distance (entry == stop_loss) cannot calculate R-multiples for TRAILING_STOP."""
        t = Trade(
            direction="BULLISH",
            entry=100.0,
            stop_loss=100.0,
            quantity=1.0,
            exit_mode="TRAILING_STOP",
            trailing_enabled=True,
            trailing_activation_r=1.0,
            trailing_distance_r=0.5,
        )
        with self.assertRaises(ValueError) as ctx:
            t.validate_executable()
        self.assertIn("stop distance is zero", str(ctx.exception))

    def test_inconsistent_target_stop_geometry_rejected(self):
        """Inconsistent stop/target geometry fails closed."""
        # BULLISH stop loss above entry
        t1 = Trade(direction="BULLISH", entry=100.0, stop_loss=105.0, quantity=1.0)
        with self.assertRaises(ValueError) as ctx1:
            t1.validate_executable()
        self.assertIn("Inconsistent BULLISH geometry", str(ctx1.exception))

        # BULLISH take profit below or equal to entry
        t2 = Trade(direction="BULLISH", entry=100.0, stop_loss=95.0, take_profit=98.0, quantity=1.0)
        with self.assertRaises(ValueError) as ctx2:
            t2.validate_executable()
        self.assertIn("Inconsistent BULLISH geometry", str(ctx2.exception))

        # BEARISH stop loss below entry
        t3 = Trade(direction="BEARISH", entry=100.0, stop_loss=95.0, quantity=1.0)
        with self.assertRaises(ValueError) as ctx3:
            t3.validate_executable()
        self.assertIn("Inconsistent BEARISH geometry", str(ctx3.exception))

        # BEARISH take profit above or equal to entry
        t4 = Trade(direction="BEARISH", entry=100.0, stop_loss=105.0, take_profit=102.0, quantity=1.0)
        with self.assertRaises(ValueError) as ctx4:
            t4.validate_executable()
        self.assertIn("Inconsistent BEARISH geometry", str(ctx4.exception))

    def test_trailing_stop_invariants(self):
        """Trailing stop requires trailing_enabled and positive activation and distance."""
        # trailing_enabled=False with TRAILING_STOP
        t1 = Trade(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,
            quantity=1.0,
            exit_mode="TRAILING_STOP",
            trailing_enabled=False,
            trailing_activation_r=1.0,
            trailing_distance_r=0.5,
        )
        with self.assertRaises(ValueError) as ctx:
            t1.validate_executable()
        self.assertIn("trailing_enabled is False", str(ctx.exception))

        # trailing_activation_r <= 0
        t2 = Trade(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,
            quantity=1.0,
            exit_mode="TRAILING_STOP",
            trailing_enabled=True,
            trailing_activation_r=0.0,
            trailing_distance_r=0.5,
        )
        with self.assertRaises(ValueError) as ctx:
            t2.validate_executable()
        self.assertIn("trailing_activation_r must be > 0", str(ctx.exception))

        # trailing_distance_r <= 0
        t3 = Trade(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,
            quantity=1.0,
            exit_mode="TRAILING_STOP",
            trailing_enabled=True,
            trailing_activation_r=1.0,
            trailing_distance_r=0.0,
        )
        with self.assertRaises(ValueError) as ctx:
            t3.validate_executable()
        self.assertIn("trailing_distance_r must be > 0", str(ctx.exception))

    def test_trailing_stop_initial_stop_loss_stability(self):
        """initial_stop_loss remains unchanged while stop_loss trails,

        guaranteeing initial risk calculation remains stable.
        """
        sim = TradeSimulator()
        setup = SetupCandidate(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,
            take_profit=0.0,
            exit_mode="TRAILING_STOP",
            trailing_enabled=True,
            trailing_activation_r=1.0,
            trailing_distance_r=0.5,
        )
        trade = sim.open_trade(setup, timestamp=100)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.initial_stop_loss, 90.0)
        self.assertEqual(trade.stop_loss, 90.0)

        # Candle 1: moves up by 15 (> 1.0 R = 10 activation). Close = 115.
        # Trailing stop should advance to 115 - (0.5 * 10) = 110.0
        c1 = DummyCandle(high=116.0, low=98.0, close=115.0, timestamp=101)
        sim.update(c1)

        self.assertEqual(trade.status, "OPEN")
        self.assertEqual(trade.stop_loss, 110.0)
        # Invariant: initial_stop_loss MUST remain at 90.0!
        self.assertEqual(trade.initial_stop_loss, 90.0)

        # Risk calculation using getattr remains strictly anchored to inception
        initial_risk = abs(trade.entry - getattr(trade, "initial_stop_loss", trade.stop_loss))
        self.assertEqual(initial_risk, 10.0)

    def test_setup_score_api_serialization(self):
        """setup_score is copied at open and serialized in API snapshots via asdict()."""
        sim = TradeSimulator()
        setup = SetupCandidate(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,
            take_profit=120.0,
            score=88.5,
            confidence=95.0,
        )
        trade = sim.open_trade(setup, timestamp=10)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.setup_score, 88.5)
        self.assertEqual(trade.confidence, 95.0)

        # Test generic dataclass serializer used by API server
        serialized = _json_safe(asdict(trade))
        self.assertIn("setup_score", serialized)
        self.assertEqual(serialized["setup_score"], 88.5)
        self.assertIn("confidence", serialized)
        self.assertEqual(serialized["confidence"], 95.0)

    def test_broker_engine_route_validation_failure(self):
        """BrokerEngine._route rejects orders with invalid trade parameters."""
        from core.live.broker_engine import BrokerEngine
        from unittest.mock import MagicMock

        mock_pipeline = MagicMock()
        mock_pipeline.context = MagicMock()
        mock_bus = MagicMock()
        mock_executor = MagicMock()

        engine = BrokerEngine(mock_pipeline, mock_bus, mock_executor, dry_run=True)
        candle = MagicMock(high=100.0, low=90.0, close=95.0, timestamp=1000)

        # Order with invalid direction
        bad_order = MagicMock(
            direction="INVALID",
            entry=100.0,
            stop_loss=90.0,
            take_profit=120.0,
            symbol="BTCUSD",
            quantity=1.0,
        )
        mock_pipeline.context.order = bad_order
        engine._route(candle)
        self.assertIsNone(engine._live_trade)


if __name__ == "__main__":
    unittest.main()
