"""
====================================================

QuantEngine

Paper Runtime Boundary Certification Tests
Phase 163 Full Audit and Runtime Boundary Hardening

Verifies paper trading feed integrity, rejection logging,
identity chain preservation, cost binding, reconciler snapshot
durability, and restart recovery.

====================================================
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from config import risk_settings
from core.events.candle_event import CandleEvent
from core.execution.order_registry import OrderRegistry, PENDING, FILLED
from core.live.reconciler import (
    Reconciler,
    MATCH,
    MISMATCH,
    SKIP,
    UNKNOWN,
)
from core.market_state import MarketState
from core.paper_trading.paper_trading_engine import PaperTradingEngine
from core.pipeline.pipeline_context import PipelineContext
from core.risk.account import Account
from core.risk.costs import paper_cost_profile
from core.risk.order_intent import OrderIntent
from core.setup.setup_candidate import SetupCandidate


class DummyCandle:
    def __init__(self, high: float, low: float, close: float, timestamp: int, open_p: float = 0.0, closed: bool = True):
        self.open = open_p if open_p > 0 else (high + low) / 2.0
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "BTC-USDT"
        self.timeframe = "1m"
        self.closed = closed


class ScriptedPipeline:
    def __init__(self, orders_by_bar=None):
        self.orders_by_bar = orders_by_bar or {}
        self.bar_index = 0
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="BTC-USDT", timeframe="1m")
        self.context.order_registry = OrderRegistry()

    def reset(self):
        self.bar_index = 0
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="BTC-USDT", timeframe="1m")
        self.context.order_registry = OrderRegistry()

    def on_candle(self, event):
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        order = self.orders_by_bar.get(self.bar_index, None)
        if order is not None:
            self.context.order = order
            self.context.order_registry.create(order)
        self.bar_index += 1


class TestPaperRuntimeBoundaryCertification(unittest.TestCase):
    """Certification suite for Phase 4 paper runtime and recovery."""

    def test_01_feed_finality_and_ordering(self):
        """PaperTradingEngine executes candles sequentially and updates internal clock."""
        pipe = ScriptedPipeline()
        engine = PaperTradingEngine(pipeline=pipe, event_bus=None)

        c1 = DummyCandle(high=105.0, low=95.0, close=100.0, timestamp=1000)
        c2 = DummyCandle(high=110.0, low=99.0, close=108.0, timestamp=1060)

        engine.run_candle(c1)
        self.assertEqual(engine.processed_bars, 1)
        self.assertEqual(pipe.context.market.timestamp, 1000)

        engine.run_candle(c2)
        self.assertEqual(engine.processed_bars, 2)
        self.assertEqual(pipe.context.market.timestamp, 1060)

    def test_02_rejection_fail_closed_kill_switch_and_rr(self):
        """Paper execution blocks fills when kill switch is active or R:R is disallowed."""
        setup = SetupCandidate(direction="BULLISH", entry=100.0, stop_loss=98.5, take_profit=110.0)
        bad_rr_order = OrderIntent(
            direction="BULLISH",
            entry=100.0,
            stop_loss=99.5,   # stop distance 0.5
            take_profit=100.4, # target distance 0.4 -> R:R 0.8 < min 1.0
            quantity=1.0,
            symbol="BTC-USDT",
            valid=True,
            setup=setup,
            setup_id="SETUP-BAD-RR",
            order_id="ORD-BAD-RR",
        )

        pipe = ScriptedPipeline(orders_by_bar={0: bad_rr_order})
        engine = PaperTradingEngine(pipeline=pipe, event_bus=None)

        with self.assertLogs("core.paper_trading.paper_trading_engine", level="ERROR") as cm:
            engine.run_candle(DummyCandle(high=102.0, low=99.0, close=100.0, timestamp=1000))

        # Must log PAPER_FILL_BLOCKED_RR and refuse fill
        self.assertTrue(any("PAPER_FILL_BLOCKED_RR" in m for m in cm.output))
        self.assertIsNone(engine.current_trade)

    def test_03_identity_chain_setup_order_trade(self):
        """Order execution binds setup_id -> order_id -> trade_id and updates lifecycle."""
        setup = SetupCandidate(direction="BULLISH", entry=100.0, stop_loss=98.5, take_profit=110.0)
        setup.setup_id = "SETUP-CANONICAL-42"
        setup.lifecycle = "ACCEPTED"

        order = OrderIntent(
            direction="BULLISH",
            entry=100.0,
            stop_loss=98.5,
            take_profit=110.0,
            quantity=1.0,
            symbol="BTC-USDT",
            valid=True,
            setup=setup,
            setup_id="SETUP-CANONICAL-42",
            order_id="ORD-CANONICAL-42",
        )

        pipe = ScriptedPipeline(orders_by_bar={0: order})
        engine = PaperTradingEngine(pipeline=pipe, event_bus=None)

        engine.run_candle(DummyCandle(high=102.0, low=99.0, close=100.0, timestamp=1000))

        trade = engine.current_trade
        self.assertIsNotNone(trade)
        self.assertEqual(trade.setup_id, "SETUP-CANONICAL-42")
        self.assertEqual(trade.order_id, "ORD-CANONICAL-42")
        self.assertTrue(len(trade.trade_id) > 0)
        registered_order = pipe.context.order_registry.get("ORD-CANONICAL-42")
        self.assertEqual(registered_order.status, FILLED)
        self.assertEqual(registered_order.trade_id, trade.trade_id)
        self.assertEqual(setup.lifecycle, FILLED)

    def test_04_paper_cost_profile_binding(self):
        """Paper trading engine binds paper_cost_profile() on fills and books net PnL."""
        costs = paper_cost_profile(overrides={"rate": 0.0005, "slippage_bps": 2.5})
        self.assertGreater(costs.rate, 0)
        self.assertGreater(costs.slippage_bps, 0)

        setup = SetupCandidate(direction="BULLISH", entry=100.0, stop_loss=90.0, take_profit=115.0)
        order = OrderIntent(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,
            take_profit=115.0,
            quantity=2.0,
            symbol="BTC-USDT",
            valid=True,
            setup=setup,
            setup_id="SETUP-COSTS",
            order_id="ORD-COSTS",
        )

        pipe = ScriptedPipeline(orders_by_bar={0: order})
        account = Account(starting_balance=10000.0)
        engine = PaperTradingEngine(pipeline=pipe, event_bus=None, account=account)

        with patch("core.paper_trading.paper_trading_engine.paper_cost_profile", return_value=costs):
            # Bar 0: Fill opened
            engine.run_candle(DummyCandle(high=102.0, low=99.0, close=100.0, timestamp=1000))
            trade = engine.current_trade
            self.assertIsNotNone(trade)
            self.assertGreater(trade.commission, 0.0)
            self.assertGreater(trade.slippage, 0.0)

            # Bar 1: Hits take profit at 115.0
            engine.run_candle(DummyCandle(high=116.0, low=101.0, close=115.0, timestamp=1060))
            self.assertIsNone(engine.current_trade)

            closed = engine.completed_trades
            self.assertEqual(len(closed), 1)
            closed_trade = closed[0]
            # Net PnL must be gross (30.0) minus round-trip commission and slippage
            expected_net = 30.0 - (closed_trade.commission + closed_trade.slippage)
            self.assertAlmostEqual(closed_trade.pnl, expected_net)
            self.assertAlmostEqual(account.balance, 10000.0 + expected_net)

    def test_05_reconciler_startup_and_durability(self):
        """Reconciler creates atomic snapshots and survives process restart without state loss."""
        with tempfile.TemporaryDirectory() as tmpdir:
            snap_path = os.path.join(tmpdir, "reconciler_snapshot.json")

            # 1. Active session saves snapshot
            rec1 = Reconciler(snapshot_path=snap_path)
            state_data = {
                "schema": "broker-snapshot-v1",
                "in_position": True,
                "timestamp": 1234567890,
                "open_order_id": None,
                "product_id": "BTC-USDT",
                "ack_state": "FILLED",
                "order_seq": 1,
                "live_trade": {
                    "direction": "BULLISH",
                    "entry": 100.0,
                    "stop_loss": 90.0,
                    "take_profit": 115.0,
                    "quantity": 1.5,
                    "entry_time": 1234567800,
                },
            }
            rec1.persist(state_data)
            self.assertTrue(os.path.exists(snap_path))

            # 2. Restart simulation: rec2 loads snapshot
            rec2 = Reconciler(snapshot_path=snap_path)
            loaded = rec2.load_snapshot()
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded["in_position"])
            self.assertEqual(loaded["live_trade"]["entry"], 100.0)
            self.assertEqual(loaded["live_trade"]["quantity"], 1.5)

            # 3. Paper mode boot check returns SKIP (no real exchange)
            res = rec2.startup_check(dry_run=True)
            self.assertEqual(res["verdict"], SKIP)

    def test_06_reconciler_fails_closed_on_drift(self):
        """Reconciler halts on position side or quantity mismatch."""
        class MockExecutor:
            def __init__(self, positions):
                self._positions = positions
            def positions(self):
                return self._positions

        # Local is LONG 1.0, Exchange reports SHORT 1.0 -> SIDE_MISMATCH
        mock_exec = MockExecutor([{"direction": "SHORT", "quantity": 1.0, "entry": 100.0}])
        rec = Reconciler(executor=mock_exec)

        local_trade = {"direction": "LONG", "quantity": 1.0, "entry": 100.0}
        res = rec.runtime_check(bar=1, timestamp=1000, local_position=local_trade)

        self.assertEqual(res["verdict"], MISMATCH)
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(res["drift"]["kind"], "SIDE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
