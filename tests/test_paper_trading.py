"""
====================================================

QuantEngine

Paper Trading Engine Contract Tests

Run with:

    python -m unittest tests.test_paper_trading -v

Proves the feed-driven PaperTradingEngine shares the
canonical Backtester execution flow exactly:

    1. Valid OrderIntent -> paper fill with the intent's
       quantity / commission / slippage.
    2. Invalid / missing orders are never filled.
    3. Ledger identity: after any run,
       account.balance == starting_balance + sum(closed pnl),
       realized_pnl == balance - starting_balance,
       total_trades == wins + losses == closed registry count.
    4. Exactly-once booking per closed trade, including
       re-entry on a later candle and same-bar stop exit.
    5. Single-position first-wins determinism: an order while
       a position is already open is ignored.
    6. The pipeline is driven BEFORE the fill (the engine
       observes the order only because its explicit
       pipeline.on_candle drove RiskEngine that cycle).
    7. The paper account's live state is published into the
       pipeline context, so RiskEngine sizes from it.
    8. Opt-in fill_slippage_bps: buys fill worse (entry + bps),
       sells fill worse (entry - bps); stops/targets unchanged.
    9. Opt-in mark_to_market: equity moves with the open
       trade's floating P&L, net of commission + slippage.
   10. subscribe() registers the CandleEvent callback and
       drives a fill off a live-style event.
   11. reset() returns the engine to a clean state.

Stdlib only -- no network, no real pipeline.

====================================================
"""

import unittest
from unittest.mock import patch

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.order_intent import OrderIntent

from core.backtesting.trade_simulator import TradeSimulator

from core.events.candle_event import CandleEvent
from core.events.event_types import EventType

from core.paper_trading.paper_trading_engine import (
    PaperTradingEngine,
)


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


# Phase 12: stop 98.5 keeps scripted paper fills inside
# the mandatory gates (10 / 1.5 = 6.67:1); loss legs exit
# at 98.5 (-1.5), win legs at 110 (+10) unchanged.
def order(
    entry=100.0,
    stop=98.5,
    tp=110.0,
    quantity=1.0,
    direction="BULLISH",
    commission=0.0,
    slippage=0.0,
):
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


# A candle that cannot exit a 100/95SL/110TP band.
SAFE = dict(high=105.0, low=99.0, close=102.0)

EXIT_WIN = dict(high=112.0, low=101.0, close=111.0)

EXIT_LOSS = dict(high=100.0, low=85.0, close=88.0)


