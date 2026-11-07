"""
====================================================

QuantEngine

Portfolio (Cross-Symbol) Contract Tests

Run with:

    python -m unittest tests.test_portfolio_contract -v

Proves the multi-symbol portfolio layer keeps every
per-symbol backtest isolated and deterministic, and that
aggregation is exactly the sum of the per-symbol books:

    1. Symbol isolation: each symbol's trades come ONLY
       from its own order script; accounts, contexts and
       registries are distinct objects; nothing bleeds
       across symbols.
    2. Determinism: two runs on the same PortfolioBacktester
       reproduce identical trades for every symbol.
    3. Aggregation: portfolio total PnL == sum of per-symbol
       close PnL == sum over accounts of (balance - starting).
    4. PortfolioRiskManager caps: max_portfolio_risk and
       max_positions reject new trades; close_trade releases
       exposure; counters can never go negative; and the
       bookkeeping invariant current_risk == sum of active
       trade risk, open_positions == number of active trades.

Stdlib only -- no network, no real pipeline.

====================================================
"""

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.order_intent import OrderIntent

from backtesting.backtester import Backtester
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
# inside the mandatory gates (10 / 1.5 = 6.67:1); the ETH
# loss leg exits at 98.5 (-1.5), so the aggregation
# identity below nets to +8.5, not zero.
def order(
    entry=100.0,
    stop=98.5,
    tp=110.0,
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
        symbol="TEST",
        valid=True,
    )


SAFE = dict(high=105.0, low=99.0, close=102.0)

EXIT_WIN = dict(high=112.0, low=101.0, close=111.0)

EXIT_LOSS = dict(high=100.0, low=85.0, close=88.0)

BTC_CANDLES = [
    Candle(**SAFE, timestamp=0, symbol="BTC"),
    Candle(**EXIT_WIN, timestamp=1, symbol="BTC"),
]

ETH_CANDLES = [
    Candle(**SAFE, timestamp=0, symbol="ETH"),
    Candle(**EXIT_LOSS, timestamp=1, symbol="ETH"),
]

BTC_SCRIPT = {0: (order(), None)}

ETH_SCRIPT = {0: (order(stop=98.5, tp=115.0), None)}


def make_factory(scripts):
    def pipeline_factory(symbol):
        pipeline = FakePipeline(scripts.get(symbol, {}), symbol)
        return pipeline, FakeEventBus(pipeline)

    return pipeline_factory


