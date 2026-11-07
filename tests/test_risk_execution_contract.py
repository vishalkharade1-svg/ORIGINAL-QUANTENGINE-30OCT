"""
====================================================

QuantEngine

Risk + Execution Contract Tests

Run with:

    python -m unittest tests.test_risk_execution_contract -v

Proves the final adapter stage contract:

RiskEngine (priority 750)
    1. No execution signal -> context.order is None
       (and a stale order from a previous cycle is cleared).
    2. Zero/negative account -> no order.
    3. Exact fixed-fractional sizing on the default config:
       risk_percent = RISK_PER_TRADE * confidence_factor
       quantity = risk_amount / stop_distance, then the
       allocation cap at MAX_ALLOCATION_PER_TRADE.
    4. Commission = flat + rate * position value; slippage =
       2x basis points of position value (round trip).
    5. Drawdown protection scales risk down with account
       drawdown_percent.
    6. Zero stop distance -> sizer invalid -> no order.
    7. Determinism: same inputs -> identical order.

Backtester adapter
    8. Risk-validated OrderIntent takes precedence over the
       raw execution signal and carries quantity + costs.
    9. Net PnL = gross price PnL - commission - slippage.
   10. Closing trades are booked into the account: balance,
       realized_pnl, trade counters, win/loss counters.
   11. With no RiskEngine product (falls back to the raw
       execution signal), the legacy fixed-quantity path is
       unchanged (quantity=1.0, zero costs).
   12. No signal anywhere -> no trades, balance untouched.

Stdlib only -- no network.

====================================================
"""

import unittest
from unittest import mock

from config import risk_settings

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.account_state import AccountState
from core.risk.order_intent import OrderIntent
from core.risk.risk_engine import RiskEngine
from core.setup.setup_candidate import SetupCandidate


def seeded_account(balance=10000.0, drawdown=0.0):
    return AccountState(
        starting_balance=balance,
        balance=balance,
        equity=balance,
        peak_equity=balance,
        drawdown=drawdown,
        drawdown_percent=drawdown,
    )


def cand(
    direction="BULLISH",
    entry=100.0,
    stop=90.0,
    tp=160.0,
    confidence=85.0,
    score=85.0,
    regime=None,
):
    c = SetupCandidate(
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=tp,
        risk_reward=(
            (tp - entry) / (entry - stop)
            if entry != stop
            else 0.0
        ),
        confidence=confidence,
        score=score,
    )
    c.regime = regime
    return c


class TestRiskEngineContract(unittest.TestCase):

    def _analyze(self, signal, account):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        context.execution_signal = signal
        context.account = account

        engine = RiskEngine()
        engine.analyze(context)

        return context.order

    def _analyze_with_prior_order(self, signal, account):
        context = PipelineContext()
        context.market = MarketState(symbol="TEST", timeframe="1m")
        context.execution_signal = signal
        context.account = account
        context.order = OrderIntent(valid=True, quantity=99.0)

        engine = RiskEngine()
        engine.analyze(context)

        return context.order

    def test_no_signal_clears_stale_order(self):
        order = self._analyze_with_prior_order(None, seeded_account())
        self.assertIsNone(order)

    def test_zero_account_no_order(self):
        order = self._analyze(cand(), seeded_account(balance=0.0))
        self.assertIsNone(order)

    def test_exact_fixed_fractional_math(self):
        order = self._analyze(cand(), seeded_account())

        self.assertIsInstance(order, OrderIntent)
        self.assertTrue(order)
        self.assertEqual(order.direction, "BULLISH")
        self.assertEqual(order.entry, 100.0)
        self.assertEqual(order.stop_loss, 90.0)
        self.assertEqual(order.take_profit, 160.0)
        self.assertEqual(order.risk_reward, 6.0)

        # confidence_factor = 0.5 + (85 / 100) * 0.5 = 0.925
        # risk_percent = 0.01 * 0.925 = 0.00925
        # requested risk_amount = 10000 * 0.00925 = 92.5
        # stop_distance = 10 -> requested quantity = 9.25
        # 11E-Prep H1: notional cap 500 binds (PV 925 > 500):
        # final qty 5.0, PV 500, risk = EL = 5*10 = 50.
        self.assertAlmostEqual(order.risk_percent, 0.00925, places=6)
        self.assertAlmostEqual(order.risk_amount, 50.0, places=6)
        self.assertAlmostEqual(order.quantity, 5.0, places=6)
        self.assertAlmostEqual(
            order.position_value, 500.0, places=6
        )
        self.assertAlmostEqual(order.expected_loss, 50.0, places=6)
        self.assertAlmostEqual(
            order.expected_profit, 300.0, places=6
        )
        # Default config: no execution costs.
        self.assertEqual(order.commission, 0.0)
        self.assertEqual(order.slippage, 0.0)
        self.assertEqual(order.symbol, "TEST")

        self.assertTrue(order)

    def test_setup_reference_preserved(self):
        signal = cand()
        order = self._analyze(signal, seeded_account())
        self.assertIs(order.setup, signal)

    def test_fees_flow_from_config(self):
        order = self._analyze(cand(), seeded_account())

        with mock.patch.object(
            risk_settings, "COMMISSION_PER_TRADE", 1.0
        ), mock.patch.object(
            risk_settings, "COMMISSION_RATE", 0.001
        ), mock.patch.object(
            risk_settings, "SLIPPAGE_BPS", 10.0
        ):
            order = self._analyze(cand(), seeded_account())

        self.assertAlmostEqual(
            order.commission, 1.0 + 500.0 * 0.001, places=6
        )
        self.assertAlmostEqual(
            order.slippage, 2.0 * 500.0 * 0.001, places=6
        )

    def test_drawdown_protection_shrinks_risk(self):
        clean = self._analyze(cand(), seeded_account())
        impaired = self._analyze(
            cand(), seeded_account(drawdown=15.0)
        )

        self.assertGreater(clean.quantity, impaired.quantity)
        self.assertAlmostEqual(
            impaired.risk_percent, 0.0069375, places=6
        )

    def test_zero_stop_distance_no_order(self):
        order = self._analyze(
            cand(entry=100.0, stop=100.0), seeded_account()
        )
        self.assertIsNone(order)

    def test_deterministic(self):
        a = self._analyze(cand(), seeded_account())
        b = self._analyze(cand(), seeded_account())

        fields = [
            "direction", "entry", "quantity", "risk_amount",
            "position_value", "commission", "slippage",
        ]
        self.assertEqual(
            [getattr(a, f) for f in fields],
            [getattr(b, f) for f in fields],
        )


