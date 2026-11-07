"""
====================================================

QuantEngine

Portfolio Risk Wiring Tests

Run with:

    python -m unittest tests.test_portfolio_risk_wiring -v

Proves the opt-in integration of PortfolioRiskManager into
PortfolioBacktester. The default PortfolioBacktester path (no
risk manager) must be byte-identical in behavior; with a risk
manager the shared portfolio caps gate new trades across all
symbols and release exposure when trades close.

    1. Default neutrality: with no risk manager the same trades
       open, close and book exactly as if the hooks were absent.
    2. Position cap gating: max_positions rejects the next
       order regardless of symbol; the rejected symbol opens
       nothing.
    3. Risk cap gating: an order whose risk_amount would exceed
       max_portfolio_risk is rejected.
    4. Release on close: closing a gated trade frees the cap so
       a later order can open on another symbol.
    5. Bookkeeping: current_risk == sum of active open trade
       risk; open_positions == number of open trades.
    6. Repeat-run determinism with a risk manager: stale
       exposure from a previous run never blocks the same run
       twice (reset-at-run).

Stdlib only -- no network, no real pipeline.

====================================================
"""

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.order_intent import OrderIntent

from backtesting.portfolio_backtester import PortfolioBacktester

from risk.portfolio_risk import PortfolioRiskManager


class Candle:

    def __init__(self, high, low, close, timestamp, symbol="TEST"):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = symbol
        self.timeframe = "1m"


class FakeEventBus:

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def publish(self, event):
        self.pipeline.on_candle(event)


class FakePipeline:

    def __init__(self, script, symbol):
        self.script = script
        self.symbol = symbol
        self._idx = 0
        self.reset()

    def reset(self):
        self.context = PipelineContext()
        self.context.market = MarketState(symbol=self.symbol, timeframe="1m")
        self._idx = 0

    def on_candle(self, event):
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        order, signal = self.script.get(self._idx, (None, None))
        self.context.order = order
        self.context.execution_signal = signal
        self._idx += 1


# Phase 12: stop 98.5 keeps scripted legacy-path orders
# inside the mandatory gates (10 / 1.5 = 6.67:1).
def order(entry=100.0, stop=98.5, tp=110.0, risk_amount=1.0):
    return OrderIntent(
        direction="BULLISH",
        entry=entry,
        stop_loss=stop,
        take_profit=tp,
        quantity=1.0,
        commission=0.0,
        slippage=0.0,
        confidence=85.0,
        score=85.0,
        symbol="TEST",
        valid=True,
        risk_amount=risk_amount,
    )


SAFE = dict(high=105.0, low=99.0, close=102.0)

EXIT_WIN = dict(high=112.0, low=101.0, close=111.0)

EXIT_LOSS = dict(high=100.0, low=85.0, close=88.0)

BTC_WIN_CANDLES = [
    Candle(**SAFE, timestamp=0, symbol="BTC"),
    Candle(**EXIT_WIN, timestamp=1, symbol="BTC"),
]

ETH_LOSS_CANDLES = [
    Candle(**SAFE, timestamp=0, symbol="ETH"),
    Candle(**EXIT_LOSS, timestamp=1, symbol="ETH"),
]

BTC_WIN_SCRIPT = {0: (order(risk_amount=3.0), None)}

ETH_LOSS_SCRIPT = {0: (order(stop=98.5, tp=115.0, risk_amount=3.0), None)}


def make_factory(scripts):
    def pipeline_factory(symbol):
        pipeline = FakePipeline(scripts.get(symbol, {}), symbol)
        return pipeline, FakeEventBus(pipeline)

    return pipeline_factory


def open_trades(manager):
    return [
        t
        for symbol in ("BTC", "ETH")
        for t in manager.engines[symbol].trades.all()
    ]


class TestDefaultPathUnchanged(unittest.TestCase):

    def test_no_risk_manager_books_identical_trades(self):
        history = {
            "BTC": list(BTC_WIN_CANDLES),
            "ETH": list(ETH_LOSS_CANDLES),
        }
        scripts = {"BTC": BTC_WIN_SCRIPT, "ETH": ETH_LOSS_SCRIPT}

        plain = PortfolioBacktester(pipeline_factory=make_factory(scripts))
        with_manager = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=PortfolioRiskManager(
                max_portfolio_risk=100.0, max_positions=100
            ),
        )

        plain_results = plain.run(history)
        gated_results = with_manager.run(history)

        for symbol in ("BTC", "ETH"):
            a = plain_results[symbol].all()
            b = gated_results[symbol].all()
            self.assertEqual([t.entry_time for t in a], [t.entry_time for t in b])
            self.assertEqual([t.exit_price for t in a], [t.exit_price for t in b])
            self.assertEqual([t.pnl for t in a], [t.pnl for t in b])

        self.assertEqual(
            sum(len(r.all()) for r in plain_results.values()),
            sum(len(r.all()) for r in gated_results.values()),
        )

    def test_trade_risk_amount_recorded_from_order(self):
        history = {
            "BTC": list(BTC_WIN_CANDLES),
            "ETH": list(ETH_LOSS_CANDLES),
        }
        scripts = {"BTC": BTC_WIN_SCRIPT, "ETH": ETH_LOSS_SCRIPT}

        portfolio = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=PortfolioRiskManager(max_portfolio_risk=100.0),
        )
        portfolio.run(history)

        risk_amounts = [t.risk_amount for t in open_trades(portfolio)]

        self.assertEqual(risk_amounts, [3.0, 3.0])


