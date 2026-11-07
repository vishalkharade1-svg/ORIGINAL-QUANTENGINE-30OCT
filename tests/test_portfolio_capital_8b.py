"""
====================================================

QuantEngine

Phase 8B -- Shared Portfolio Capital & Allocation tests

Core/risk/capital.py (SharedCapital), core/risk/
portfolio_state.py (PortfolioState + CapitalCandidate),
core/risk/allocator.py (CapitalAllocator + AllocationResult).

A narrowly-scoped infrastructure layer: shared reservation-based
capital, deterministic allocation against a portfolio risk budget
+ capital envelope, and a real CAPITAL LIFECYCLE:

    Candidate A --reserve--> A open
    Candidate B --reserve--> B open
    Candidate A --close / release--> A freed
    Candidate C --now allowed-->

THE INVARIANT (carried forward): the gate (can_accept /
can_reserve / order_allows) is a PURE DECISION -- never mutates a
candidate/order/strategy; reserve/release/cancel are bookkeeping.
The allocator is DELIBERATELY DETERMINISTIC (strict order, no
ranking -- opportunity ranking belongs to a future 8C/Confluence
layer, NOT here).

Tests cover the listed Phase 8B behaviors: shared equity /
available / reserved capital; risk reservations; release on close;
multiple symbols; simultaneous candidates; directional +
correlation limits; insufficient capital; deterministic
allocation; reset; failed execution after reservation; rejected
order does not consume capital; closed trade releases capital;
backtest/paper parity; and the capital-lifecycle sequence.

Stdlib only -- scripted world / direct unit tests, no network.
====================================================
"""

import unittest

from core.risk.capital import SharedCapital
from core.risk.allocator import CapitalAllocator, AllocationResult
from core.risk.portfolio_state import CapitalCandidate, PortfolioState


def cand(symbol="X", direction="BULLISH", risk=1.0, capital=1000.0,
         group=None):
    return CapitalCandidate(
        symbol=symbol, direction=direction,
        correlation_group=group, risk=risk, capital=capital,
    )


def state(**kwargs):
    kwargs.setdefault("equity", 10000.0)
    return PortfolioState(**kwargs)


# ====================================================
# SharedCapital -- equity / available / reserved
# ====================================================

class TestSharedCapital(unittest.TestCase):

    def test_equity_available_reserved_buckets(self):
        cap = SharedCapital(equity=10000.0)
        self.assertEqual(cap.equity, 10000.0)
        self.assertEqual(cap.available_capital, 10000.0)
        self.assertEqual(cap.reserved_capital, 0.0)

    def test_reserve_moves_capital_out_of_available(self):
        cap = SharedCapital(equity=10000.0)
        self.assertTrue(cap.can_reserve(4000.0))
        cap.reserve("r1", 4000.0)
        self.assertEqual(cap.reserved_capital, 4000.0)
        self.assertEqual(cap.available_capital, 6000.0)

    def test_release_returns_capital_and_folds_pnl(self):
        cap = SharedCapital(equity=10000.0)
        cap.reserve("r1", 4000.0)
        cap.release("r1", pnl=50.0)
        self.assertEqual(cap.reserved_capital, 0.0)
        self.assertEqual(cap.available_capital, 10050.0)
        self.assertEqual(cap.equity, 10050.0)

    def test_insufficient_capital_reason(self):
        cap = SharedCapital(equity=1000.0)
        self.assertFalse(cap.can_reserve(5000.0))
        self.assertEqual(cap.last_reason, "insufficient_capital")

    def test_cancel_returns_capital_no_pnl(self):
        cap = SharedCapital(equity=10000.0)
        cap.reserve("r1", 4000.0)
        cap.cancel("r1")
        self.assertEqual(cap.reserved_capital, 0.0)
        self.assertEqual(cap.equity, 10000.0)  # no PnL folded