# ==========================================================
# Backtester Adapter (fake pipeline drives deterministic candles)
# ==========================================================


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
        self.context = PipelineContext()
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


class TestBacktesterAdapterContract(unittest.TestCase):

    def _run(self, candles, script):
        pipeline = FakePipeline(script)
        event_bus = FakeEventBus(pipeline)

        from core.backtesting.trade_simulator import TradeSimulator
        from backtesting.backtester import Backtester

        simulator = TradeSimulator()
        backtester = Backtester(pipeline, event_bus, simulator)

        backtester.run(candles)

        return backtester, simulator, pipeline.context

    def test_loss_net_of_costs_and_booked(self):
        open_candle = Candle(high=105.0, low=99.0, close=102.0, timestamp=1)
        stop_candle = Candle(high=100.0, low=85.0, close=88.0, timestamp=2)

        # Phase 12: stop 98.5 keeps the gated legacy path
        # green (10 / 1.5 = 6.67:1); the loss leg exits at
        # the stop, 98.5.
        # Phase-13 maintenance: target 115 keeps the MANDATORY
        # post-cost R:R gate green (costs 2+0.5 shift the entry to
        # 100.625: 14.375/2.125 = 6.76 >= 6). Loss-booking intent
        # (SL exit math, account postings) unchanged.
        order = OrderIntent(
            direction="BULLISH",
            entry=100.0,
            stop_loss=98.5,
            take_profit=115.0,
            risk_reward=6.76,
            quantity=2.0,
            position_value=200.0,
            commission=2.0,
            slippage=0.5,
            confidence=85.0,
            score=85.0,
            symbol="TEST",
            valid=True,
        )

        backtester, simulator, _ = self._run(
            [open_candle, stop_candle],
            {0: (order, None)},
        )

        self.assertEqual(simulator.registry.count(), 1)
        trade = simulator.registry.all()[0]

        self.assertEqual(trade.result, "LOSS")
        # gross = (98.5 - 100) * 2 = -3; net = -3 - 2.0 - 0.5
        self.assertAlmostEqual(trade.pnl, -5.5, places=6)
        self.assertEqual(trade.commission, 2.0)
        self.assertEqual(trade.slippage, 0.5)
        self.assertEqual(trade.quantity, 2.0)

        # Account booking: 2000 - 5.5 = 1994.5
        self.assertAlmostEqual(backtester.account.balance, 1994.5, places=6)
        self.assertAlmostEqual(backtester.account.equity, 1994.5, places=6)
        self.assertAlmostEqual(
            backtester.account.state.realized_pnl, -5.5, places=6
        )
        self.assertEqual(backtester.account.state.total_trades, 1)
        self.assertEqual(backtester.account.state.winning_trades, 0)
        self.assertEqual(backtester.account.state.losing_trades, 1)

    def test_win_net_of_costs_and_booked(self):
        open_candle = Candle(high=105.0, low=99.0, close=102.0, timestamp=1)
        tp_candle = Candle(high=112.0, low=101.0, close=111.0, timestamp=2)

        # Phase-13 maintenance: target 112 keeps the MANDATORY
        # post-cost R:R gate green (costs 0.5+0.25 shift the entry
        # to 100.375: 11.625/1.875 = 6.2 >= 6). Win-booking intent
        # unchanged (TP exit math, account postings).
        order = OrderIntent(
            direction="BULLISH",
            entry=100.0,
            stop_loss=98.5,
            take_profit=112.0,
            risk_reward=6.2,
            quantity=1.0,
            position_value=100.0,
            commission=0.5,
            slippage=0.25,
            confidence=85.0,
            score=85.0,
            symbol="TEST",
            valid=True,
        )

        backtester, simulator, _ = self._run(
            [open_candle, tp_candle],
            {0: (order, None)},
        )

        trade = simulator.registry.all()[0]

        self.assertEqual(trade.result, "WIN")
        # gross = (112 - 100) * 1 = 12; net = 12 - 0.5 - 0.25
        self.assertAlmostEqual(trade.pnl, 11.25, places=6)
        self.assertAlmostEqual(backtester.account.balance, 2011.25, places=6)
        self.assertEqual(backtester.account.state.winning_trades, 1)
        self.assertEqual(backtester.account.state.losing_trades, 0)

    def test_order_takes_precedence_over_signal(self):
        open_candle = Candle(high=105.0, low=99.0, close=102.0, timestamp=1)
        tp_candle = Candle(high=112.0, low=101.0, close=111.0, timestamp=2)

        order = OrderIntent(
            direction="BULLISH",
            entry=100.0,
            stop_loss=98.5,
            take_profit=110.0,
            risk_reward=6.67,
            quantity=3.0,
            position_value=300.0,
            confidence=85.0,
            score=85.0,
            symbol="TEST",
            valid=True,
        )
        signal = cand(entry=99.0, stop=94.0, tp=120.0, confidence=95.0)

        backtester, simulator, _ = self._run(
            [open_candle, tp_candle],
            {0: (order, signal)},
        )

        trade = simulator.registry.all()[0]
        self.assertEqual(trade.quantity, 3.0)
        self.assertEqual(trade.entry, 100.0)

    def test_legacy_signal_fallback_unchanged(self):
        open_candle = Candle(high=105.0, low=99.0, close=102.0, timestamp=1)
        tp_candle = Candle(high=112.0, low=101.0, close=111.0, timestamp=2)

        signal = cand(entry=100.0, stop=98.5, tp=110.0)

        backtester, simulator, _ = self._run(
            [open_candle, tp_candle],
            {0: (None, signal)},
        )

        trade = simulator.registry.all()[0]
        # Legacy path: quantity=1.0, zero costs -> gross pnl.
        self.assertEqual(trade.quantity, 1.0)
        self.assertEqual(trade.commission, 0.0)
        self.assertEqual(trade.slippage, 0.0)
        self.assertAlmostEqual(trade.pnl, 10.0, places=6)
        self.assertAlmostEqual(backtester.account.balance, 2010.0, places=6)

    def test_no_signal_no_trades_no_balance_change(self):
        candle = Candle(high=105.0, low=99.0, close=102.0, timestamp=1)

        backtester, simulator, _ = self._run([candle, candle], {})

        self.assertEqual(simulator.registry.count(), 0)
        self.assertAlmostEqual(backtester.account.balance, 2000.0, places=6)

    def test_stale_order_across_cycles_cannot_refill(self):
        open_candle = Candle(high=105.0, low=99.0, close=102.0, timestamp=1)
        tp_candle = Candle(high=112.0, low=101.0, close=111.0, timestamp=2)

        order = OrderIntent(
            direction="BULLISH",
            entry=100.0,
            stop_loss=98.5,
            take_profit=110.0,
            risk_reward=6.67,
            quantity=1.0,
            position_value=100.0,
            confidence=85.0,
            score=85.0,
            symbol="TEST",
            valid=True,
        )

        # The order is scripted on candle 0 only. reset_cycle +
        # the fake pipeline clear it afterwards, so once the
        # trade closes on candle 1 there is nothing left to
        # re-enter -- exactly the stale-refill regression the
        # per-candle clearing was added for.
        backtester, simulator, _ = self._run(
            [
                open_candle,
                tp_candle,
                open_candle,
                tp_candle,
                open_candle,
                tp_candle,
            ],
            {0: (order, None)},
        )

        self.assertEqual(simulator.registry.count(), 1)
        self.assertEqual(backtester.account.state.total_trades, 1)


if __name__ == "__main__":
    unittest.main()