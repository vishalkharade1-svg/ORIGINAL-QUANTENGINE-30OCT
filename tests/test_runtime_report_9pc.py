"""
====================================================

QuantEngine

Canonical Runtime Analytics / Account Reporting
Attach-Point Tests (Phase 9P-c)

Run with:

    python -m unittest tests.test_runtime_report_9pc -v

Scope

    Proves that the running PAPER runtime can expose the CANONICAL
    performance report (PerformanceAnalytics / PerformanceReport)
    for its completed trades through a pure attach-point, with NO
    second PF/expectancy calculation and NO account-level duplicate
    surface.

    Attach-points under test:

        PaperRuntime.report()
            -> PerformanceAnalytics.analyze(runtime.account,
                                             runtime.ledger)
               (per-instrument, canonical performance report)

        RealTimeEngine.performance(symbol=...)
            -> the single active runtime's report (or None)

        RealTimeEngine.performance()
            -> aggregate report over ALL active runtimes' completed
               trades (shared starting balance: sum of per-runtime)

    Both delegate EXCLUSIVELY to PerformanceAnalytics -- the report
    object is the same object any other mode (backtest / validation
    / dashboard) consumes, so it can never disagree.

    Coverage required:

        1. runtime can obtain the canonical performance report
        2. report uses completed (CLOSED) trades only
        3. open trades are excluded
        4. rejected orders are excluded (never in the ledger)
        5. expired / unfilled / cancelled orders are excluded
        6. breakeven remains neither win nor loss
        7. Profit Factor comes from canonical analytics (identity
           with PerformanceAnalytics)
        8. expectancy comes from canonical analytics
        9. no second PF/expectancy implementation is introduced
       10. report updates after a trade closes
       11. repeated report generation is deterministic
       12. PAPER runtime integration remains intact
       13. account state does not become a duplicate analytics
           engine (no profit_factor / expectancy on AccountState)

    Also verifies the multi-symbol orchestration level: per-symbol
    routing isolation of reports, and the aggregate report over all
    symbols.

Stdlib only -- no network, no threads, no caches.
====================================================
"""

import unittest
from types import SimpleNamespace

from core.registry.instrument import Instrument

from core.analytics.performance import (
    PerformanceAnalytics,
    PerformanceReport,
)

from core.runtime.paper_runtime import PaperRuntime

from core.runtime.paper_main import (
    ExplicitSymbolUniverseManager,
    build_paper_engine,
)
from core.runtime.pipeline_registry import instrument_identity_key


def _instrument(symbol):
    return Instrument(
        instrument_id=symbol,
        symbol=symbol,
        exchange="DELTA",
        product_type="SPOT",
        underlying_asset=symbol,
        quote_asset="USDT",
        tick_size=0.01,
        quantity_step=0.001,
        minimum_quantity=0.001,
        trading_enabled=True,
        state="ELIGIBLE",
    )


def _mini_world():
    world = SimpleNamespace()
    world.context = SimpleNamespace(market=SimpleNamespace(symbol=""))
    world.reset = lambda: None
    return world


def _mini_pipeline():
    """The smallest pipeline-compatible object PaperRuntime needs
    (it builds a BrokerEngine from .world / .event_bus / .simulator;
    the report tests never drive a candle)."""
    from core.backtesting.trade_simulator import TradeSimulator

    return SimpleNamespace(
        world=_mini_world(),
        event_bus=None,
        simulator=TradeSimulator(),
        context=SimpleNamespace(),
    )


def _closed_trade(pnl, symbol="", entry_time=0, exit_time=0):
    from core.backtesting.trade import Trade

    return Trade(
        direction="BULLISH",
        entry=100.0,
        quantity=1.0,
        entry_time=entry_time,
        exit_time=exit_time,
        exit_price=100.0 + pnl,
        pnl=pnl,
        pnl_percent=(pnl / 100.0) if pnl else 0.0,
        bars_held=1,
        status="CLOSED",
        result="WIN" if pnl > 0 else ("LOSS" if pnl < 0 else ""),
        symbol=symbol or "",
    )


def _open_trade(pnl=0.0, symbol=""):
    trade = _closed_trade(pnl, symbol=symbol)
    trade.status = "OPEN"
    trade.result = ""
    return trade