# ====================================================
# Deterministic allocation (the canonical example)
# ====================================================

class TestDeterministicAllocation(unittest.TestCase):

    def test_user_example_sol_deferred_against_2r(self):
        s = state(max_portfolio_risk=2.0)
        alloc = CapitalAllocator(s)
        res = alloc.allocate([
            cand("BTC", risk=0.8, capital=3000.0),
            cand("ETH", risk=0.7, capital=3000.0),
            cand("SOL", risk=0.9, capital=3000.0),
        ])
        self.assertTrue(res[0].accepted)   # BTC ACCEPT 0.8R
        self.assertTrue(res[1].accepted)   # ETH ACCEPT 0.7R
        self.assertFalse(res[2].accepted)  # SOL REJECT/DEFER
        self.assertEqual(res[2].reason, "risk_budget")
        self.assertEqual(s.remaining_budget, 0.5)  # 2 - 0.8 - 0.7

    def test_allocation_is_deterministic(self):
        def run():
            s = state(max_portfolio_risk=2.0)
            alloc = CapitalAllocator(s)
            return [(r.symbol, r.accepted) for r in alloc.allocate([
                cand("A", risk=0.6, capital=1000.0),
                cand("B", risk=0.6, capital=1000.0),
                cand("C", risk=0.9, capital=1000.0),
                cand("D", risk=0.5, capital=1000.0),
            ])]
        self.assertEqual(run(), run())

    def test_order_not_ranked_first_come_first_served(self):
        # Same candidates, different order -> different winners, but
        # ALWAYS deterministic for a given input order (no ranking).
        s = state(max_portfolio_risk=2.0)
        alloc = CapitalAllocator(s)
        res = alloc.allocate([
            cand("SOL", risk=1.4, capital=1000.0),
            cand("ETH", risk=0.7, capital=1000.0),
        ])
        self.assertTrue(res[0].accepted)   # 1.4 <= 2
        self.assertFalse(res[1].accepted)  # 1.4+0.7=2.1 > 2

    def test_simultaneous_candidates_reserve_in_order(self):
        s = state(max_portfolio_risk=1.5)
        alloc = CapitalAllocator(s)
        res = alloc.allocate([
            cand("BTC", risk=0.8, capital=1000.0),
            cand("ETH", risk=0.8, capital=1000.0),
        ])
        self.assertTrue(res[0].accepted)
        self.assertFalse(res[1].accepted)
        self.assertEqual(s.open_positions, 1)


# ====================================================
# The capital lifecycle (the crucial sequence)
# ====================================================

class TestCapitalLifecycle(unittest.TestCase):

    def test_a_reserve_b_reserve_a_close_c_now_allowed(self):
        s = state(max_portfolio_risk=2.0)
        alloc = CapitalAllocator(s)

        # Candidate A -> reserve
        rA = alloc.allocate([cand("A", risk=1.0, capital=4000.0)])[0]
        self.assertTrue(rA.accepted)
        self.assertEqual(s.open_positions, 1)

        # Candidate B -> reserve
        rB = alloc.allocate([cand("B", risk=1.0, capital=4000.0)])[0]
        self.assertTrue(rB.accepted)
        self.assertEqual(s.open_positions, 2)

        # Candidate A closes -> release
        alloc.release(rA.reservation_id, pnl=10.0)
        self.assertEqual(s.open_positions, 1)
        self.assertEqual(s.equity, 10010.0)

        # Candidate C -> now allowed
        rC = alloc.allocate([cand("C", risk=1.0, capital=4000.0)])[0]
        self.assertTrue(rC.accepted)
        self.assertEqual(s.open_positions, 2)

    def test_closed_trade_releases_capital_to_pool(self):
        s = state(equity=5000.0)
        alloc = CapitalAllocator(s)
        r = alloc.allocate([cand("BTC", risk=1.0, capital=3000.0)])[0]
        self.assertTrue(r.accepted)
        self.assertEqual(s.available_capital, 2000.0)
        alloc.release(r.reservation_id, pnl=0.0)
        self.assertEqual(s.available_capital, 5000.0)

    def test_rejected_order_does_not_consume_capital(self):
        s = state(equity=1000.0)  # tiny equity
        alloc = CapitalAllocator(s)
        res = alloc.allocate([
            cand("BTC", risk=1.0, capital=600.0),
            cand("ETH", risk=1.0, capital=600.0),
        ])
        self.assertTrue(res[0].accepted)   # 600 <= 1000
        self.assertFalse(res[1].accepted)  # insufficient capital
        self.assertEqual(res[1].reason, "insufficient_capital")
        self.assertEqual(s.available_capital, 400.0)
        self.assertEqual(s.open_positions, 1)

    def test_failed_execution_after_reservation_cancels(self):
        s = state()
        alloc = CapitalAllocator(s)
        r = alloc.allocate([cand("BTC", risk=1.0, capital=3000.0)])[0]
        self.assertTrue(r.accepted)
        self.assertEqual(s.open_positions, 1)
        # execution fails -> cancel the reservation (no PnL)
        alloc.cancel(r.reservation_id)
        self.assertEqual(s.open_positions, 0)
        self.assertEqual(s.equity, 10000.0)
        self.assertEqual(s.available_capital, 10000.0)


