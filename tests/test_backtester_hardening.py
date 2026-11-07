"""
====================================================

QuantEngine

Backtester Hardening Contract Tests

Run with:

    python -m unittest tests.test_backtester_hardening -v

Proves the event-driven Backtester keeps the account
ledger exactly consistent with the closed-trade
registry under deterministic, fabricated candles:

    1. Ledger identity: after any run,
       account.balance == starting_balance + sum(closed pnl)
       realized_pnl == balance - starting_balance
       total_trades == wins + losses == closed registry count.
    2. Exactly-once booking per closed trade, including re-entry
       on the cycle after a close and a bar-in-bar stop exit.
    3. Same-bar stop exit (entry bar also exits the trade).
    4. An order on the FINAL candle stays OPEN -- it is never
       force-closed at an imagined price (no lookahead).
    5. Empty runs are no-ops.
    6. Single-position first-wins determinism: a second order
       while a position is open is ignored.
    7. A cycle that closes more than one trade fails LOUDLY
       (the guard that replaced silent all()[-1] under-booking).

Stdlib only -- no network, no real pipeline.

====================================================
"""

import unittest
from unittest import mock

from config import risk_settings

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.order_intent import OrderIntent

from core.backtesting.trade import Trade
from core.backtesting.trade_registry import TradeRegistry

from core.backtesting.trade_simulator import TradeSimulator
from backtesting.backtester import Backtester


class Candle:

    def __init__(self, high, low, close, timestamp):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


class FakeEventBus:

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def publish(self, event):
        self.pipeline.on_candle(event)


class FakePipeline:

    def __init__(self, script):
        self.script = script
        self._idx = 0
        self.reset()

    def reset(self):
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST", timeframe="1m")
        self._idx = 0

    def on_candle(self, event):
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        order, signal = self.script.get(self._idx, (None, None))
        self.context.order = order
        self.context.execution_signal = signal
        self._idx += 1


# Phase 12: scripted legacy-path orders must satisfy the
# same mandatory gates as production orders (directional
# geometry + R:R >= 6). stop 98.5 / tp 110 gives
# 10 / 1.5 = 6.67:1, so the ledger mechanics below are
# exercised through the gated path, not around it. A
# sub-6:1 injected order must NOT fill (proven by the new
# LEGACY_FILL_BLOCKED_* regression tests).
def order(
    entry=100.0,
    stop=98.5,
    tp=110.0,
    quantity=1.0,
):
    return OrderIntent(
        direction="BULLISH",
        entry=entry,
        stop_loss=stop,
        take_profit=tp,
        quantity=quantity,
        commission=0.0,
        slippage=0.0,
        confidence=85.0,
        score=85.0,
        symbol="TEST",
        valid=True,
    )


# A candle that cannot exit its band -> keeps any position
# with entry 100 / stop 95 / tp 110 OPEN.
SAFE = dict(high=105.0, low=99.0, close=102.0)

EXIT_WIN = dict(high=112.0, low=101.0, close=111.0)

EXIT_LOSS = dict(high=100.0, low=85.0, close=88.0)


