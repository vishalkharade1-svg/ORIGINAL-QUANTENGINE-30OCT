"""
====================================================

QuantEngine

BrokerEngine (Live Trading) Contract Tests

Run with:

    python -m unittest tests.test_broker_engine -v

Proves the live BrokerEngine:

DRY-RUN (default, ZERO exchange writes):
    1. A valid OrderIntent is recorded on `placed` and opened
       through the SAME TradeSimulator used by the backtester;
       the executor is NEVER called.
    2. Ledger identity via paper-style candle exits mirrors the
       Backtester math exactly.
    3. Single-position first-wins: an order while a position is
       open is ignored.
    4. The pipeline is driven BEFORE the route (explicit drive,
       pipeline-first ordering).
    5. The broker's live account state is published into the
       pipeline context for RiskEngine sizing.
    6. reset() returns to a clean state.

LIVE (dry_run=False, fake recording executor):
    7. execute() is called exactly once per routed intent; the
       order id is captured from the exchange envelope and the
       open live trade is exposed.
    8. A position that vanishes (bracket fill wheels flat) books
       ONE close: a Trade lands in the registry with the
       exchange-reported exit price / realized P&L, and the
       account is updated exactly once.
    9. A rejected order is refused without opening a position.
   10. The open-order watch clears a cancelled / expired order
       so it never blocks reuse.
   11. Equity is re-synced from the exchange ledger.
   12. subscribe() registers the CandleEvent callback.

Stdlib only -- no network, no real pipeline.

====================================================
"""

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.order_intent import OrderIntent

from core.backtesting.trade_simulator import TradeSimulator

from core.events.candle_event import CandleEvent
from core.events.event_types import EventType

from core.live.broker_engine import BrokerEngine


class Candle:

    def __init__(self, high, low, close, timestamp):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


class FakePipeline:

    def __init__(self, script=None):
        self.script = script or {}
        self._idx = 0
        self.drives = 0
        self.reset()

    def reset(self):
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST", timeframe="1m")
        self._idx = 0

    def on_candle(self, event):
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.context.order = self.script.get(self._idx, None)
        self._idx += 1
        self.drives += 1


class FakeExecutor:

    def __init__(
        self,
        positions=None,
        balance=None,
        order=None,
        success=True,
        order_id="QE-LIVE-1",
    ):
        self.calls = []
        self._positions = positions or []
        self._balance = balance if balance is not None else {}
        self._order = order if order is not None else {}
        self._success = success
        self._order_id = order_id

    def execute(self, intent):
        self.calls.append(("execute", intent.symbol))
        if not self._success:
            return {"success": False, "reason": "risk gate"}
        return {
            "success": True,
            "intent": intent,
            "contract": type(
                "C", (), {"product_id": 2}
            )(),
            "response": {
                "result": {
                    "id": self._order_id,
                    "status": "open",
                }
            },
        }

    def fetch(self, order_id):
        self.calls.append(("fetch", order_id))
        return self._order

    def cancel(self, order_id):
        self.calls.append(("cancel", order_id))
        return {}

    def balance(self):
        self.calls.append(("balance",))
        return self._balance

    def positions(self):
        self.calls.append(("positions",))
        return self._positions


def order(
    entry=100.0,
    stop=90.0,
    tp=170.0,
    quantity=1.0,
    direction="BULLISH",
    commission=0.0,
    slippage=0.0,
):
    # Phase-14 maintenance: gate-compliant economics (gross RR
    # (170-100)/10 = 7.0 >= 6, zero costs so the post-cost layer
    # is vacuous), because BrokerEngine._route now enforces the
    # mandatory geometry + gross-RR + post-cost gates on dry AND
    # live paths — a hand-fed sub-6 order must never route, exactly
    # as RiskEngine would refuse it. Plumbing intent of every test
    # below is unchanged; only the fixture economics moved.
    return OrderIntent(
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=tp,
        quantity=quantity,
        commission=commission,
        slippage=slippage,
        confidence=85.0,
        score=85.0,
        symbol="TEST",
        valid=True,
    )