# ====================================================
# Directional / correlation / per-symbol / exposure
# ====================================================

class TestLimits(unittest.TestCase):

    def test_directional_limit(self):
        # 1% of 10000 equity = 100 risk cap per direction.
        s = state(max_directional_risk_pct=1.0)
        alloc = CapitalAllocator(s)
        a = alloc.allocate([cand("BTC", direction="BULLISH", risk=60.0)])[0]
        b = alloc.allocate([cand("ETH", direction="BULLISH", risk=60.0)])[0]
        c = alloc.allocate([cand("SOL", direction="BEARISH", risk=60.0)])[0]
        self.assertTrue(a.accepted)
        self.assertFalse(b.accepted)             # bull 60+60=120 > 100
        self.assertEqual(b.reason, "directional_limit")
        self.assertTrue(c.accepted)              # separate direction

    def test_correlation_limit(self):
        # 0.5% of 10000 = 50 risk cap per group.
        s = state(max_correlated_risk_pct=0.5,
                  correlation_groups={"BTC": "crypto", "ETH": "crypto"})
        alloc = CapitalAllocator(s)
        a = alloc.allocate([cand("BTC", risk=30.0)])[0]
        b = alloc.allocate([cand("ETH", risk=30.0)])[0]
        self.assertTrue(a.accepted)
        self.assertFalse(b.accepted)             # crypto 30+30=60 > 50
        self.assertEqual(b.reason, "correlation_limit")

    def test_per_symbol_capital_limit(self):
        s = state(max_per_symbol_capital=1500.0)
        alloc = CapitalAllocator(s)
        a = alloc.allocate([cand("BTC", capital=1000.0)])[0]
        b = alloc.allocate([cand("BTC", capital=1000.0)])[0]
        c = alloc.allocate([cand("ETH", capital=1000.0)])[0]
        self.assertTrue(a.accepted)
        self.assertFalse(b.accepted)             # same symbol 2000 > 1500
        self.assertEqual(b.reason, "per_symbol_capital")
        self.assertTrue(c.accepted)              # different symbol


# ====================================================
# Multiple symbols + reset
# ====================================================