class TestPositionCapGating(unittest.TestCase):

    def test_max_positions_blocks_second_symbol(self):
        # BTC stays flat-to-open and NEVER exits (both candles are
        # SAFE, so stop/target are never touched), keeping its slot
        # taken the whole run.
        history = {
            "BTC": [
                Candle(**SAFE, timestamp=0, symbol="BTC"),
                Candle(**SAFE, timestamp=1, symbol="BTC"),
            ],
            "ETH": list(ETH_LOSS_CANDLES),
        }
        scripts = {"BTC": BTC_WIN_SCRIPT, "ETH": ETH_LOSS_SCRIPT}

        portfolio = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=PortfolioRiskManager(max_positions=1, max_portfolio_risk=100.0),
        )
        portfolio.run(history)

        # BTC opened and holds (no closed trades in its registry);
        # ETH's order is gated out, so it never opens.
        self.assertIsNotNone(portfolio.engines["BTC"].simulator.current_trade)
        self.assertIsNone(portfolio.engines["ETH"].simulator.current_trade)
        self.assertEqual(len(portfolio.engines["ETH"].trades.all()), 0)
        self.assertEqual(
            portfolio.risk_manager.open_positions, 1
        )


class TestRiskCapGating(unittest.TestCase):

    def test_risk_amount_over_cap_is_rejected(self):
        history = {
            "BTC": list(BTC_WIN_CANDLES),
            "ETH": list(ETH_LOSS_CANDLES),
        }
        scripts = {
            "BTC": {0: (order(risk_amount=6.0), None)},
            "ETH": ETH_LOSS_SCRIPT,
        }

        portfolio = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=PortfolioRiskManager(max_portfolio_risk=5.0),
        )
        results = portfolio.run(history)

        self.assertEqual(len(results["BTC"].all()), 0)
        self.assertEqual(len(results["ETH"].all()), 1)
        self.assertEqual(results["ETH"].all()[0].risk_amount, 3.0)


class TestReleaseOnClose(unittest.TestCase):

    def test_closed_trade_releases_position_cap(self):
        # ETH would be gated out by max_positions=1 if BTC's
        # exposure were still held. BTC's lone trade closes after
        # candle 1, releasing the slot so ETH may open its trade
        # (ETH_LOSS_SCRIPT fires on candle 0 -- but that candle is
        # replayed AFTER BTC's run completed, so the release has
        # already happened and the gate now passes).
        history = {
            "BTC": list(BTC_WIN_CANDLES),
            "ETH": list(ETH_LOSS_CANDLES),
        }
        scripts = {"BTC": BTC_WIN_SCRIPT, "ETH": ETH_LOSS_SCRIPT}

        portfolio = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=PortfolioRiskManager(max_positions=1, max_portfolio_risk=100.0),
        )
        portfolio.run(history)

        # Both trades opened: BTC's release happened before ETH ran.
        self.assertEqual(len(portfolio.engines["BTC"].trades.all()), 1)
        self.assertEqual(len(portfolio.engines["ETH"].trades.all()), 1)

    def test_bookkeeping_invariant_after_full_run(self):
        history = {
            "BTC": list(BTC_WIN_CANDLES),
            "ETH": list(ETH_LOSS_CANDLES),
        }
        scripts = {"BTC": BTC_WIN_SCRIPT, "ETH": ETH_LOSS_SCRIPT}

        manager = PortfolioRiskManager(max_portfolio_risk=100.0, max_positions=100)
        portfolio = PortfolioBacktester(
            pipeline_factory=make_factory(scripts), risk_manager=manager
        )
        portfolio.run(history)

        # Both trades opened and both closed: nothing remains open.
        self.assertEqual(manager.current_risk, 0.0)
        self.assertEqual(manager.open_positions, 0)


class TestRepeatRunsDeterministic(unittest.TestCase):

    def test_second_run_not_blocked_by_stale_exposure(self):
        history = {
            "BTC": list(BTC_WIN_CANDLES),
            "ETH": list(ETH_LOSS_CANDLES),
        }
        scripts = {"BTC": BTC_WIN_SCRIPT, "ETH": ETH_LOSS_SCRIPT}

        portfolio = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=PortfolioRiskManager(max_positions=1, max_portfolio_risk=100.0),
        )

        first = portfolio.run(history)
        second = portfolio.run(history)

        for symbol in ("BTC", "ETH"):
            a = first[symbol].all()
            b = second[symbol].all()
            self.assertEqual([t.entry_time for t in a], [t.entry_time for t in b])
            self.assertEqual([t.pnl for t in a], [t.pnl for t in b])


if __name__ == "__main__":
    unittest.main()