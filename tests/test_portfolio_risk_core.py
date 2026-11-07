"""
====================================================

QuantEngine

Phase 8 -- Portfolio Risk & Capital Coordination (core
layer) tests

The core layer core/risk/portfolio.py::PortfolioRiskManager
is the first-class portfolio risk gate that consumes the
FROZEN OrderIntent / Trade fields and the shared portfolio
ledger. Its cardinal invariant (carried forward verbatim):

    the portfolio layer GATES (can/cannot accept an
    otherwise-valid trade) but NEVER mutates the setup's
    entry / stop / target / direction / strategy logic.

So `order_allows()` is a PURE DECISION -- it inspects the
order + current portfolio state and returns True/False, never
touching the order or the ledger. `register_open()` /
`release_closed()` are the BOOKKEEPING that updates the
ledger. A declined order is simply not accepted.

Tests cover every dimensional cap (concurrency / portfolio
risk / total notional exposure / per-symbol capital /
directional exposure / correlated exposure / daily-loss
guard), default neutrality, the legacy-compatible surface
used by PortfolioBacktester, the pure-decision invariant,
and the live/paper BrokerEngine integration (shared gate
declines an otherwise-valid trade across symbols).

Stdlib only -- no network, no real pipeline (scripted world).
====================================================
"""

import unittest

from core.risk.order_intent import OrderIntent
from core.risk.portfolio import PortfolioRiskManager


class FakeTrade:
    """Minimal Trade-like object for the release path."""

    def __init__(self, symbol="BTC", direction="BULLISH",
                 risk_amount=1.0, position_value=10.0, pnl=0.0):
        self.symbol = symbol
        self.direction = direction
        self.risk_amount = risk_amount
        self.position_value = position_value
        self.pnl = pnl


# Phase 12: stop 98.5 keeps scripted orders inside the
# mandatory gates (10 / 1.5 = 6.67:1).
def order(symbol="BTC", direction="BULLISH", risk=1.0, notional=10.0,
          expected_loss=1.0):
    return OrderIntent(
        symbol=symbol,
        direction=direction,
        entry=100.0,
        stop_loss=98.5,
        take_profit=110.0,
        quantity=1.0,
        risk_amount=risk,
        position_value=notional,
        expected_loss=expected_loss,
        valid=True,
    )


# ====================================================
# Default neutrality + invariants
# ====================================================

class TestDefaultNeutrality(unittest.TestCase):

    def test_no_caps_allows_everything(self):
        pm = PortfolioRiskManager()
        for i in range(5):
            self.assertTrue(
                pm.order_allows(order(symbol=f"S{i}", risk=5.0, notional=200.0))
            )

    def test_order_allows_is_pure_decision(self):
        pm = PortfolioRiskManager(max_positions=1)
        o = order(symbol="BTC", risk=1.0)
        before = pm.snapshot()

        # repeated pure decisions do not mutate order or ledger
        for _ in range(3):
            pm.order_allows(o)

        self.assertEqual(pm.open_positions, before["open_positions"])
        self.assertEqual(pm.current_risk, before["current_risk"])
        # the order object itself is untouched
        self.assertEqual(o.risk_amount, 1.0)
        self.assertEqual(o.entry, 100.0)

    def test_order_allows_sets_last_reason_on_decline(self):
        pm = PortfolioRiskManager(max_positions=1)
        o1 = order(symbol="BTC", risk=1.0)
        o2 = order(symbol="ETH", risk=1.0)

        pm.register_open(o1)

        self.assertFalse(pm.order_allows(o2))
        self.assertEqual(pm.last_reason, "max_positions")

    def test_default_manager_is_object_neutral_for_live(self):
        # a default (no-cap) manager never declines -- live/paper
        # behaviour is unchanged unless caps are supplied.
        from core.runtime.realtime_engine import RealTimeEngine
        pm = PortfolioRiskManager()
        self.assertIsNone(pm.max_positions)
        self.assertEqual(pm.max_portfolio_risk, 0.0)


# ====================================================
# Dimensional caps
# ====================================================

class TestConcurrencyCap(unittest.TestCase):

    def test_max_positions_gates_next_symbol(self):
        pm = PortfolioRiskManager(max_positions=1)
        o1 = order("BTC")
        o2 = order("ETH")
        self.assertTrue(pm.order_allows(o1))
        pm.register_open(o1)
        self.assertFalse(pm.order_allows(o2))
        self.assertTrue(pm.open_positions, 1)


class TestPortfolioRiskBudget(unittest.TestCase):

    def test_aggregate_risk_exceeds_budget(self):
        pm = PortfolioRiskManager(max_portfolio_risk=5.0)
        a = order("BTC", risk=3.0)
        b = order("ETH", risk=3.0)
        self.assertTrue(pm.order_allows(a))
        pm.register_open(a)
        # 3 + 3 = 6 > 5 -> declined
        self.assertFalse(pm.order_allows(b))
        self.assertEqual(pm.last_reason, "max_portfolio_risk")