SAFE = dict(high=105.0, low=99.0, close=102.0)

# Phase-14 maintenance: EXIT_WIN reaches the gate-compliant target
# (high 172 >= tp 170); the SL band is untouched.
EXIT_WIN = dict(high=172.0, low=101.0, close=171.0)

EXIT_LOSS = dict(high=100.0, low=85.0, close=88.0)


class TestBrokerEngineDryRun(unittest.TestCase):

    def _engine(self, script, candles, **kwargs):
        pipeline = FakePipeline(script)
        executor = FakeExecutor()
        engine = BrokerEngine(
            pipeline,
            event_bus=None,
            executor=executor,
            **kwargs,
        )
        for candle in candles:
            engine.run_candle(candle)
        return engine, pipeline, executor

    def test_valid_order_routed_dry_without_exchange_calls(self):

        engine, _, executor = self._engine(
            {0: order()},
            [Candle(**SAFE, timestamp=1)],
        )

        self.assertIsNotNone(engine.current_trade)

        self.assertEqual(engine.total_bars, 1)

        # Recorded as a would-be intent, never written.
        self.assertEqual(len(engine.placed), 1)

        self.assertEqual(len(executor.calls), 0)

    def test_no_order_produced_is_never_routed(self):

        engine, _, executor = self._engine(
            {},
            [Candle(**SAFE, timestamp=1)],
        )

        self.assertIsNone(engine.current_trade)

        self.assertEqual(engine.placed, [])

        self.assertEqual(len(executor.calls), 0)

    def test_paper_style_exit_books_shared_registry(self):

        scripts = {0: order(), 2: order(), 4: order()}

        engine, _, _ = self._engine(
            scripts,
            [
                Candle(**SAFE, timestamp=1),
                Candle(**EXIT_WIN, timestamp=2),
                Candle(**SAFE, timestamp=3),
                Candle(**EXIT_LOSS, timestamp=4),
                Candle(**SAFE, timestamp=5),
                Candle(**EXIT_WIN, timestamp=6),
            ],
        )

        self.assertEqual(engine.registry.count(), 3)

        # Phase-14 maintenance: TP exits now book at the compliant
        # target (170-100 = 70); the SL leg (-10) is unchanged.
        self.assertEqual(
            [t.pnl for t in engine.completed_trades],
            [70.0, -10.0, 70.0],
        )

        state = engine.account.state

        self.assertAlmostEqual(state.balance, 2130.0, places=6)

        self.assertAlmostEqual(
            state.balance,
            state.starting_balance + sum(
                t.pnl for t in engine.completed_trades
            ),
            places=6,
        )

        self.assertEqual(engine.completed_trades, engine.trades.all())

    def test_single_position_first_wins(self):

        scripts = {0: order(), 1: order()}

        engine, _, _ = self._engine(
            scripts,
            [
                Candle(**SAFE, timestamp=1),
                Candle(**SAFE, timestamp=2),
            ],
        )

        self.assertEqual(engine.registry.count(), 0)

        self.assertIsNotNone(engine.current_trade)

        self.assertEqual(engine.current_trade.entry, 100.0)

    def test_pipeline_driven_before_route(self):

        engine, pipeline, _ = self._engine(
            {0: order()},
            [Candle(**SAFE, timestamp=1)],
        )

        self.assertEqual(pipeline.drives, 1)

        self.assertIsNotNone(engine.current_trade)

    def test_live_account_state_published_into_context(self):

        engine, pipeline, _ = self._engine(
            {0: order()},
            [Candle(**SAFE, timestamp=1)],
        )

        self.assertIs(pipeline.context.account, engine.account.state)

    def test_reset_returns_to_clean_state(self):

        scripts = {0: order(), 2: order()}

        engine, _, _ = self._engine(
            scripts,
            [
                Candle(**EXIT_LOSS, timestamp=1),
                Candle(**SAFE, timestamp=2),
                Candle(**EXIT_WIN, timestamp=3),
            ],
        )

        self.assertEqual(engine.account.state.total_trades, 2)

        engine.reset()

        self.assertEqual(engine.processed_bars, 0)

        self.assertEqual(engine.registry.count(), 0)

        self.assertIsNone(engine.current_trade)

        self.assertEqual(engine.placed, [])

    def test_subscribe_registers_candle_callback(self):

        class FakeBus:

            def __init__(self):
                self.subs = {}

            def subscribe(self, event_type, callback):
                self.subs[event_type] = callback

        bus = FakeBus()

        pipeline = FakePipeline({0: order()})

        engine = BrokerEngine(
            pipeline,
            event_bus=bus,
            executor=FakeExecutor(),
        )

        engine.subscribe()

        self.assertIn(EventType.CANDLE, bus.subs)

        bus.subs[EventType.CANDLE](
            CandleEvent(
                candle=Candle(**SAFE, timestamp=1)
            )
        )

        self.assertIsNotNone(engine.current_trade)