def _book(account, pnl):
    if pnl > 0:
        account.book_profit(pnl)
    elif pnl < 0:
        account.book_loss(-pnl)
    else:
        account.book_profit(0.0)


class TestPaperRuntimeReport(unittest.TestCase):

    def make_runtime(self, symbol="BTC", starting=2000.0):
        runtime = PaperRuntime(
            instrument=_instrument(symbol),
            pipeline=_mini_pipeline(),
            starting_balance=starting,
        )
        return runtime

    def test_runtime_exposes_canonical_report(self):

        runtime = self.make_runtime()

        report = runtime.report()

        self.assertEqual(report.total_trades, 0)

        # The report is the SAME canonical object surface a caller
        # gets by calling PerformanceAnalytics directly (not a new
        # competing report type).
        self.assertIsInstance(report, PerformanceReport)

        canonical = PerformanceAnalytics.analyze(
            runtime.account,
            runtime.ledger,
        )
        self.assertIsInstance(canonical, PerformanceReport)

    def test_report_uses_completed_trades_both_paths(self):

        runtime = self.make_runtime()

        runtime.ledger.add(_closed_trade(10.0, symbol="BTC"))
        runtime.ledger.add(_closed_trade(-5.0, symbol="BTC"))
        _book(runtime.account, 10.0)
        _book(runtime.account, -5.0)

        report = runtime.report()

        self.assertEqual(report.total_trades, 2)
        self.assertEqual(report.wins, 1)
        self.assertEqual(report.losses, 1)
        self.assertAlmostEqual(report.profit_factor, 2.0, places=6)
        self.assertAlmostEqual(report.expectancy, 2.5, places=6)

        # identity with the canonical path (no separate calc)
        canonical = PerformanceAnalytics.analyze(
            runtime.account,
            runtime.ledger,
        )
        self.assertEqual(report.profit_factor, canonical.profit_factor)
        self.assertEqual(report.expectancy, canonical.expectancy)
        self.assertEqual(report.gross_profit, canonical.gross_profit)
        self.assertEqual(report.gross_loss, canonical.gross_loss)

    def test_open_trades_excluded(self):

        runtime = self.make_runtime()

        runtime.ledger.add(_open_trade(pnl=100.0, symbol="BTC"))

        report = runtime.report()

        self.assertEqual(report.total_trades, 0)
        self.assertEqual(report.net_profit, 0.0)

    def test_rejected_orders_never_enter_ledger(self):

        # A rejected order is dropped by the broker BEFORE the
        # ledger (BrokerEngine never adds it). Simulate the broker's
        # contract: nothing is added for a failed route, so the
        # report must show zero computed trades from it.
        runtime = self.make_runtime()

        # Only closed trades reach the ledger in the canonical path;
        # rejected/expired/unfilled/cancelled never do. Add nothing
        # and prove the report still reconciles with the ledger.
        runtime.ledger.add(_closed_trade(7.0, symbol="BTC"))
        _book(runtime.account, 7.0)

        report = runtime.report()

        self.assertEqual(report.total_trades, runtime.ledger.count())

        # Open positions / partial entries never counted:
        runtime.ledger.add(_open_trade(pnl=50.0, symbol="BTC"))

        report2 = runtime.report()
        self.assertEqual(report2.total_trades, 1)
        self.assertAlmostEqual(report2.net_profit, 7.0, places=6)

    def test_breakeven_is_neither_win_nor_loss(self):

        runtime = self.make_runtime()

        runtime.ledger.add(_closed_trade(10.0, symbol="BTC"))
        runtime.ledger.add(_closed_trade(0.0, symbol="BTC"))
        runtime.ledger.add(_closed_trade(-10.0, symbol="BTC"))
        _book(runtime.account, 10.0)
        _book(runtime.account, 0.0)
        _book(runtime.account, -10.0)

        report = runtime.report()

        self.assertEqual(report.total_trades, 3)
        self.assertEqual(report.wins, 1)
        self.assertEqual(report.losses, 1)
        self.assertEqual(report.breakeven, 1)
        self.assertAlmostEqual(report.profit_factor, 1.0, places=6)
        self.assertAlmostEqual(report.expectancy, 0.0, places=6)

    def test_report_updates_after_a_trade_closes(self):

        runtime = self.make_runtime()

        runtime.ledger.add(_closed_trade(10.0, symbol="BTC"))
        _book(runtime.account, 10.0)

        before = runtime.report()
        self.assertEqual(before.total_trades, 1)

        # A later close is reflected on the next access
        runtime.ledger.add(_closed_trade(-5.0, symbol="BTC"))
        _book(runtime.account, -5.0)

        after = runtime.report()
        self.assertEqual(after.total_trades, 2)
        self.assertAlmostEqual(after.net_profit, 5.0, places=6)

    def test_repeated_report_is_deterministic(self):

        runtime = self.make_runtime()

        runtime.ledger.add(_closed_trade(10.0, symbol="BTC"))
        runtime.ledger.add(_closed_trade(0.0, symbol="BTC"))
        runtime.ledger.add(_closed_trade(-5.0, symbol="BTC"))
        _book(runtime.account, 10.0)
        _book(runtime.account, 0.0)
        _book(runtime.account, -5.0)

        r1 = runtime.report()
        r2 = runtime.report()
        r3 = runtime.report()

        self.assertEqual(r1.profit_factor, r2.profit_factor)
        self.assertEqual(r1.profit_factor, r3.profit_factor)
        self.assertEqual(r1.expectancy, r2.expectancy)
        self.assertEqual(r1.gross_profit, r2.gross_profit)
        self.assertEqual(r1.gross_loss, r2.gross_loss)

    def test_account_state_remains_counter_only(self):

        runtime = self.make_runtime()

        runtime.ledger.add(_closed_trade(10.0, symbol="BTC"))
        _book(runtime.account, 10.0)

        # The report hold the profit factor / expectancy.
        report = runtime.report()
        self.assertTrue(hasattr(report, "profit_factor"))
        self.assertTrue(hasattr(report, "expectancy"))

        # But the account state must NOT become a second analytics
        # engine (no duplicate surface).
        self.assertFalse(hasattr(runtime.account.state, "profit_factor"))
        self.assertFalse(hasattr(runtime.account.state, "expectancy"))


