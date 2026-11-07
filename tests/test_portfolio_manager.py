"""
====================================================

QuantEngine

Portfolio Manager Tests

Run with:

    python -m unittest tests.test_portfolio_manager -v

Proves the extended PortfolioRiskManager (the shared,
legacy-compatible portfolio risk object -- NO duplicate class)
now also enforces:

    1. Legacy cap neutrality: max_portfolio_risk and
       max_positions still gate exactly as before when the new
       allocation / loss guards are left disabled (defaults).
    2. Daily loss limit: once realized PnL lags the starting
       balance by the limit, every order is gated; a recovery
       win re-enables trading.
    3. Portfolio allocation cap: summed open notional cannot
       exceed a percentage of current equity.
    4. Per-symbol allocation cap: each symbol's open notional
       is capped independently of the others.
    5. Symbols release their share of the notional when a
       trade closes; equity tracks realized PnL.
    6. reset() clears EVERY piece of state so a fresh run can
       never inherit stale exposure.
    7. PortfolioBacktester integration: the gate passes the
       order's symbol / position_value and the release passes
       the traded symbol / pnl end-to-end.

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
# inside the mandatory gates (10 / 1.5 = 6.67:1). Loss legs
# exit at 98.5 (-1.5); the daily-loss test below sizes its
# limit to that exact boundary.
def order(
    entry=100.0,
    stop=98.5,
    tp=110.0,
    risk_amount=1.0,
    position_value=0.0,
    symbol="TEST",
):
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
        symbol=symbol,
        valid=True,
        risk_amount=risk_amount,
        position_value=position_value,
    )


SAFE = dict(high=105.0, low=99.0, close=102.0)

EXIT_WIN = dict(high=112.0, low=101.0, close=111.0)

EXIT_LOSS = dict(high=100.0, low=85.0, close=88.0)


def make_factory(scripts):
    def pipeline_factory(symbol):
        pipeline = FakePipeline(scripts.get(symbol, {}), symbol)
        return pipeline, FakeEventBus(pipeline)

    return pipeline_factory


class TestPortfolioRiskManager(unittest.TestCase):

    def test_legacy_caps_unchanged_when_guards_disabled(self):
        # All new guards default off -- the legacy risk and
        # position caps behave byte-identically.
        manager = PortfolioRiskManager(
            max_portfolio_risk=5.0,
            max_positions=2,
        )

        self.assertTrue(manager.can_open(3.0))
        manager.register_trade(3.0)
        self.assertTrue(manager.can_open(2.0))
        manager.register_trade(2.0)
        self.assertFalse(manager.can_open(0.01))

        self.assertEqual(manager.open_by_symbol, {})

    def test_daily_loss_limit_gates_and_recovers(self):
        manager = PortfolioRiskManager(
            max_portfolio_risk=100.0,
            starting_balance=1000.0,
            daily_loss_limit=10.0,
        )

        manager.close_trade(1.0, symbol="A", pnl=-10.0)

        self.assertEqual(manager.equity, 990.0)
        # floor == 990 -> hit exactly
        self.assertFalse(manager.can_open(1.0))

        manager.close_trade(0.0, symbol="A", pnl=20.0)

        self.assertEqual(manager.equity, 1010.0)
        self.assertTrue(manager.can_open(1.0))

    def test_daily_loss_limit_zero_disables(self):
        manager = PortfolioRiskManager(
            max_portfolio_risk=100.0,
            starting_balance=1000.0,
        )

        manager.close_trade(1.0, pnl=-50.0)

        self.assertEqual(manager.equity, 950.0)
        self.assertTrue(manager.can_open(1.0))

    def test_portfolio_allocation_cap(self):
        manager = PortfolioRiskManager(
            max_portfolio_risk=100.0,
            starting_balance=1000.0,
            max_portfolio_allocation=50.0,
        )

        # 50% of 1000 == 500
        self.assertTrue(
            manager.can_open(1.0, symbol="A", position_value=300.0)
        )
        manager.register_trade(1.0, symbol="A", position_value=300.0)

        self.assertEqual(manager.open_notional, 300.0)

        self.assertFalse(
            manager.can_open(1.0, symbol="B", position_value=250.0)
        )

        # Closing A frees the notional.
        manager.close_trade(1.0, symbol="A")

        self.assertEqual(manager.open_notional, 0.0)
        self.assertTrue(
            manager.can_open(1.0, symbol="B", position_value=250.0)
        )

    def test_per_symbol_allocation_cap(self):
        manager = PortfolioRiskManager(
            max_portfolio_risk=100.0,
            starting_balance=1000.0,
            max_per_symbol_allocation=40.0,
        )

        # 40% of 1000 == 400
        self.assertTrue(
            manager.can_open(1.0, symbol="A", position_value=300.0)
        )
        manager.register_trade(1.0, symbol="A", position_value=300.0)

        # A is nearly full: another 150 puts it at 450 > 400.
        self.assertFalse(
            manager.can_open(1.0, symbol="A", position_value=150.0)
        )

        # An independent symbol is not affected by A's exposure.
        self.assertTrue(
            manager.can_open(1.0, symbol="B", position_value=380.0)
        )
        manager.register_trade(1.0, symbol="B", position_value=380.0)

        self.assertEqual(manager.open_notional, 680.0)

    def test_allocation_cap_with_zero_or_negative_equity(self):
        manager = PortfolioRiskManager(
            max_portfolio_risk=100.0,
            max_portfolio_allocation=50.0,
        )

        self.assertEqual(manager.equity, 0.0)
        self.assertFalse(manager.can_open(1.0, symbol="A", position_value=1.0))

    def test_equity_tracks_realized_pnl(self):
        manager = PortfolioRiskManager(
            max_portfolio_risk=100.0,
            starting_balance=2000.0,
        )

        manager.close_trade(1.0, symbol="A", pnl=10.0)
        manager.close_trade(1.0, symbol="B", pnl=-5.0)

        self.assertEqual(manager.equity, 2005.0)
        self.assertEqual(manager.realized_pnl, 5.0)

    def test_reset_clears_everything(self):
        manager = PortfolioRiskManager(
            max_portfolio_risk=100.0,
            starting_balance=1000.0,
        )

        manager.register_trade(4.0, symbol="A", position_value=400.0)
        manager.close_trade(2.0, symbol="B", pnl=30.0)
        manager.reset()

        self.assertEqual(manager.current_risk, 0.0)
        self.assertEqual(manager.open_positions, 0)
        self.assertEqual(manager.open_by_symbol, {})
        self.assertEqual(manager.realized_pnl, 0.0)
        self.assertEqual(manager.equity, 1000.0)
        self.assertTrue(manager.can_open(5.0))


class TestPortfolioBacktesterIntegration(unittest.TestCase):

    def test_daily_loss_floor_blocks_later_symbols(self):
        history = {
            "ALPHA": [
                Candle(**SAFE, timestamp=0, symbol="ALPHA"),
                Candle(**EXIT_LOSS, timestamp=1, symbol="ALPHA"),
            ],
            "BETA": [
                Candle(**SAFE, timestamp=0, symbol="BETA"),
                Candle(**EXIT_LOSS, timestamp=1, symbol="BETA"),
            ],
        }
        scripts = {
            "ALPHA": {0: (order(stop=98.5, tp=115.0), None)},
            "BETA": {0: (order(stop=98.5, tp=115.0), None)},
        }

        portfolio = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=PortfolioRiskManager(
                max_portfolio_risk=100.0,
                starting_balance=2000.0,
                daily_loss_limit=1.5,
            ),
        )
        portfolio.run(history)

        # ALPHA lost exactly the 1.5 limit (equity 1998.5 ==
        # floor -- exact equality blocks), so BETA's order is
        # gated and never opens.
        self.assertEqual(len(portfolio.engines["ALPHA"].trades.all()), 1)
        self.assertEqual(
            portfolio.engines["ALPHA"].trades.all()[0].result, "LOSS"
        )
        self.assertEqual(len(portfolio.engines["BETA"].trades.all()), 0)
        self.assertEqual(portfolio.risk_manager.equity, 1998.5)

    def test_allocation_cap_blocks_second_symbol_while_open(self):
        history = {
            "ALPHA": [
                Candle(**SAFE, timestamp=0, symbol="ALPHA"),
                Candle(**SAFE, timestamp=1, symbol="ALPHA"),
            ],
            "BETA": [
                Candle(**SAFE, timestamp=0, symbol="BETA"),
                Candle(**SAFE, timestamp=1, symbol="BETA"),
            ],
        }
        scripts = {
            "ALPHA": {0: (order(position_value=400.0), None)},
            "BETA": {0: (order(position_value=400.0), None)},
        }

        portfolio = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=PortfolioRiskManager(
                max_portfolio_risk=100.0,
                starting_balance=1000.0,
                max_portfolio_allocation=50.0,
            ),
        )
        portfolio.run(history)

        # ALPHA holds its whole run (SAFE candles never touch
        # the 98.5/110 bracket), keeping 400 of the 500 cap used;
        # BETA's 400 would take notional to 800 > 500.
        self.assertIsNotNone(portfolio.engines["ALPHA"].simulator.current_trade)
        self.assertIsNone(portfolio.engines["BETA"].simulator.current_trade)
        self.assertEqual(portfolio.risk_manager.open_notional, 400.0)

    def test_allocation_cap_releases_when_trade_closes(self):
        history = {
            "ALPHA": [
                Candle(**SAFE, timestamp=0, symbol="ALPHA"),
                Candle(**EXIT_WIN, timestamp=1, symbol="ALPHA"),
            ],
            "BETA": [
                Candle(**SAFE, timestamp=0, symbol="BETA"),
                Candle(**EXIT_WIN, timestamp=1, symbol="BETA"),
            ],
        }
        scripts = {
            "ALPHA": {0: (order(position_value=400.0), None)},
            "BETA": {0: (order(position_value=400.0), None)},
        }

        portfolio = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=PortfolioRiskManager(
                max_portfolio_risk=100.0,
                starting_balance=1000.0,
                max_portfolio_allocation=50.0,
            ),
        )
        portfolio.run(history)

        # ALPHA closes at candle 1 (+10), releasing its notional
        # and PnL, so BETA's order passes the gate and wins too.
        self.assertEqual(len(portfolio.engines["ALPHA"].trades.all()), 1)
        self.assertEqual(len(portfolio.engines["BETA"].trades.all()), 1)
        self.assertEqual(
            portfolio.engines["BETA"].trades.all()[0].result, "WIN"
        )
        self.assertEqual(portfolio.risk_manager.open_notional, 0.0)
        self.assertEqual(portfolio.risk_manager.equity, 1020.0)


if __name__ == "__main__":
    unittest.main()