class TestBrokerEngineLive(unittest.TestCase):

    def _positions(self, size, entry=100.0, **extra):
        record = {
            "product_id": 2,
            "size": size,
            "entry_price": entry,
        }
        record.update(extra)
        return {"result": [record]}

    def _engine(self, script, candles, executor, **kwargs):
        from core.execution.live_safety_gate import LiveSafetyGate

        # Offline live-path tests arm the Phase 11A gate
        # explicitly with a test token (fake transport --
        # never real settings/credentials). Production
        # arms via main.py from operator configuration.
        kwargs.setdefault(
            "safety", LiveSafetyGate.test_armed()
        )
        pipeline = FakePipeline(script)
        engine = BrokerEngine(
            pipeline,
            event_bus=None,
            executor=executor,
            dry_run=False,
            **kwargs,
        )
        for candle in candles:
            engine.run_candle(candle)
        return engine, pipeline

    def test_live_places_and_captures_order_id(self):

        executor = FakeExecutor(
            positions=self._positions(0.0)
        )

        engine, _ = self._engine(
            {0: order()},
            [Candle(**SAFE, timestamp=1)],
            executor,
        )

        self.assertEqual(
            executor.calls.count(("execute", "TEST")),
            1,
        )

        self.assertIsNotNone(engine.current_trade)

        self.assertEqual(engine._open_order_id, "QE-LIVE-1")

        self.assertEqual(engine.placed[0]["success"], True)

    def test_live_close_books_once_with_exchange_pnl(self):

        # Candle 1: fresh boot is flat (verified-boot contract: an
        # exchange position with no local journal halts instead of
        # routing), the order fills locally. Candle 2: the exchange
        # shows the working position (visibility beat). Candle 3:
        # hit TP, bracket fills, the record is flat with the
        # exchange-realized P&L.
        executor = FakeExecutor(
            positions=self._positions(0.0)
        )

        engine, _ = self._engine(
            {0: order(quantity=0.062)},
            [Candle(**SAFE, timestamp=1)],
            executor,
        )

        self.assertEqual(engine.registry.count(), 0)

        executor._positions = self._positions(
            0.062,
            entry=100.0,
            realized_pnl=0.62,
        )

        engine.run_candle(Candle(**SAFE, timestamp=2))

        # Position flat now -- the close books exactly once.
        executor._positions = self._positions(
            0.0,
            entry=100.0,
            realized_pnl=0.62,
        )

        engine.run_candle(Candle(**EXIT_WIN, timestamp=3))

        self.assertEqual(engine.registry.count(), 1)

        close = engine.completed_trades[0]

        self.assertEqual(close.status, "CLOSED")

        self.assertEqual(close.result, "WIN")

        self.assertAlmostEqual(close.pnl, 0.62, places=6)

        self.assertEqual(close.exit_time, 3)

        self.assertEqual(close.entry, 100.0)

        # Booked profit exactly once, ledger identity holds.
        self.assertAlmostEqual(
            engine.account.balance,
            2000.0 + 0.62,
            places=6,
        )

        self.assertEqual(engine.account.state.total_trades, 1)

    def test_live_close_no_double_reentry_same_candle(self):

        # Fresh boot is flat; the working mirror appears on the
        # visibility beat (candle 2) before the flat close (candle
        # 3) so the verified-boot gate never trips on the harness.
        executor = FakeExecutor(
            positions=self._positions(0.0)
        )

        engine, _ = self._engine(
            {0: order(quantity=0.062)},
            [Candle(**SAFE, timestamp=1)],
            executor,
        )

        executor._positions = self._positions(
            0.062,
            entry=100.0,
        )

        engine.run_candle(Candle(**SAFE, timestamp=2))

        # Candle 3 closes the position via the exchange; a fresh
        # intent on the same candle must NOT reopen a position
        # because routing precedes the sync (mirrors backtest).
        engine.pipeline.script[2] = order(quantity=0.062)

        executor._positions = self._positions(0.0)

        engine.run_candle(Candle(**EXIT_WIN, timestamp=3))

        self.assertEqual(engine.registry.count(), 1)

        self.assertIsNone(engine.current_trade)

    def test_live_reentry_after_close_on_next_candle(self):

        # Fresh boot is flat (verified-boot contract); the working
        # mirror appears on the visibility beat (candle 2), the
        # close lands on candle 3, and the refill on candle 4.
        executor = FakeExecutor(
            positions=self._positions(0.0)
        )

        engine, _ = self._engine(
            {0: order(quantity=0.062)},
            [Candle(**SAFE, timestamp=1)],
            executor,
        )

        executor._positions = self._positions(
            0.062,
            entry=100.0,
            realized_pnl=-0.5,
        )

        engine.run_candle(Candle(**SAFE, timestamp=2))

        # Close on candle 3 (flat record).
        executor._positions = self._positions(
            0.0,
            realized_pnl=-0.5,
        )

        engine.run_candle(Candle(**EXIT_LOSS, timestamp=3))

        # Candle 4: fresh intent routes into a NEW live position.
        engine.pipeline.script[3] = order(quantity=0.062)

        executor._positions = self._positions(0.062, entry=100.0)

        engine.run_candle(Candle(**SAFE, timestamp=4))

        self.assertEqual(engine.registry.count(), 1)

        self.assertIsNotNone(engine.current_trade)

        self.assertEqual(
            executor.calls.count(("execute", "TEST")),
            2,
        )

    def test_live_rejected_order_opens_nothing(self):

        executor = FakeExecutor(
            success=False,
            positions=self._positions(0.0),
        )

        engine, _ = self._engine(
            {0: order()},
            [Candle(**SAFE, timestamp=1)],
            executor,
        )

        self.assertIsNone(engine.current_trade)

        self.assertEqual(engine.placed[0]["success"], False)

        self.assertEqual(engine.registry.count(), 0)

    def test_open_order_watch_clears_cancelled(self):

        executor = FakeExecutor(
            positions=self._positions(0.0),
            order={"result": {"status": "open"}},
        )

        engine, _ = self._engine(
            {0: order()},
            [Candle(**SAFE, timestamp=1)],
            executor,
        )

        # Order working but never a position: the watch keeps it.
        self.assertIsNotNone(engine._open_order_id)

        self.assertEqual(
            executor.calls.count(("fetch", "QE-LIVE-1")),
            1,
        )

        # Candle 2: the exchange reports the order cancelled --
        # the watch clears it so a later intent can route again.
        executor._order = {"result": {"status": "cancelled"}}

        engine.run_candle(Candle(**SAFE, timestamp=2))

        self.assertIsNone(engine._open_order_id)

        self.assertEqual(
            executor.calls.count(("fetch", "QE-LIVE-1")),
            2,
        )

    def test_live_equity_synced_from_exchange(self):

        executor = FakeExecutor(
            positions=self._positions(0.0, entry=100.0),
            balance={"total_equity": 1950.0},
        )

        engine, _ = self._engine(
            {},
            [Candle(**SAFE, timestamp=1)],
            executor,
        )

        self.assertAlmostEqual(
            engine.account.balance,
            1950.0,
            places=6,
        )

        self.assertIn(("balance",), executor.calls)


if __name__ == "__main__":
    unittest.main()