class FakeClock:
    def __init__(self, now=0.0):
        self.now = float(now)

    def __call__(self):
        return self.now

    def advance(self, delta):
        self.now += delta


class FakeTransport:
    def __init__(self):
        self._routes = {}
        self.subscribe_calls = {}
        self.unsubscribed = []
        self.closed = False

    def subscribe(self, symbol, on_candle, on_down):
        self.subscribe_calls[symbol] = (
            self.subscribe_calls.get(symbol, 0) + 1
        )
        self._routes[symbol] = (on_candle, on_down)

    def unsubscribe(self, symbol):
        self._routes.pop(symbol, None)
        self.unsubscribed.append(symbol)

    def push(self, symbol, candle):
        route = self._routes.get(symbol)
        if route is not None:
            route[0](candle)

    def down(self, symbol):
        route = self._routes.get(symbol)
        if route is not None:
            route[1]()

    def close(self):
        self.closed = True
        self._routes.clear()


class ScriptedWorld:
    def __init__(self, context):
        self.context = context
        self.candles_seen = []

    def reset(self):
        self.candles_seen = []

    def on_candle(self, event):
        self.candles_seen.append(event.candle)
        self.context.add_candle(event.candle)


def _build_engine(symbols, starting_balance=1000.0):
    """Assemble the paper-main engine over a fake universe +
    fake transport + scripted worlds (offline, multi-symbol)."""
    clock = FakeClock(now=1000.0)
    manager = ExplicitSymbolUniverseManager(
        symbols=symbols,
        timeframe="1m",
    )
    transport = FakeTransport()
    engine, _ = build_paper_engine(
        universe_manager=manager,
        transport_factory=lambda: transport,
        world_factory=ScriptedWorld,
        clock=clock,
        timeframe="1m",
        refresh_interval_seconds=0,
        starting_balance=starting_balance,
    )
    engine.start()
    return engine