class TestBacktesterLedgerHardening(unittest.TestCase):

    def setUp(self):
        # Phase 5C/D: these raw-lead contracts drive mode-less
        # OrderIntents through the backtester's canonical LIMIT
        # baseline channel. With BREAKOUT_CONTINUATION the active
        # production default, the run must DECLARE its mode
        # explicitly instead of relying on a silent config default.
        patcher = mock.patch.object(
            risk_settings, "ACTIVE_ENTRY_MODES", ("LIMIT_RETEST",)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, candles, script, simulator=None):
        pipeline = FakePipeline(script)
        event_bus = FakeEventBus(pipeline)
        simulator = simulator or TradeSimulator()
        backtester = Backtester(pipeline, event_bus, simulator)
        backtester.run(candles)
        return backtester, simulator

    def test_ledger_identity_across_win_loss_win(self):
        # WIN +10, LOSS -1.5, WIN +10 -> balance 2018.5.
        # (Phase 12: stop 98.5 keeps the 1:6 gate green;
        # the loss leg exits at the stop, 98.5.)
        candles = [
            Candle(**SAFE, timestamp=0),
            Candle(**EXIT_WIN, timestamp=1),
            Candle(**SAFE, timestamp=2),
            Candle(**EXIT_LOSS, timestamp=3),
            Candle(**SAFE, timestamp=4),
            Candle(**EXIT_WIN, timestamp=5),
        ]
        script = {
            0: (order(), None),
            2: (order(stop=98.5, tp=115.0), None),
            4: (order(), None),
        }

        backtester, simulator = self._run(candles, script)

        self.assertEqual(simulator.registry.count(), 3)

        account = backtester.account
        self.assertAlmostEqual(account.balance, 2018.5, places=6)
        self.assertAlmostEqual(account.equity, 2018.5, places=6)
        self.assertAlmostEqual(account.state.realized_pnl, 18.5, places=6)
        self.assertEqual(account.state.total_trades, 3)
        self.assertEqual(account.state.winning_trades, 2)
        self.assertEqual(account.state.losing_trades, 1)

        # Every registered trade is closed, exactly once.
        closed = simulator.registry.all()
        self.assertTrue(all(t.status == "CLOSED" for t in closed))
        self.assertEqual([t.exit_price for t in closed], [110.0, 98.5, 110.0])
        self.assertEqual([t.pnl for t in closed], [10.0, -1.5, 10.0])

        # Ledger identity: balance == starting + sum(closed pnl).
        total = sum(t.pnl for t in closed)
        self.assertAlmostEqual(
            account.balance, account.state.starting_balance + total, places=6
        )
        self.assertAlmostEqual(
            account.state.realized_pnl,
            account.balance - account.state.starting_balance,
            places=6,
        )

    def test_reentry_after_close_books_both_exactly_once(self):
        # Execution precedes the bar's exit check, so an order is
        # only actionable the cycle AFTER a close (no same-cycle
        # close+reopen). Candle 2 both opens B and stops it out
        # bar-in-bar; both A and B must be booked exactly once.
        candles = [
            Candle(**SAFE, timestamp=0),
            Candle(**EXIT_WIN, timestamp=1),
            Candle(**EXIT_LOSS, timestamp=2),
        ]
        script = {
            0: (order(), None),
            2: (order(stop=98.5, tp=115.0), None),
        }

        backtester, simulator = self._run(candles, script)

        self.assertEqual(simulator.registry.count(), 2)
        a, b = simulator.registry.all()
        self.assertEqual(a.result, "WIN")
        self.assertEqual(a.exit_time, 1)
        self.assertEqual(b.entry_time, 2)
        self.assertEqual(b.exit_time, 2)
        self.assertEqual(b.bars_held, 1)
        self.assertEqual(b.result, "LOSS")
        # +10 booked on cycle 1, -1.5 booked on cycle 2.
        self.assertAlmostEqual(backtester.account.balance, 2008.5, places=6)
        self.assertEqual(backtester.account.state.total_trades, 2)
        self.assertEqual(backtester.account.state.winning_trades, 1)
        self.assertEqual(backtester.account.state.losing_trades, 1)

    def test_same_bar_stop_exit_books_immediately(self):
        candle = Candle(high=105.0, low=80.0, close=95.0, timestamp=0)

        backtester, simulator = self._run(
            [candle], {0: (order(stop=98.5), None)}
        )

        trade = simulator.registry.all()[0]
        self.assertEqual(trade.status, "CLOSED")
        self.assertEqual(trade.result, "LOSS")
        self.assertEqual(trade.exit_price, 98.5)
        self.assertEqual(trade.exit_time, 0)
        self.assertEqual(trade.bars_held, 1)
        self.assertAlmostEqual(trade.pnl, -1.5, places=6)
        self.assertAlmostEqual(backtester.account.balance, 1998.5, places=6)
        self.assertEqual(backtester.account.state.losing_trades, 1)

    def test_final_candle_entry_stays_open_not_force_closed(self):
        candle = Candle(**SAFE, timestamp=0)

        backtester, simulator = self._run(
            [candle], {0: (order(), None)}
        )

        self.assertEqual(simulator.registry.count(), 0)
        self.assertIsNotNone(simulator.current_trade)
        self.assertEqual(simulator.current_trade.status, "OPEN")
        self.assertEqual(simulator.current_trade.bars_held, 1)
        # No imaginary exit: account untouched.
        self.assertAlmostEqual(backtester.account.balance, 2000.0, places=6)
        self.assertEqual(backtester.account.state.total_trades, 0)

    def test_empty_run_is_a_noop(self):
        backtester, simulator = self._run([], {})

        self.assertEqual(backtester.total_bars, 0)
        self.assertEqual(simulator.registry.count(), 0)
        self.assertAlmostEqual(backtester.account.balance, 2000.0, places=6)
        self.assertEqual(backtester.account.state.total_trades, 0)

    def test_order_every_candle_never_breaches_single_position(self):
        candles = [
            Candle(**SAFE, timestamp=0),
            Candle(**SAFE, timestamp=1),
            Candle(**SAFE, timestamp=2),
            Candle(**SAFE, timestamp=3),
            Candle(**EXIT_WIN, timestamp=4),
        ]
        # A competing order on EVERY candle while a position is
        # open must be ignored (first-wins determinism).
        script = {i: (order(), None) for i in range(5)}

        _, simulator = self._run(candles, script)

        self.assertEqual(simulator.registry.count(), 1)
        trade = simulator.registry.all()[0]
        self.assertEqual(trade.entry_time, 0)
        self.assertEqual(trade.exit_time, 4)
        self.assertEqual(trade.status, "CLOSED")


class TestBacktesterMultiCloseGuard(unittest.TestCase):

    def test_two_closes_in_one_cycle_fails_loudly(self):

        class DoubleClosingSimulator:

            def __init__(self):
                self.registry = TradeRegistry()
                self.current_trade = None

            def reset(self):
                self.registry.clear()
                self.current_trade = None

            def open_trade(self, *args, **kwargs):
                pass

            def update(self, candle):
                self.registry.add(
                    Trade(entry=100.0, pnl=10.0, status="CLOSED")
                )
                self.registry.add(
                    Trade(entry=100.0, pnl=-10.0, status="CLOSED")
                )

        pipeline = FakePipeline({})
        event_bus = FakeEventBus(pipeline)
        backtester = Backtester(
            pipeline, event_bus, DoubleClosingSimulator()
        )

        with self.assertRaises(RuntimeError):
            backtester.run(
                [Candle(**SAFE, timestamp=0)]
            )


if __name__ == "__main__":
    unittest.main()