class TestPaperTradingEngine(unittest.TestCase):

    def setUp(self):
        # These legacy contract tests exercise fixed-target mechanics.
        # Runtime production policy defaults to trailing-enabled; disable
        # it only inside this fixture so assertions about historical
        # fixed-target bookkeeping remain exact. Dedicated policy tests
        # cover the default trailing behavior.
        from core.risk.trading_policy import trading_policy_manager, TradingPolicy
        self._policy_manager = trading_policy_manager()
        self._saved_global_policy = self._policy_manager._global
        self._policy_manager._global = TradingPolicy(
            min_rr=self._saved_global_policy.min_rr,
            max_rr=self._saved_global_policy.max_rr,
            trailing_enabled=False,
            trailing_activation_r=self._saved_global_policy.trailing_activation_r,
            trailing_distance_r=self._saved_global_policy.trailing_distance_r,
            auto_exit_on_opposite_signal=self._saved_global_policy.auto_exit_on_opposite_signal,
        )

    def tearDown(self):
        self._policy_manager._global = self._saved_global_policy

    def _engine(
        self,
        script,
        candles,
        account=None,
        **kwargs,
    ):
        pipeline = FakePipeline(script)
        engine = PaperTradingEngine(
            pipeline,
            event_bus=None,
            account=account,
            **kwargs,
        )
        for candle in candles:
            engine.run_candle(candle)
        return engine, pipeline

    # --------------------------------------------------
    # Fill semantics
    # --------------------------------------------------

    def test_valid_order_fills_with_intent_terms(self):
        # Phase-13 maintenance: gate-compliant target (costs 1+2 on
        # qty 1.5 shift the entry to 101.0: 15.0/2.5 = 6.0, the
        # inclusive boundary), so the mandatory post-cost R:R gate
        # admits the fill. Fill-terms intent unchanged.

        intent = order(quantity=1.5, commission=1.0, slippage=2.0,
                       tp=116.0)

        from core.risk.costs import CostSpec
        with patch(
            "core.paper_trading.paper_trading_engine.paper_cost_profile",
            return_value=CostSpec(per_trade=1.0, rate=0.0, slippage_bps=66.66666666666667),
        ):
            engine, _ = self._engine(
                {0: intent},
                [Candle(**SAFE, timestamp=1)],
            )

        trade = engine.current_trade

        self.assertIsNotNone(trade)

        self.assertEqual(trade.direction, "BULLISH")

        self.assertEqual(trade.entry, intent.entry)

        self.assertEqual(trade.quantity, 1.5)

        self.assertEqual(trade.commission, 1.0)

        self.assertEqual(trade.slippage, 2.0)

        self.assertEqual(engine.processed_bars, 1)

    def test_no_order_produced_is_never_filled(self):

        engine, _ = self._engine(
            {},
            [
                Candle(**SAFE, timestamp=1),
                Candle(**SAFE, timestamp=2),
            ],
        )

        self.assertIsNone(engine.current_trade)

        self.assertEqual(engine.trades.count(), 0)

    def test_order_does_not_reopen_on_future_candles(self):

        intent = order()

        engine, _ = self._engine(
            {0: intent},
            [
                Candle(**SAFE, timestamp=1),
                Candle(**SAFE, timestamp=2),
                Candle(**SAFE, timestamp=3),
            ],
        )

        self.assertIsNotNone(engine.current_trade)

        self.assertEqual(engine.trades.count(), 0)

    # --------------------------------------------------
    # Ledger identity (same math as the Backtester)
    # --------------------------------------------------

    def test_ledger_identity_win_loss_win(self):

        scripts = {0: order(), 2: order(), 4: order()}

        engine, _ = self._engine(
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

        self.assertEqual(engine.trades.count(), 3)

        state = engine.account.state

        self.assertAlmostEqual(state.balance, 2018.5, places=6)

        self.assertAlmostEqual(state.equity, 2018.5, places=6)

        self.assertAlmostEqual(state.realized_pnl, 18.5, places=6)

        self.assertEqual(state.total_trades, 3)

        self.assertEqual(state.winning_trades, 2)

        self.assertEqual(state.losing_trades, 1)

        closed = engine.completed_trades

        self.assertTrue(
            all(t.status == "CLOSED" for t in closed)
        )

        self.assertEqual(
            [t.pnl for t in closed],
            [10.0, -1.5, 10.0],
        )

        # Ledger identity: balance == starting + sum(closed pnl).
        self.assertAlmostEqual(
            state.balance,
            state.starting_balance + sum(t.pnl for t in closed),
            places=6,
        )

        self.assertAlmostEqual(
            state.realized_pnl,
            state.balance - state.starting_balance,
            places=6,
        )

    def test_win_books_profit_and_loss_books_loss(self):

        engine_win, _ = self._engine(
            {0: order()},
            [Candle(**EXIT_WIN, timestamp=1)],
        )

        self.assertAlmostEqual(
            engine_win.account.balance,
            2010.0,
            places=6,
        )

        engine_loss, _ = self._engine(
            {0: order()},
            [Candle(**EXIT_LOSS, timestamp=1)],
        )

        self.assertAlmostEqual(
            engine_loss.account.balance,
            1998.5,
            places=6,
        )

    def test_same_bar_stop_exit_books_exactly_once(self):

        same_bar = dict(high=112.0, low=85.0, close=100.0)

        engine, _ = self._engine(
            {0: order()},
            [Candle(**same_bar, timestamp=1)],
        )

        self.assertIsNone(engine.current_trade)

        self.assertEqual(engine.trades.count(), 1)

        self.assertEqual(engine.trades.all()[0].result, "LOSS")

        self.assertEqual(engine.account.state.losing_trades, 1)

    def test_reentry_on_later_candle_after_close(self):

        scripts = {0: order(), 3: order()}

        engine, _ = self._engine(
            scripts,
            [
                Candle(**EXIT_LOSS, timestamp=1),
                Candle(**SAFE, timestamp=2),
                Candle(**SAFE, timestamp=3),
                Candle(**EXIT_WIN, timestamp=4),
            ],
        )

        self.assertEqual(engine.trades.count(), 2)

        self.assertEqual(engine.account.state.total_trades, 2)

        self.assertEqual(
            [t.result for t in engine.completed_trades],
            ["LOSS", "WIN"],
        )

    def test_second_order_while_position_open_is_ignored(self):

        scripts = {0: order(), 1: order(entry=101.0, stop=99.5, tp=111.0)}

        engine, _ = self._engine(
            scripts,
            [
                Candle(**SAFE, timestamp=1),
                Candle(**SAFE, timestamp=2),
            ],
        )

        self.assertEqual(engine.completed_trades, [])

        self.assertIsNotNone(engine.current_trade)

        self.assertEqual(engine.current_trade.entry, 100.0)

    def test_account_can_bleed_down_below_starting_balance(self):

        scripts = {0: order(), 2: order(), 4: order()}

        engine, _ = self._engine(
            scripts,
            [
                Candle(**EXIT_LOSS, timestamp=1),
                Candle(**SAFE, timestamp=2),
                Candle(**EXIT_LOSS, timestamp=3),
                Candle(**SAFE, timestamp=4),
                Candle(**EXIT_LOSS, timestamp=5),
                Candle(**SAFE, timestamp=6),
            ],
        )

        self.assertAlmostEqual(
            engine.account.balance,
            1995.5,
            places=6,
        )

        self.assertEqual(
            engine.account.state.losing_trades,
            3,
        )

    # --------------------------------------------------
    # Pipeline-first ordering
    # --------------------------------------------------

    def test_pipeline_driven_before_fill(self):

        engine, pipeline = self._engine(
            {0: order()},
            [Candle(**SAFE, timestamp=1)],
        )

        # The engine drove the pipeline exactly once for the
        # single candle, and a fill only happened because that
        # explicit drive produced the OrderIntent that cycle.
        self.assertEqual(pipeline.drives, 1)

        self.assertIsNotNone(engine.current_trade)

    def test_live_account_state_published_into_context(self):

        engine, pipeline = self._engine(
            {0: order()},
            [Candle(**SAFE, timestamp=1)],
        )

        # RiskEngine sizes from exactly the paper account state:
        # a paper loss later must lower the equity that the next
        # cycle's sizing reads.
        self.assertIs(
            pipeline.context.account,
            engine.account.state,
        )

    def test_reset_returns_to_clean_state(self):

        scripts = {0: order(), 2: order()}

        engine, _ = self._engine(
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

        self.assertEqual(engine.trades.count(), 0)

        self.assertIsNone(engine.current_trade)

        self.assertEqual(
            engine.account.balance,
            engine.account.state.starting_balance,
        )

    # --------------------------------------------------
    # Opt-in paper realism
    # --------------------------------------------------

    def test_fill_slippage_bps_worsens_buy_entry(self):

        intent = order(entry=100.0)

        engine, _ = self._engine(
            {0: intent},
            [Candle(**SAFE, timestamp=1)],
            fill_slippage_bps=10.0,
        )

        # 100 + 100 * 10 / 10000 = 100.10
        self.assertAlmostEqual(
            engine.current_trade.entry,
            100.1,
            places=6,
        )

        # Stops / targets stay at the intent's levels.
        self.assertEqual(
            engine.current_trade.stop_loss,
            intent.stop_loss,
        )

        self.assertEqual(
            engine.current_trade.take_profit,
            intent.take_profit,
        )

    def test_fill_slippage_bps_worsens_sell_entry(self):

        intent = order(
            entry=100.0,
            stop=101.5,
            tp=90.0,
            direction="BEARISH",
        )

        # Custom bar: high 101.0 stays under the 101.5 stop
        # (SAFE's 105 high would stop it out on the fill bar).
        calm = dict(high=101.0, low=99.0, close=100.0)

        engine, _ = self._engine(
            {0: intent},
            [Candle(**calm, timestamp=1)],
            fill_slippage_bps=10.0,
        )

        # 100 - 100 * 10 / 10000 = 99.90
        self.assertAlmostEqual(
            engine.current_trade.entry,
            99.9,
            places=6,
        )

        self.assertEqual(
            engine.current_trade.stop_loss,
            intent.stop_loss,
        )

    def test_fill_slippage_does_not_fill_invalid_setups(self):

        engine, _ = self._engine(
            {0: None},
            [Candle(**SAFE, timestamp=1)],
            fill_slippage_bps=10.0,
        )

        self.assertIsNone(engine.current_trade)

    def test_mark_to_market_floats_open_equity(self):

        intent = order()

        engine, _ = self._engine(
            {0: intent},
            [Candle(high=105.0, low=99.0, close=105.0, timestamp=1)],
            mark_to_market=True,
        )

        # Floating = (105 - 100) * 1 = 5 above balance.
        self.assertAlmostEqual(
            engine.account.state.floating_pnl,
            5.0,
            places=6,
        )

        self.assertAlmostEqual(
            engine.account.equity,
            engine.account.balance + 5.0,
            places=6,
        )

    def test_mark_to_market_net_of_commission_and_slippage(self):
        # Phase-13 maintenance: gate-compliant target (entry shifts
        # to 100.75: 15.25/2.25 = 6.78 >= 6). MTM-math intent
        # unchanged (gross 10 - 3 costs = 7).

        intent = order(quantity=2.0, commission=1.0, slippage=2.0,
                       tp=116.0)

        from core.risk.costs import CostSpec
        with patch(
            "core.paper_trading.paper_trading_engine.paper_cost_profile",
            return_value=CostSpec(per_trade=1.0, rate=0.0, slippage_bps=50.0),
        ):
            engine, _ = self._engine(
                {0: intent},
                [Candle(high=105.0, low=99.0, close=105.0, timestamp=1)],
                mark_to_market=True,
            )

        # Gross = (105 - 100) * 2 = 10, net of comm+slip = 7.
        self.assertAlmostEqual(
            engine.account.state.floating_pnl,
            7.0,
            places=6,
        )

    def test_mark_to_market_tracks_while_open(self):
        # Phase-13 maintenance: gate-compliant target (116.0, never
        # touched by the 105/106 candles). Tracking intent unchanged.

        intent = order(quantity=2.0, commission=1.0, slippage=2.0,
                       tp=116.0)

        from core.risk.costs import CostSpec
        with patch(
            "core.paper_trading.paper_trading_engine.paper_cost_profile",
            return_value=CostSpec(per_trade=1.0, rate=0.0, slippage_bps=50.0),
        ):
            engine, _ = self._engine(
                {0: intent},
                [
                    Candle(high=105.0, low=99.0, close=105.0, timestamp=1),
                    Candle(high=106.0, low=100.0, close=106.0, timestamp=2),
                ],
                mark_to_market=True,
            )

        # Second candle: gross = (106 - 100) * 2 = 12, net = 9.
        self.assertAlmostEqual(
            engine.account.state.floating_pnl,
            9.0,
            places=6,
        )

    def test_mark_to_market_resets_when_flat(self):

        engine, _ = self._engine(
            {0: order()},
            [
                Candle(**EXIT_WIN, timestamp=1),
                Candle(**SAFE, timestamp=2),
            ],
            mark_to_market=True,
        )

        # After the win + a flat candle, floating P&L returns to
        # zero and equity == balance.
        self.assertAlmostEqual(
            engine.account.state.floating_pnl,
            0.0,
            places=6,
        )

        self.assertAlmostEqual(
            engine.account.equity,
            engine.account.balance,
            places=6,
        )

    # --------------------------------------------------
    # Live wiring
    # --------------------------------------------------

    def test_subscribe_registers_candle_callback(self):

        class FakeBus:

            def __init__(self):
                self.subs = {}

            def subscribe(self, event_type, callback):
                self.subs[event_type] = callback

        bus = FakeBus()

        pipeline = FakePipeline({0: order()})

        engine = PaperTradingEngine(
            pipeline,
            event_bus=bus,
        )

        engine.subscribe()

        self.assertIn(EventType.CANDLE, bus.subs)

        candle = Candle(**SAFE, timestamp=1)

        bus.subs[EventType.CANDLE](
            CandleEvent(candle=candle)
        )

        self.assertIsNotNone(engine.current_trade)

        self.assertEqual(engine.processed_bars, 1)


if __name__ == "__main__":
    unittest.main()