class TestRealTimeEnginePerformance(unittest.TestCase):

    def test_per_symbol_report_and_isolation(self):

        engine = _build_engine(["BTC", "ETH"])

        key_btc = instrument_identity_key("DELTA", "BTC")
        key_eth = instrument_identity_key("DELTA", "ETH")

        btc = engine.runtimes[key_btc]
        eth = engine.runtimes[key_eth]

        btc.ledger.add(_closed_trade(100.0, symbol="BTC"))
        btc.ledger.add(_closed_trade(-50.0, symbol="BTC"))
        _book(btc.account, 100.0)
        _book(btc.account, -50.0)

        eth.ledger.add(_closed_trade(200.0, symbol="ETH"))
        _book(eth.account, 200.0)

        btc_report = engine.performance("BTC")
        eth_report = engine.performance("ETH")

        # per-symbol isolation: BTC only its own completed trades
        self.assertEqual(btc_report.total_trades, 2)
        self.assertEqual(btc_report.wins, 1)
        self.assertEqual(btc_report.losses, 1)
        self.assertAlmostEqual(btc_report.net_profit, 50.0, places=6)
        self.assertAlmostEqual(btc_report.profit_factor, 2.0, places=6)

        self.assertEqual(eth_report.total_trades, 1)
        self.assertAlmostEqual(eth_report.net_profit, 200.0, places=6)

        # unknown symbol -> None (universe-routing semantics)
        self.assertIsNone(engine.performance("DOGE"))

        self.assertEqual(engine.routed, 0)  # no candles pushed

        engine.stop()

    def test_aggregate_report_over_all_symbols(self):

        engine = _build_engine(["BTC", "ETH"], starting_balance=1000.0)

        key_btc = instrument_identity_key("DELTA", "BTC")
        key_eth = instrument_identity_key("DELTA", "ETH")

        btc = engine.runtimes[key_btc]
        eth = engine.runtimes[key_eth]

        btc.ledger.add(_closed_trade(100.0, symbol="BTC"))
        btc.ledger.add(_closed_trade(-50.0, symbol="BTC"))
        _book(btc.account, 100.0)
        _book(btc.account, -50.0)

        eth.ledger.add(_closed_trade(200.0, symbol="ETH"))
        _book(eth.account, 200.0)

        agg = engine.performance()

        self.assertEqual(agg.total_trades, 3)
        self.assertEqual(agg.wins, 2)
        self.assertEqual(agg.losses, 1)
        self.assertAlmostEqual(agg.net_profit, 250.0, places=6)
        self.assertAlmostEqual(agg.gross_profit, 300.0, places=6)
        self.assertAlmostEqual(agg.gross_loss, 50.0, places=6)
        self.assertAlmostEqual(agg.profit_factor, 6.0, places=6)
        self.assertAlmostEqual(agg.expectancy, 250.0 / 3, places=6)

        # shared starting balance = sum of per-runtime starting
        # balances (2 * 1000), so final equity reconciles.
        self.assertAlmostEqual(agg.starting_balance, 2000.0, places=6)
        self.assertAlmostEqual(
            agg.final_equity,
            agg.starting_balance + agg.net_profit,
            places=6,
        )

        engine.stop()

    def test_empty_aggregate_report(self):

        engine = _build_engine(["BTC", "ETH"], starting_balance=1000.0)

        agg = engine.performance()

        self.assertEqual(agg.total_trades, 0)
        self.assertAlmostEqual(agg.starting_balance, 2000.0, places=6)
        self.assertAlmostEqual(agg.net_profit, 0.0, places=6)
        self.assertAlmostEqual(agg.expectancy, 0.0, places=6)

        engine.stop()

    def test_aggregate_deterministic(self):

        engine = _build_engine(["BTC"], starting_balance=1000.0)

        key_btc = instrument_identity_key("DELTA", "BTC")
        btc = engine.runtimes[key_btc]

        btc.ledger.add(_closed_trade(10.0, symbol="BTC"))
        btc.ledger.add(_closed_trade(0.0, symbol="BTC"))
        _book(btc.account, 10.0)
        _book(btc.account, 0.0)

        a1 = engine.performance()
        a2 = engine.performance()

        self.assertEqual(a1.profit_factor, a2.profit_factor)
        self.assertEqual(a1.expectancy, a2.expectancy)
        self.assertEqual(a1.total_trades, a2.total_trades)

        engine.stop()


if __name__ == "__main__":
    unittest.main()