class TestMultipleAndReset(unittest.TestCase):

    def test_multiple_symbols_independent_reservations(self):
        s = state(max_portfolio_risk=3.0)
        alloc = CapitalAllocator(s)
        res = alloc.allocate([
            cand("BTC", risk=1.0, capital=1000.0),
            cand("ETH", risk=1.0, capital=1000.0),
            cand("SOL", risk=1.0, capital=1000.0),
        ])
        self.assertTrue(all(r.accepted for r in res))
        self.assertEqual(s.open_positions, 3)
        self.assertEqual(s.total_risk, 3.0)
        self.assertEqual(s.reserved_capital, 3000.0)

    def test_reset_clears_full_session(self):
        s = state(max_portfolio_risk=2.0)
        alloc = CapitalAllocator(s)
        alloc.allocate([cand("BTC", risk=1.0, capital=1000.0)])
        alloc.allocate([cand("ETH", risk=1.0, capital=1000.0)])
        self.assertEqual(s.open_positions, 2)
        s.reset()
        self.assertEqual(s.open_positions, 0)
        self.assertEqual(s.total_risk, 0.0)
        self.assertEqual(s.reserved_capital, 0.0)
        self.assertEqual(s.equity, 10000.0)


# ====================================================
# Parity -- identical lifecycle through the portfolio
# backtest AND paper paths on ONE shared state.
# ====================================================

class TestBacktestPaperParity(unittest.TestCase):

    def _make_state_gate(self, pstate, rids):
        from core.risk.portfolio_state import CapitalCandidate

        def gate(order):
            cand_obj = CapitalCandidate.from_order(order)
            if not pstate.can_accept(cand_obj):
                return False
            rids[getattr(order, "symbol", None)] = pstate.reserve(cand_obj)
            return True

        def rel(trade):
            rid = rids.pop(getattr(trade, "symbol", None), None)
            if rid is not None:
                pstate.release(rid, pnl=getattr(trade, "pnl", 0.0))

        return gate, rel

    def test_portfolio_backtester_state_lifecycle(self):
        from tests.test_portfolio_risk_wiring import (
            make_factory, BTC_WIN_CANDLES, BTC_WIN_SCRIPT,
        )
        from backtesting.portfolio_backtester import PortfolioBacktester

        pstate = PortfolioState(equity=10000.0)
        pb = PortfolioBacktester(
            pipeline_factory=make_factory({"BTC": BTC_WIN_SCRIPT}),
            portfolio_state=pstate,
        )
        result = pb.run({"BTC": list(BTC_WIN_CANDLES)})

        self.assertEqual(len(result["BTC"].all()), 1)
        # reservation released + PnL folded into shared equity
        self.assertEqual(pstate.open_positions, 0)
        self.assertEqual(pstate.equity, 10010.0)
        self.assertEqual(pb._reservation_by_symbol, {})

    def test_broker_engine_state_lifecycle_parity(self):
        from core.market_state import MarketState
        from core.pipeline.pipeline_context import PipelineContext
        from core.risk.order_intent import OrderIntent
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

        order = OrderIntent(
            symbol="BTC", direction="BULLISH", entry=100.0,
            stop_loss=98.5, take_profit=110.0, quantity=1.0,
            risk_amount=3.0, position_value=100.0, valid=True,
        )

        ctx = PipelineContext()
        ctx.market = MarketState(symbol="BTC", timeframe="1m")

        pstate = PortfolioState(equity=10000.0)
        rids = {}
        gate, rel = self._make_state_gate(pstate, rids)

        engine = BrokerEngine(
            FakePipeline(ctx, order), None, PaperExecutionAdapter(),
            dry_run=True, portfolio_gate=gate, portfolio_release=rel,
        )

        engine.run_candle(Candle(105, 99, 102, 0, "BTC"))   # open
        self.assertEqual(pstate.open_positions, 1)
        self.assertEqual(pstate.reserved_capital, 100.0)

        engine.run_candle(Candle(112, 101, 111, 1, "BTC"))  # TP close
        # Parity: identical resulting shared state as the backtest
        # path above (+10 PnL, reservation released).
        self.assertEqual(pstate.open_positions, 0)
        self.assertEqual(pstate.equity, 10010.0)


if __name__ == "__main__":

    unittest.main()