class TestPortfolioBacktesterIsolation(unittest.TestCase):

    def _run(self):
        history = {
            "BTC": list(BTC_CANDLES),
            "ETH": list(ETH_CANDLES),
        }
        scripts = {"BTC": BTC_SCRIPT, "ETH": ETH_SCRIPT}
        portfolio = PortfolioBacktester(pipeline_factory=make_factory(scripts))
        results = portfolio.run(history)
        return portfolio, results, scripts

    def test_symbol_trades_come_only_from_own_script(self):
        portfolio, results, _ = self._run()

        # BTC scripts exactly one WIN (+10); ETH one LOSS (-10).
        btc = results["BTC"].all()
        eth = results["ETH"].all()

        self.assertEqual(len(btc), 1)
        self.assertEqual(btc[0].result, "WIN")
        self.assertAlmostEqual(btc[0].pnl, 10.0, places=6)

        self.assertEqual(len(eth), 1)
        self.assertEqual(eth[0].result, "LOSS")
        self.assertAlmostEqual(eth[0].pnl, -1.5, places=6)

        # The symbols each ran their own account ledger.
        self.assertAlmostEqual(
            portfolio.engines["BTC"].account.balance, 2010.0, places=6
        )
        self.assertAlmostEqual(
            portfolio.engines["ETH"].account.balance, 1998.5, places=6
        )

    def test_engines_accounts_and_contexts_are_distinct_objects(self):
        portfolio, _, _ = self._run()

        btc_engine = portfolio.engines["BTC"]
        eth_engine = portfolio.engines["ETH"]

        self.assertIsNot(btc_engine, eth_engine)
        self.assertIsNot(btc_engine.account, eth_engine.account)
        self.assertIsNot(
            btc_engine.account.state, eth_engine.account.state
        )
        self.assertIsNot(btc_engine.pipeline.context, eth_engine.pipeline.context)
        self.assertEqual(btc_engine.pipeline.context.market.symbol, "BTC")
        self.assertEqual(eth_engine.pipeline.context.market.symbol, "ETH")

    def test_run_twice_is_deterministic(self):
        history = {
            "BTC": list(BTC_CANDLES),
            "ETH": list(ETH_CANDLES),
        }
        scripts = {"BTC": BTC_SCRIPT, "ETH": ETH_SCRIPT}
        portfolio = PortfolioBacktester(pipeline_factory=make_factory(scripts))

        first = portfolio.run(history)
        second = portfolio.run(history)

        for symbol in ("BTC", "ETH"):
            a = first[symbol].all()
            b = second[symbol].all()
            self.assertEqual([t.entry_time for t in a], [t.entry_time for t in b])
            self.assertEqual([t.exit_price for t in a], [t.exit_price for t in b])
            self.assertEqual([t.pnl for t in a], [t.pnl for t in b])

    def test_aggregation_is_sum_of_per_symbol_books(self):
        portfolio, results, _ = self._run()

        per_symbol_pnl = {
            symbol: sum(t.pnl for t in reg.all())
            for symbol, reg in results.items()
        }
        account_pnl = {
            symbol: (
                engine.account.balance
                - engine.account.state.starting_balance
            )
            for symbol, engine in portfolio.engines.items()
        }

        self.assertEqual(per_symbol_pnl, account_pnl)
        self.assertEqual(sum(per_symbol_pnl.values()), 8.5)

        grand_total_trades = sum(
            engine.account.state.total_trades
            for engine in portfolio.engines.values()
        )
        grand_registry_trades = sum(
            reg.count() for reg in results.values()
        )
        self.assertEqual(grand_total_trades, grand_registry_trades)
        self.assertEqual(grand_total_trades, 2)

    def test_register_compat_adds_engine(self):
        scripts = {"BTC": BTC_SCRIPT, "ETH": ETH_SCRIPT}
        portfolio = PortfolioBacktester(pipeline_factory=make_factory(scripts))

        engine = portfolio.register("ZZZ")

        self.assertIn("ZZZ", portfolio.engines)
        self.assertIs(portfolio.engines["ZZZ"], engine)
        self.assertEqual(engine.pipeline.context.market.symbol, "ZZZ")


class TestPortfolioRiskManager(unittest.TestCase):

    def test_risk_cap_rejects_overflow(self):
        manager = PortfolioRiskManager(max_portfolio_risk=5.0)

        self.assertTrue(manager.can_open(3.0))
        manager.register_trade(3.0)
        self.assertTrue(manager.can_open(2.0))
        manager.register_trade(2.0)
        self.assertFalse(manager.can_open(0.01))

    def test_position_cap_rejects(self):
        manager = PortfolioRiskManager(max_portfolio_risk=100.0, max_positions=2)

        self.assertTrue(manager.can_open(1.0))
        manager.register_trade(1.0)
        self.assertTrue(manager.can_open(1.0))
        manager.register_trade(1.0)
        self.assertFalse(manager.can_open(1.0))

    def test_close_trade_releases_exposure(self):
        manager = PortfolioRiskManager(max_portfolio_risk=5.0)

        manager.register_trade(3.0)
        manager.close_trade(3.0)

        self.assertTrue(manager.can_open(5.0))
        self.assertEqual(manager.open_positions, 0)

    def test_bookkeeping_invariant(self):
        manager = PortfolioRiskManager(max_portfolio_risk=100.0)

        manager.register_trade(2.0)
        manager.register_trade(3.0)
        manager.close_trade(2.0)
        manager.register_trade(1.0)

        # current_risk == sum of active risk; open == active count.
        self.assertEqual(manager.current_risk, 4.0)
        self.assertEqual(manager.open_positions, 2)

    def test_close_trade_never_goes_negative(self):
        manager = PortfolioRiskManager(max_portfolio_risk=5.0)

        manager.close_trade(10.0)
        manager.close_trade(10.0)

        self.assertEqual(manager.current_risk, 0.0)
        self.assertEqual(manager.open_positions, 0)

    def test_reset(self):
        manager = PortfolioRiskManager(max_portfolio_risk=5.0)

        manager.register_trade(4.0)
        manager.reset()

        self.assertEqual(manager.current_risk, 0.0)
        self.assertEqual(manager.open_positions, 0)
        self.assertTrue(manager.can_open(5.0))


if __name__ == "__main__":
    unittest.main()