class TestTotalExposureCap(unittest.TestCase):

    def test_notional_exposure_ceiling(self):
        pm = PortfolioRiskManager(
            max_total_exposure_pct=10.0, equity=1000.0
        )
        a = order("BTC", notional=60.0)
        b = order("ETH", notional=60.0)
        self.assertTrue(pm.order_allows(a))
        pm.register_open(a)
        # 60 + 60 = 120 > 100 (10% * 1000) -> declined
        self.assertFalse(pm.order_allows(b))
        self.assertEqual(pm.last_reason, "max_total_exposure")


class TestPerSymbolCapital(unittest.TestCase):

    def test_symbol_notional_cap(self):
        pm = PortfolioRiskManager(max_per_symbol_notional=100.0)
        a = order("BTC", notional=70.0)
        b = order("BTC", notional=70.0)
        self.assertTrue(pm.order_allows(a))
        pm.register_open(a)
        # same symbol 70 + 70 = 140 > 100 -> declined
        self.assertFalse(pm.order_allows(b))
        self.assertEqual(pm.last_reason, "max_per_symbol_notional")


class TestDirectionalCap(unittest.TestCase):

    def test_same_direction_gated_other_direction_allowed(self):
        pm = PortfolioRiskManager(
            max_directional_risk_pct=1.0, equity=1000.0
        )
        bull1 = order("BTC", direction="BULLISH", risk=6.0)
        bull2 = order("ETH", direction="BULLISH", risk=6.0)
        bear = order("SOL", direction="BEARISH", risk=6.0)

        self.assertTrue(pm.order_allows(bull1))
        pm.register_open(bull1)

        # 6 + 6 = 12 > 10 (1% * 1000) for BULLISH -> declined
        self.assertFalse(pm.order_allows(bull2))
        self.assertEqual(pm.last_reason, "max_directional_risk")

        # BEARISH bucket is separate -> still allowed
        self.assertTrue(pm.order_allows(bear))


class TestCorrelatedCap(unittest.TestCase):

    def test_correlation_group_gated_across_symbols(self):
        pm = PortfolioRiskManager(
            max_correlated_risk_pct=0.5, equity=1000.0,
            correlation_groups={"BTC": "crypto", "ETH": "crypto"},
        )
        a = order("BTC", risk=3.0)
        b = order("ETH", risk=3.0)
        self.assertTrue(pm.order_allows(a))
        pm.register_open(a)
        # same group crypto: 3 + 3 = 6 > 5 (0.5% * 1000) -> declined
        self.assertFalse(pm.order_allows(b))
        self.assertEqual(pm.last_reason, "max_correlated_risk")


class TestDailyLossGuard(unittest.TestCase):

    def test_realized_loss_halts_new_entries(self):
        pm = PortfolioRiskManager(
            max_daily_loss_pct=1.0, equity=1000.0
        )
        t = FakeTrade(symbol="BTC", pnl=-12.0)  # 12 > 1% * 1000 = 10
        pm.release_closed(t)
        self.assertFalse(pm.order_allows(order("ETH")))
        self.assertEqual(pm.last_reason, "max_daily_loss")


# ====================================================
# Release + ledgers
# ====================================================

class TestRelease(unittest.TestCase):

    def test_release_frees_slot_and_folds_pnl(self):
        pm = PortfolioRiskManager(max_positions=1, max_portfolio_risk=100.0)
        a = order("BTC", risk=3.0, notional=50.0)
        pm.register_open(a)
        self.assertEqual(pm.open_positions, 1)
        self.assertEqual(pm.current_risk, 3.0)

        pm.release_closed(FakeTrade(symbol="BTC", risk_amount=3.0, pnl=10.0))

        self.assertEqual(pm.open_positions, 0)
        self.assertEqual(pm.current_risk, 0.0)
        self.assertEqual(pm.realized_pnl, 10.0)
        self.assertEqual(pm.equity, 10.0)

        # slot freed -> next symbol allowed
        self.assertTrue(pm.order_allows(order("ETH")))

    def test_direction_and_correlation_ledgers(self):
        pm = PortfolioRiskManager(
            max_directional_risk_pct=100.0,
            max_correlated_risk_pct=100.0,
            correlation_groups={"BTC": "crypto"},
        )
        pm.register_open(order("BTC", direction="BULLISH", risk=2.0))
        pm.register_open(order("ETH", direction="BEARISH", risk=3.0))

        self.assertEqual(pm.direction_risk["BULLISH"], 2.0)
        self.assertEqual(pm.direction_risk["BEARISH"], 3.0)
        self.assertEqual(pm.correlated_risk["crypto"], 2.0)
        self.assertEqual(pm.correlated_risk[""], 3.0)
        self.assertEqual(pm.open_positions, 2)


class TestReset(unittest.TestCase):

    def test_reset_clears_ledger_and_pnl(self):
        pm = PortfolioRiskManager(max_positions=1)
        pm.register_open(order("BTC", risk=1.0))
        pm.release_closed(FakeTrade(symbol="BTC", risk_amount=1.0, pnl=5.0))
        pm.reset()
        self.assertEqual(pm.open_positions, 0)
        self.assertEqual(pm.realized_pnl, 0.0)
        self.assertEqual(pm.equity, 0.0)


# ====================================================
# Legacy-compatible surface (PortfolioBacktester)
# ====================================================

class TestLegacySurface(unittest.TestCase):

    def test_can_open_register_close_primitives(self):
        pm = PortfolioRiskManager(max_portfolio_risk=5.0)

        self.assertTrue(pm.can_open(3.0, symbol="BTC", position_value=50.0))
        pm.register_trade(3.0, symbol="BTC", position_value=50.0)

        self.assertFalse(pm.can_open(3.0, symbol="ETH", position_value=50.0))

        pm.close_trade(3.0, symbol="BTC", pnl=5.0)

        self.assertTrue(pm.can_open(3.0, symbol="ETH", position_value=50.0))

    def test_portfolio_backtester_accepts_core_manager(self):
        from tests.test_portfolio_risk_wiring import (
            make_factory,
            BTC_WIN_CANDLES,
            ETH_LOSS_CANDLES,
            BTC_WIN_SCRIPT,
            ETH_LOSS_SCRIPT,
        )
        from backtesting.portfolio_backtester import PortfolioBacktester

        history = {
            "BTC": list(BTC_WIN_CANDLES),
            "ETH": list(ETH_LOSS_CANDLES),
        }
        scripts = {"BTC": BTC_WIN_SCRIPT, "ETH": ETH_LOSS_SCRIPT}

        pm = PortfolioRiskManager(max_positions=1, max_portfolio_risk=100.0)
        pb = PortfolioBacktester(
            pipeline_factory=make_factory(scripts),
            risk_manager=pm,
        )
        results = pb.run(history)

        # BTC opened + closed (release before ETH runs) -> both open
        self.assertEqual(len(results["BTC"].all()), 1)
        self.assertEqual(len(results["ETH"].all()), 1)


# ====================================================
# Live/paper integration -- shared gate declines a
# valid trade when portfolio risk is exhausted.
# ====================================================

class TestLivePaperGate(unittest.TestCase):

    def test_broker_engine_shared_gate_declines_across_symbols(self):
        from core.market_state import MarketState
        from core.pipeline.pipeline_context import PipelineContext
        from core.live.broker_engine import BrokerEngine
        from core.runtime.execution_port import PaperExecutionAdapter

        class Candle:
            def __init__(self, high, low, close, ts, symbol="TEST"):
                self.high = high
                self.low = low
                self.close = close
                self.timestamp = ts
                self.symbol = symbol
                self.timeframe = "1m"

        class FakePipeline:
            def __init__(self, ctx, o):
                self.context = ctx
                self._order = o
                self.world = None
                self.event_bus = None

            def on_candle(self, ev):
                self.context.order = self._order

        def make_ctx(symbol):
            c = PipelineContext()
            c.market = MarketState(symbol=symbol, timeframe="1m")
            return c

        pm = PortfolioRiskManager(max_positions=1, max_portfolio_risk=100.0)

        def gate(o):
            if not pm.order_allows(o):
                return False
            pm.register_open(o)
            return True

        def rel(t):
            pm.release_closed(t)

        def eng(symbol):
            return BrokerEngine(
                FakePipeline(make_ctx(symbol), order(symbol, risk=3.0)),
                None,
                PaperExecutionAdapter(),
                dry_run=True,
                portfolio_gate=gate,
                portfolio_release=rel,
            )

        btc = eng("BTC")
        eth = eng("ETH")

        # BTC opens and holds (SAFE bar: no SL/TP touch)
        btc.run_candle(Candle(105, 99, 102, 0, "BTC"))
        self.assertIsNotNone(btc.current_trade)
        self.assertEqual(pm.open_positions, 1)

        # ETH's otherwise-valid order is declined (portfolio risk
        # exhausted through max_positions) -- the gate NEVER mutates
        # the order; it only declines.
        eth.run_candle(Candle(105, 99, 102, 1, "ETH"))
        self.assertIsNone(eth.current_trade)
        self.assertEqual(pm.open_positions, 1)

        # BTC closes (TP touched) -> releases the slot
        btc.run_candle(Candle(112, 101, 111, 2, "BTC"))
        self.assertEqual(pm.open_positions, 0)

        # ETH is now accepted
        eth.run_candle(Candle(105, 99, 102, 3, "ETH"))
        self.assertIsNotNone(eth.current_trade)


if __name__ == "__main__":

    unittest.main()
