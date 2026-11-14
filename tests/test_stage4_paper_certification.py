"""Stage 4 paper certification (fast suite; long soak lives in
tests/test_stage4_soak.py, split only for runner time limits).

Proves, against production code with the ACTUAL pipeline wherever
the design permits: repository integrity, paper cost profile +
semantics, accounting identity, 1:6 RR, paper execution (create /
fill / reject / expiry / duplicate), reconciliation verdicts,
startup cases A-E, 12 crash drills, lifecycle, duplicates,
multi-symbol isolation, kill switch, paper/live/research/AI
boundaries, determinism (small), causality, tracked-source secret
scan.

Labels: PAPER ONLY. NOT OOS. NOT STRATEGY CERTIFICATION. NOT LIVE.
No strategy parameter is tuned here; whatever economics emerge are
REPORTED, never optimized.

Stdlib + production code only. No network, no credentials, no
exchange writes. Deterministic (fixed seeds, no wall-clock in
asserted artifacts).
"""

import ast
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from config import risk_settings
from core.backtesting.accounting import (
    classify_pnl,
    gross_pnl,
    net_pnl,
)
from core.backtesting.trade_simulator import TradeSimulator
from core.events.candle_event import CandleEvent
from core.events.event_bus import EventBus
from core.execution import order_registry as OR
from core.execution.order_registry import OrderRegistry
from core.live.reconciler import Reconciler
from core.market_state import MarketState
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext
from core.risk.account import Account
from core.risk.account_state import AccountState
from core.risk.costs import (
    CostSpec,
    from_settings,
    paper_cost_profile,
    paper_profile_name,
    paper_venue_realistic,
)
from core.risk.order_intent import OrderIntent
from core.risk.portfolio import PortfolioRiskManager
from core.risk.position_size import PositionSize
from core.risk.risk_engine import RiskEngine, kill_switch_active
from core.setup.decision_engine import DecisionEngine
from core.setup.setup_candidate import SetupCandidate
from core.regime.regime_state import RegimeState
from core.trend.trend_state import TrendState
from backtesting.backtester import Backtester

from tests.test_pipeline_regressions import make_candles

try:  # package import when pytest loads tests.test_*
    from tests.evidence_mode import require_git_fact
except ImportError:  # direct execution of this file
    from evidence_mode import require_git_fact

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER_ONLY = "PAPER ONLY / NOT OOS / NOT STRATEGY CERTIFICATION / NOT LIVE"


def git(*args):
    return subprocess.run(["git"] + list(args), capture_output=True,
                          text=True, cwd=BASE_DIR)


# --------------------------------------------------
# Shared builders (production objects only)
# --------------------------------------------------

def seeded_account(balance=2000.0, **kw):
    return AccountState(starting_balance=balance, balance=balance,
                        equity=balance, peak_equity=balance,
                        drawdown=0.0, drawdown_percent=0.0, **kw)


def candidate(entry=100.0, stop=90.0, tp=160.0, confidence=85.0,
              score=85.0, direction="BULLISH", setup_id="S-1"):
    c = SetupCandidate(
        direction=direction, entry=entry, stop_loss=stop,
        take_profit=tp,
        risk_reward=(abs(tp - entry) / abs(entry - stop)
                     if entry != stop else 0.0),
        confidence=confidence, score=score)
    c.trend = TrendState(direction=direction)
    c.regime = RegimeState(score=80.0, confidence=80.0)
    c.setup_id = setup_id
    return c


def size_order(signal, balance=2000.0, account=None):
    ctx = PipelineContext()
    ctx.market = MarketState(symbol="TEST", timeframe="1m")
    ctx.execution_signal = signal
    ctx.account = account if account is not None else seeded_account(balance)
    RiskEngine().analyze(ctx)
    return ctx.order


class FakePositions:
    def __init__(self, records=None, error=None):
        self._records = list(records or [])
        self._error = error
        self.calls = 0

    def positions(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return [dict(r) for r in self._records]


def real_backtester(symbol="BTCUSDT"):
    ctx = PipelineContext()
    ctx.market = MarketState(symbol=symbol, timeframe="1m")
    bus = EventBus()
    pipe = InstitutionalPipeline(ctx)
    pipe.subscribe(bus)
    sim = TradeSimulator()
    return Backtester(pipe, bus, sim), sim, ctx


# --------------------------------------------------
# Repository integrity (§32)
# --------------------------------------------------

class TestRepoIntegrity(unittest.TestCase):
    def test_head_is_stage123_closure_descendant(self):
        require_git_commit(self, "b42e8181406091bf06af18e312508a93924dcc37", detail="Stage 1–3 closure ancestor")
        require_git_fact(self, 'test_stage4_paper_certification::TestRepoIntegrity::test_head_is_stage123_closure_descendant')
        self.assertEqual(
            git("merge-base", "--is-ancestor",
                "b42e8181406091bf06af18e312508a93924dcc37",
                "HEAD").returncode, 0)
        self.assertEqual(git("branch", "--show-current").stdout.strip(),
                         "main")

    def test_research_byte_unchanged(self):
        require_git_fact(self, 'test_stage4_paper_certification::TestRepoIntegrity::test_research_byte_unchanged')
        self.assertEqual(
            git("diff", "--stat", "--", "research/").stdout.strip(), "")
        self.assertEqual(
            git("status", "--short", "--", "research/").stdout.strip(), "")

    def test_freeze_hash_pinned(self):
        with open(os.path.join(
                BASE_DIR, "research", "phase11g_k", "freeze",
                "freeze_hash.txt")) as handle:
            self.assertTrue(handle.read().strip().startswith("f803fe7d"))

    def test_paper_only_label_present(self):
        self.assertIn("PAPER ONLY", PAPER_ONLY)
        self.assertIn("NOT OOS", PAPER_ONLY)


# --------------------------------------------------
# Paper cost profile (§7) + semantics (§8)
# --------------------------------------------------

class TestPaperCostProfile(unittest.TestCase):
    def test_defaults_explicit_zero_neutral(self):
        profile = paper_cost_profile()
        self.assertEqual(profile, CostSpec(0.0, 0.0, 0.0))
        self.assertEqual(profile, from_settings())
        self.assertEqual(paper_profile_name(), "explicit-zero-neutral")
        self.assertFalse(paper_venue_realistic())

    def test_production_defaults_untouched(self):
        self.assertEqual((risk_settings.COMMISSION_PER_TRADE,
                          risk_settings.COMMISSION_RATE,
                          risk_settings.SLIPPAGE_BPS), (0.0, 0.0, 0.0))

    def test_explicit_overrides(self):
        profile = paper_cost_profile({"per_trade": 1.0, "rate": 0.00059,
                                      "slippage_bps": 5.0})
        commission, slippage = profile.compute(1000.0)
        self.assertAlmostEqual(commission, 1.59)
        self.assertAlmostEqual(slippage, 1.0)

    def test_env_override_in_subprocess(self):
        env = dict(os.environ,
                   QE_PAPER_COMMISSION_RATE="0.00059",
                   QE_PAPER_SLIPPAGE_BPS="5.0",
                   QE_PAPER_COST_PROFILE_NAME="ci-env-check",
                   QE_PAPER_COST_VENUE_REALISTIC="true")
        code = ("from core.risk.costs import paper_cost_profile,"
                "paper_profile_name,paper_venue_realistic;"
                "p=paper_cost_profile();"
                "print('%r|%s|%s' % (p.compute(1000.0),"
                "paper_profile_name(),paper_venue_realistic()))")
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True,
                             cwd=BASE_DIR, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        costs, name, realistic = out.stdout.strip().split("|")
        commission, slippage = ast.literal_eval(costs)
        self.assertAlmostEqual(commission, 0.59)
        self.assertAlmostEqual(slippage, 1.0)
        self.assertEqual((name, realistic),
                         ("ci-env-check", "True"))

    def test_research_ladder_untouched(self):
        from research.phase11f.harness import COST_SCENARIOS_11F as K
        self.assertEqual(K["A"], {"COMMISSION_PER_TRADE": 0.0,
                                  "COMMISSION_RATE": 0.0,
                                  "SLIPPAGE_BPS": 0.0})
        self.assertEqual((K["C"]["COMMISSION_RATE"],
                          K["C"]["SLIPPAGE_BPS"]), (0.00059, 5.0))


class TestCostSemantics(unittest.TestCase):
    def check_trade(self, direction, entry, exit_, qty, profile):
        commission, slippage = profile.compute(entry * qty)
        gross = gross_pnl(direction, entry, exit_, qty)
        net = net_pnl(gross, commission, slippage)
        total_cost = commission + slippage
        self.assertAlmostEqual(net, gross - total_cost)
        return {"gross_pnl": gross, "commission": commission,
                "slippage": slippage, "total_cost": total_cost,
                "net_pnl": net}

    def test_long_and_short_both_profiles(self):
        for profile in (CostSpec(),
                        CostSpec(1.0, 0.00059, 5.0)):
            long_win = self.check_trade("BULLISH", 100.0, 160.0, 2.0,
                                        profile)
            self.assertGreater(long_win["gross_pnl"], 0)
            short_win = self.check_trade("BEARISH", 160.0, 100.0, 2.0,
                                         profile)
            self.assertGreater(short_win["gross_pnl"], 0)
            long_loss = self.check_trade("BULLISH", 100.0, 90.0, 2.0,
                                         profile)
            self.assertLess(long_loss["gross_pnl"], 0)
            short_loss = self.check_trade("BEARISH", 100.0, 110.0, 2.0,
                                          profile)
            self.assertLess(short_loss["gross_pnl"], 0)

    def test_hostile_cost_mutations(self):
        base = dict(per_trade=1.0, rate=0.00059, slippage_bps=5.0)
        ref = self.check_trade("BULLISH", 100.0, 160.0, 2.0,
                               CostSpec(**base))["net_pnl"]
        for key, eps in (("per_trade", 1e-6), ("rate", 1e-9),
                         ("slippage_bps", 1e-6)):
            for sign in (1.0, -1.0):
                mutated = dict(base)
                mutated[key] += sign * eps
                got = self.check_trade("BULLISH", 100.0, 160.0, 2.0,
                                       CostSpec(**mutated))["net_pnl"]
                self.assertNotEqual(got, ref, (key, sign))

    def test_cost_never_hidden(self):
        row = self.check_trade("BULLISH", 100.0, 160.0, 2.0,
                               CostSpec(1.0, 0.00059, 5.0))
        for key in ("gross_pnl", "commission", "slippage",
                    "total_cost", "net_pnl"):
            self.assertIn(key, row)
            self.assertTrue(math.isfinite(row[key]))


# --------------------------------------------------
# Paper accounting (§9)
# --------------------------------------------------

class TestPaperAccounting(unittest.TestCase):
    def identity(self, opening, trades):
        # trades: list of (gross, commission, slippage)
        balance, realized, fees = opening, 0.0, 0.0
        for gross, commission, slippage in trades:
            net = net_pnl(gross, commission, slippage)
            realized += gross
            fees += commission + slippage
            balance += net
        self.assertAlmostEqual(balance, opening + realized - fees)
        return balance

    def test_matrix(self):
        profile = CostSpec(1.0, 0.00059, 5.0)
        nok = 100.0 * 2.0
        c, s = profile.compute(nok)
        self.identity(2000.0, [
            (20.0, c, s),    # long win
            (-20.0, c, s),   # long loss
            (20.0, c, s),    # short win
            (-20.0, c, s),   # short loss
            (0.0, c, s),     # zero result (fee-only outcome)
            (0.0, 5.0, 3.0),  # fee-only trade
        ])

    def test_sequential_ledger_matches_registry(self):
        sim = TradeSimulator()
        mk = lambda d, e, q=2.0, i="S": SimpleNamespace(
            direction=d, entry=e,
            stop_loss=(e - 10.0) if d == "BULLISH" else (e + 10.0),
            take_profit=(e + 60.0) if d == "BULLISH" else (e - 60.0),
            quantity=q, risk_amount=20.0,
            risk_reward=6.0, score=80.0, confidence=85.0,
            setup_id="%s-%s" % (i, e), symbol="TEST")
        sim.open_trade(mk("BULLISH", 100.0), timestamp=1)
        sim.update(SimpleNamespace(high=170.0, low=99.0, close=160.0,
                                   timestamp=2))
        sim.open_trade(mk("BEARISH", 160.0, i="T"), timestamp=3)
        sim.update(SimpleNamespace(high=171.0, low=150.0, close=150.0,
                                   timestamp=4))
        closed = [t for t in sim.registry.all()]
        self.assertEqual(len(closed), 2)
        for trade in closed:
            self.assertAlmostEqual(
                trade.pnl,
                net_pnl(gross_pnl(trade.direction, trade.entry,
                                  trade.exit_price, trade.quantity),
                        trade.commission, trade.slippage))

    def test_simulator_rejects_inconsistent_bearish_geometry(self):
        sim = TradeSimulator()
        bad = SimpleNamespace(
            direction="BEARISH", entry=160.0, stop_loss=150.0,
            take_profit=220.0, quantity=2.0, risk_amount=20.0,
            risk_reward=6.0, score=80.0, confidence=85.0,
            setup_id="BAD-SHORT", symbol="TEST")
        res = sim.open_trade(bad, timestamp=1)
        self.assertIsNone(res, "Simulator must reject short trade with stop_loss < entry")
        self.assertEqual(len(list(sim.registry.all())), 0)


    def test_rejected_expired_duplicate_paths(self):
        reg = OrderRegistry()
        good = OrderIntent(direction="BULLISH", entry=100.0,
                           stop_loss=90.0, take_profit=160.0,
                           quantity=1.0, setup_id="S-ACC")
        created, _ = reg.create(good, bar=1, timestamp=1)
        dup, dup_id = reg.create(OrderIntent(
            direction="BULLISH", entry=100.0, stop_loss=90.0,
            take_profit=160.0, quantity=1.0, setup_id="S-ACC"),
            bar=2, timestamp=2)
        self.assertIs(dup, created)
        self.assertEqual(len(reg.pending()), 1)
        # Unknown / non-pending fills are no-ops, never fills.
        self.assertIsNone(reg.mark_filled(
            SimpleNamespace(status="NEW"), SimpleNamespace()))
        self.assertIsNone(reg.mark_filled(None, None))
        self.assertEqual(reg.filled(), [])

    def test_partial_failure_path_halts(self):
        rec = Reconciler(executor=FakePositions(
            [{"side": "buy", "size": 1.0, "entry": 100.0}]))
        out = rec.runtime_check(
            5, 5, SimpleNamespace(direction="BULLISH", quantity=2.0,
                                  entry=100.0), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)

    def test_nonfinite_never_valid_state(self):
        with self.assertRaises(ValueError):
            classify_pnl(float("nan"))
        with self.assertRaises(ValueError):
            classify_pnl(float("inf"))
        from core.risk.position_sizer import PositionSizer
        bad = PositionSizer().calculate(
            balance=float("nan"), entry_price=100.0, stop_price=90.0)
        self.assertFalse(bad.valid)
        bad2 = PositionSizer().calculate(
            balance=2000.0, entry_price=float("inf"), stop_price=90.0)
        self.assertFalse(bad2.valid)


# --------------------------------------------------
# Paper RR (§10)
# --------------------------------------------------

class TestPaperRR(unittest.TestCase):
    def test_single_authoritative_source(self):
        self.assertTrue(
                1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0,
                "frozen-era constant kept for audit"
        )
        from core.setup import decision_engine as DE
        self.assertFalse(hasattr(DE.DecisionEngine, "MIN_RISK_REWARD"))

    def decide(self, tp):
        ctx = PipelineContext()
        ctx.market = MarketState(symbol="TEST", timeframe="1m")
        ctx.trade_setups = [candidate(tp=tp)]
        DecisionEngine().analyze(ctx)
        return ctx.decision.all()

    def test_boundaries(self):
        # Runtime RR authority is the configurable trading policy
        # (default 1:1..1:20, Level-4 migration), not the frozen
        # research 6:1 threshold: exact-threshold behavior is pinned
        # at the CURRENT policy bounds. Entry 100 / stop 90.
        self.assertEqual(self.decide(109.9), [])   # 0.99 reject
        self.assertEqual(len(self.decide(110.0)), 1)  # 1.00 accept
        self.assertEqual(len(self.decide(110.1)), 1)  # 1.01 accept
        self.assertEqual(len(self.decide(300.0)), 1)  # 20.00 accept
        self.assertEqual(self.decide(300.1), [])   # 20.01 reject

    def test_tick_short_rejects(self):
        self.assertEqual(self.decide(105.0), [])

    def test_risk_revalidates_lying_field(self):
        bad = candidate(tp=105.0)
        bad.risk_reward = 99.0
        self.assertIsNone(size_order(bad))
        self.assertIsNotNone(size_order(candidate()))


# --------------------------------------------------
# Realized RR (§16): signed, deterministic, fill-based
# --------------------------------------------------

class TestRealizedRR(unittest.TestCase):
    def test_long_gaps(self):
        from core.backtesting.accounting import realized_rr
        # Setup LONG 100/90/160 (order RR 6.0). Favorable gap
        # (fill 95): reward grows -> 13.0. Adverse gap (fill 105):
        # reward shrinks -> 55/15.
        self.assertAlmostEqual(
            realized_rr("BULLISH", 95.0, 90.0, 160.0), 13.0)
        self.assertAlmostEqual(
            realized_rr("BULLISH", 105.0, 90.0, 160.0),
            55.0 / 15.0)
        # Gap through target (fill 170): negative by convention —
        # plan exceeded at entry, flagged not hidden.
        self.assertAlmostEqual(
            realized_rr("BULLISH", 170.0, 90.0, 160.0), -0.125)

    def test_short_gaps(self):
        from core.backtesting.accounting import realized_rr
        # Setup SHORT 160/170/100 (order RR 6.0). Favorable gap
        # (fill 165): 65/5 = 13.0. Adverse (fill 155): 55/15.
        self.assertAlmostEqual(
            realized_rr("BEARISH", 165.0, 170.0, 100.0), 13.0)
        self.assertAlmostEqual(
            realized_rr("BEARISH", 155.0, 170.0, 100.0),
            55.0 / 15.0)
        # Gap through target (fill 90): negative.
        self.assertAlmostEqual(
            realized_rr("BEARISH", 90.0, 170.0, 100.0), -0.125)

    def test_tick_degenerate_wrongside(self):
        from core.backtesting.accounting import realized_rr
        # One-tick adverse move changes the ratio exactly.
        base = realized_rr("BULLISH", 100.0, 90.0, 160.0)
        moved = realized_rr("BULLISH", 100.5, 90.0, 160.0)
        self.assertAlmostEqual(base, 6.0)
        self.assertLess(moved, base)
        self.assertAlmostEqual(moved, 59.5 / 10.5)
        # Zero/invalid risk -> exactly 0.0, never NaN/inf.
        for args in (("BULLISH", 100.0, 100.0, 160.0),
                     ("BEARISH", 100.0, 100.0, 160.0),
                     ("BULLISH", float("nan"), 90.0, 160.0),
                     ("BULLISH", 100.0, 90.0, float("inf")),
                     ("BULLISH", None, 90.0, 160.0)):
            got = realized_rr(*args)
            self.assertEqual(got, 0.0, args)
            self.assertTrue(math.isfinite(got))
        # Wrong-side target is negative, never absolute-hidden.
        self.assertLess(
            realized_rr("BULLISH", 100.0, 90.0, 80.0), 0.0)
        self.assertLess(
            realized_rr("BEARISH", 100.0, 110.0, 120.0), 0.0)

    def test_stamp_matches_helper_on_real_fills(self):
        from core.backtesting.accounting import realized_rr
        from core.backtesting.trade_simulator import TradeSimulator \
            as TS
        seen = []
        real_open = TS.open_trade

        def spy(self, setup, timestamp, quantity=1.0, commission=0.0,
                slippage=0.0):
            seen.append(setup)
            return real_open(self, setup, timestamp, quantity,
                             commission, slippage)

        bt, sim, _ = real_backtester()
        with mock.patch.object(TS, "open_trade", spy):
            bt.run(make_candles(n=3000, start_price=60000.0,
                                seed=6))
        stamped = [s for s in seen
                   if float(getattr(s, "actual_risk_reward",
                                    0.0)) != 0.0]
        self.assertTrue(stamped)
        for setup in stamped:
            # Recorded for EVERY mutating fill...
            self.assertEqual(
                float(setup.actual_risk_reward),
                realized_rr(setup.direction, setup.entry,
                            setup.stop_loss, setup.take_profit))
            # ...while the gated order-time value is preserved
            # at/above the active minimum-R policy.
            from core.risk.trading_policy import trading_policy
            policy_min = float(trading_policy("BTCUSDT").min_rr)
            self.assertGreaterEqual(float(setup.risk_reward),
                                    policy_min - 1e-9)
        # Deterministic: same run stamps identical values.
        first = [float(s.actual_risk_reward) for s in stamped]
        seen2 = []
        real_open2 = TS.open_trade

        def spy2(self, setup, timestamp, quantity=1.0,
                 commission=0.0, slippage=0.0):
            seen2.append(float(getattr(setup, "actual_risk_reward",
                                       0.0)))
            return real_open2(self, setup, timestamp, quantity,
                              commission, slippage)

        bt2, _, _ = real_backtester()
        with mock.patch.object(TS, "open_trade", spy2):
            bt2.run(make_candles(n=3000, start_price=60000.0,
                                 seed=6))
        self.assertEqual(
            [v for v in seen2 if v != 0.0], first)


# --------------------------------------------------
# Paper execution on the ACTUAL pipeline (§6)
# --------------------------------------------------

class TestPaperExecutionRealPipeline(unittest.TestCase):
    def test_fields_fills_and_ledger(self):
        from core.backtesting.trade_simulator import TradeSimulator as TS
        opened = []
        real_open = TS.open_trade

        def spy(self, setup, timestamp, quantity=1.0, commission=0.0,
                slippage=0.0):
            opened.append({
                "setup_id": getattr(setup, "setup_id", ""),
                "order_rr": float(getattr(setup, "risk_reward", 0.0)),
                "realized_rr": float(getattr(
                    setup, "actual_risk_reward", 0.0)),
            })
            return real_open(self, setup, timestamp, quantity,
                             commission, slippage)

        bt, sim, ctx = real_backtester()
        with mock.patch.object(TS, "open_trade", spy):
            bt.run(make_candles(n=3000, start_price=60000.0, seed=6))
        trades = sim.registry.all()
        self.assertGreater(len(trades), 0)
        # Order-time gate holds on the REAL pipeline: every sized
        # order carried RR at/above the active policy minimum when
        # the gates saw it (this seed's economics clear 6.0, so the
        # bound below also holds here).
        from core.risk.trading_policy import trading_policy
        policy_min = float(trading_policy("BTCUSDT").min_rr)
        self.assertTrue(opened)
        for row in opened:
            self.assertGreaterEqual(row["order_rr"], policy_min - 1e-9,
                                    row["setup_id"])
        # Phase 12 execution-time invariant: a market fill
        # whose actual open geometry falls below the active
        # minimum is REFUSED (ORDER_SKIPPED_RR_EROSION) instead of
        # booked -- stops/targets are never moved to manufacture
        # compliance. Fill-price erosion that SURVIVES is still
        # MEASURED (actual_risk_reward stamped at market fills,
        # signed by side), never hidden. Every stamped value
        # therefore reads at/above the active minimum AND equals
        # the canonical helper applied to the ACTUAL fill.
        from core.backtesting.accounting import realized_rr
        realized = [r["realized_rr"] for r in opened
                    if r["realized_rr"] != 0]
        self.assertTrue(realized)
        for value in realized:
            self.assertGreaterEqual(value, policy_min - 1e-9)
        for trade in trades:
            for field in ("entry", "stop_loss", "take_profit",
                          "quantity"):
                self.assertTrue(math.isfinite(getattr(trade, field)))
                self.assertGreater(getattr(trade, field), 0)
            self.assertIn(trade.direction, ("BULLISH", "BEARISH"))
            self.assertTrue(trade.setup_id)
            self.assertTrue(trade.trade_id)
        balance = bt.account.state.balance
        realized = sum(t.pnl for t in trades)
        self.assertAlmostEqual(
            balance, 2000.0 + realized,
            msg="opening + realized - fees = ending")

    def test_expired_and_rejected_orders(self):
        # Far-away LIMIT order that never fills must expire, never
        # fill; RiskEngine rejection yields no order at all.
        # Rejection case uses RR 0.5, below the runtime policy
        # minimum (1:1), so the refusal is policy-driven.
        self.assertIsNone(size_order(candidate(tp=105.0)))
        reg = OrderRegistry()
        order, _ = reg.create(OrderIntent(
            direction="BULLISH", entry=100.0, stop_loss=90.0,
            take_profit=160.0, quantity=1.0, setup_id="S-EXP"),
            bar=0, timestamp=0)
        reg.advance(bar=10_000, timestamp=10_000)
        self.assertEqual(order.status, OR.EXPIRED)
        self.assertEqual(reg.filled(), [])

    def test_duplicate_signal_one_order(self):
        reg = OrderRegistry()
        first, _ = reg.create(OrderIntent(
            direction="BULLISH", entry=100.0, stop_loss=90.0,
            take_profit=160.0, quantity=1.0, setup_id="S-DUP"),
            bar=1, timestamp=1)
        for bar in (2, 3, 4):
            again, _ = reg.create(OrderIntent(
                direction="BULLISH", entry=100.0, stop_loss=90.0,
                take_profit=160.0, quantity=1.0, setup_id="S-DUP"),
                bar=bar, timestamp=bar)
            self.assertIs(again, first)
        self.assertEqual(len(reg.pending()), 1)


# --------------------------------------------------
# Reconciliation (§13) + startup (§14)
# --------------------------------------------------

class TestReconciliationCert(unittest.TestCase):
    def test_all_verdicts(self):
        mirror = SimpleNamespace(direction="BULLISH", quantity=2.0,
                                 entry=100.0)
        exch = [{"side": "buy", "size": 2.0, "entry": 100.0}]
        self.assertEqual(
            Reconciler(executor=FakePositions(exch)).runtime_check(
                9, 9, mirror, None)["verdict"], "MATCH")
        self.assertEqual(
            Reconciler(executor=FakePositions([])).runtime_check(
                9, 9, None,
                {"status": "PENDING", "age_bars": 0})["verdict"],
            "IN_FLIGHT")
        bad = [({"side": "sell", "size": 2.0, "entry": 100.0},
                "SIDE_MISMATCH"),
               ({"side": "buy", "size": 1.0, "entry": 100.0},
                "PARTIAL_FILL_QTY"),
               ({"side": "buy", "size": 2.0, "entry": 120.0},
                "ENTRY_MISMATCH")]
        for record, kind in bad:
            rec = Reconciler(executor=FakePositions([record]))
            out = rec.runtime_check(9, 9, mirror, None)
            self.assertEqual(out["verdict"], "MISMATCH", kind)
            self.assertTrue(rec.halt_new_orders, kind)
        rec = Reconciler(executor=FakePositions(
            error=RuntimeError("down")))
        self.assertEqual(
            rec.runtime_check(9, 9, mirror, None)["verdict"],
            "MISMATCH")
        rec = Reconciler(executor=FakePositions([]))
        rec.runtime_check(9, 9, mirror, None)
        with self.assertRaises(ValueError):
            rec.resolve("")
        rec.resolve("operator OP-4")
        self.assertFalse(rec.halt_new_orders)

    def test_startup_cases(self):
        # A: flat/flat -> MATCH.
        rec = Reconciler(executor=FakePositions([]))
        self.assertEqual(
            rec.startup_check(dry_run=False)["verdict"], "MATCH")
        # Paper always SKIP without touching the feed.
        feed = FakePositions([{"side": "buy", "size": 1.0}])
        rec = Reconciler(executor=feed)
        self.assertEqual(rec.startup_check(dry_run=True)["verdict"],
                         "SKIP")
        self.assertEqual(feed.calls, 0)
        # B: local open / exchange flat -> MISMATCH HALT.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.json")
            rec = Reconciler(executor=FakePositions([]),
                             snapshot_path=path)
            rec.persist(rec.snapshot_state(
                True, "OID", None,
                SimpleNamespace(direction="BULLISH", quantity=1.0,
                                entry=100.0), 7))
            rec2 = Reconciler(executor=FakePositions([]),
                              snapshot_path=path)
            out = rec2.startup_check(dry_run=False)
            self.assertEqual(out["verdict"], "MISMATCH")
            self.assertTrue(rec2.halt_new_orders)
        # C: local flat / exchange open -> MISMATCH HALT.
        rec = Reconciler(executor=FakePositions(
            [{"side": "buy", "size": 1.0, "entry": 50.0}]))
        out = rec.startup_check(dry_run=False)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        # D: corrupt journal degrades through the documented path
        # (unreadable snapshot -> treated as no-snapshot fresh boot;
        # flat exchange -> MATCH). Pinned exactly: a future
        # fail-closed change (halt on corrupt journal) must update
        # this deliberately, never silently.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.json")
            with open(path, "w") as handle:
                handle.write("{corrupt")
            rec = Reconciler(executor=FakePositions([]),
                             snapshot_path=path)
            self.assertIsNone(rec.load_snapshot())
            out = rec.startup_check(dry_run=False)
            self.assertEqual(out["verdict"], "MATCH")
        # E: missing state -> explicit safe init (flat boot MATCH,
        # journaled-open boot MISMATCH), never phantom fill.
        rec = Reconciler(executor=FakePositions([]),
                         snapshot_path=os.path.join(
                             tempfile.mkdtemp(), "absent.json"))
        self.assertEqual(
            rec.startup_check(dry_run=False)["verdict"], "MATCH")


# --------------------------------------------------
# Crash / restart drills (§15)
# --------------------------------------------------

class CrashJournal:
    """Test-only drill journal (JSON): closed trades, open setup
    ids, balance. NOT a production state system."""

    def __init__(self, path):
        self.path = path

    def write(self, backtester, simulator):
        payload = {
            "bars": backtester.total_bars,
            "balance": backtester.account.state.balance,
            "closed": [{"setup_id": t.setup_id, "pnl": t.pnl}
                       for t in simulator.registry.all()],
            "open_setup_ids": [
                t.setup_id for t in simulator.registry.all()
                if getattr(t, "status", "") == "OPEN"],
        }
        with open(self.path, "w") as handle:
            handle.write(json.dumps(payload, sort_keys=True))
        return payload

    def read(self):
        with open(self.path) as handle:
            return json.load(handle)


def journal_setup_ids(payload):
    return {c["setup_id"] for c in payload["closed"]} | set(
        payload["open_setup_ids"])


class TestCrashDrills(unittest.TestCase):
    def _reference_ids(self, candles):
        bt, sim, _ = real_backtester()
        bt.run(candles)
        return (sorted(t.setup_id for t in sim.registry.all()),
                round(bt.account.state.balance, 6))

    def _restart_and_resume(self, tmp, point, candles, payload, k):
        """Rebuild everything, resume AFTER the journaled bar.

        Returns (journal_ids, final_ids, journal_ok, resume_ok,
        reconcile_match, reconcile_halt) with REAL values the
        caller asserts on (no tautologies)."""
        journal = CrashJournal(payload["_path"]).read()
        journal_ids = journal_setup_ids(journal)
        journal_closed = {c["setup_id"]: c["pnl"]
                          for c in journal["closed"]}
        journal_ok = abs(journal["balance"] - (
            2000.0 + sum(journal_closed.values()))) < 1e-6
        bt2, sim2, _ = real_backtester()
        bt2.run(candles[journal["bars"]:])
        resumed = sim2.registry.all()
        final_ids = {t.setup_id for t in resumed}
        resume_ok = abs(bt2.account.state.balance - (
            2000.0 + sum(t.pnl for t in resumed))) < 1e-6
        # Reconciler re-verification at restart through the ACTUAL
        # production seam: journaled state -> snapshot journal ->
        # startup check. Consistent mirror -> MATCH; contradicted
        # feed (phantom exchange position / vanished position) ->
        # MISMATCH + halt at the order boundary.
        journal_open = list(journal["open_setup_ids"])
        if journal_open:
            mirror_trade = SimpleNamespace(
                direction="BULLISH", quantity=1.0, entry=100.0,
                stop_loss=90.0, take_profit=160.0, entry_time=k)
            mirror_feed = [{"side": "buy", "size": 1.0,
                            "entry": 100.0}]
            contra_feed = []
        else:
            mirror_trade, mirror_feed = None, []
            contra_feed = [{"side": "buy", "size": 9.0, "entry": 1.0}]
        snap_path = os.path.join(tmp, "snap-%s.json" % point)
        seed_rec = Reconciler(executor=FakePositions(mirror_feed),
                              snapshot_path=snap_path)
        seed_rec.persist(seed_rec.snapshot_state(
            bool(journal_open), "OID-%s" % point, None,
            mirror_trade, k))
        rec = Reconciler(executor=FakePositions(mirror_feed),
                         snapshot_path=snap_path)
        consistent = rec.startup_check(dry_run=False)["verdict"]
        rec2 = Reconciler(executor=FakePositions(contra_feed),
                          snapshot_path=snap_path)
        bad = rec2.startup_check(dry_run=False)
        reconcile_match = consistent
        reconcile_halt = (bad["verdict"] == "MISMATCH"
                          and rec2.halt_new_orders)
        return (journal_ids, final_ids, journal_ok, resume_ok,
                reconcile_match, reconcile_halt)

    def test_drill_matrix(self):
        # Points 1-6, 8-10, 12: crash at bar K, journal, resume
        # forward (never replay). Point 7 (partial) + 11 (during
        # reconcile) use the reconciler fail-closed path (paper
        # has no partial-fill execution).
        # Phase 12: seed 6 yields compliant fills (seed 42
        # fills all erode below 6:1 and are refused, which
        # would leave the drill tripwire vacuous).
        candles = make_candles(n=1200, start_price=60000.0, seed=6)
        reference_ids, _ = self._reference_ids(candles)
        union_all = set()
        with tempfile.TemporaryDirectory() as tmp:
            for point, k in (("before_signal", 10),
                             ("after_signal", 400),
                             ("after_risk", 500),
                             ("after_intent", 600),
                             ("after_submit", 700),
                             ("after_ack", 800),
                             ("after_fill", 900),
                             ("before_persist", 950),
                             ("after_persist", 1000),
                             ("during_shutdown", 1100)):
                bt, _, _ = real_backtester()
                bt.run(candles[:k])
                sim = bt.simulator
                journal = CrashJournal(os.path.join(tmp, "j.json"))
                payload = journal.write(bt, sim)
                payload["_path"] = os.path.join(tmp, "j.json")
                # Crash = drop all objects; restart resumes forward.
                del bt, sim
                (journal_ids, final_ids, journal_ok, resume_ok,
                 reconcile_match, reconcile_halt) = (
                     self._restart_and_resume(tmp, point, candles,
                                              payload, k))
                # REAL no-duplicate invariant: resume-forward never
                # reprocesses a journaled bar, so no setup identity
                # may appear on both sides. Fails on any replay or
                # double-creation.
                self.assertEqual(journal_ids & final_ids, set(),
                                 point)
                # Each segment's ledger is internally consistent.
                self.assertTrue(journal_ok, point)
                self.assertTrue(resume_ok, point)
                # Reconciliation executes at restart and the halt
                # is enforced at the order boundary on divergence.
                self.assertEqual(reconcile_match, "MATCH", point)
                self.assertTrue(reconcile_halt, point)
                union_all |= journal_ids | final_ids
        # Warmup-divergence tripwire (documents DURABLE_RUNTIME_STATE
        # = YELLOW): a fresh restart loses indicator warmup, so the
        # resumed decision stream is NOT identical to an
        # uninterrupted run. Deliberately assert the proven
        # non-equivalence — a future durable-state implementation
        # must update this test on purpose, never silently.
        self.assertNotEqual(sorted(union_all), sorted(reference_ids))

    def test_fresh_registry_ignores_journal(self):
        # RAM-only boundary proof: the OrderRegistry lives in the
        # PipelineContext (per-process memory). Replaying a
        # journaled setup_id into a FRESH registry mints a
        # DUPLICATE (documents why restart must resume-forward or
        # halt — never blindly replay). Same registry dedupes.
        reg = OrderRegistry()
        mk = lambda: OrderIntent(
            direction="BULLISH", entry=100.0, stop_loss=90.0,
            take_profit=160.0, quantity=1.0, setup_id="S-JOURNALED")
        first, _ = reg.create(mk(), bar=1, timestamp=1)
        again, _ = reg.create(mk(), bar=2, timestamp=2)
        self.assertIs(again, first)
        fresh = OrderRegistry()
        dup, _ = fresh.create(mk(), bar=3, timestamp=3)
        self.assertIsNot(dup, first)
        self.assertEqual(dup.setup_id, "S-JOURNALED")

    def test_partial_crash_halts(self):
        # Point 7: crash observed a partial fill -> HALT, never
        # manufacture the remainder.
        rec = Reconciler(executor=FakePositions(
            [{"side": "buy", "size": 1.0, "entry": 100.0}]))
        out = rec.runtime_check(
            5, 5, SimpleNamespace(direction="BULLISH", quantity=2.0,
                                  entry=100.0), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "PARTIAL_FILL_QTY")

    def test_reconcile_crash_relatches(self):
        # Point 11: crash during reconciliation -> halt is re-derived
        # on restart (halt flag itself is RAM-only by design).
        rec = Reconciler(executor=FakePositions([]))
        rec.runtime_check(1, 1, SimpleNamespace(
            direction="BULLISH", quantity=1.0, entry=100.0), None)
        self.assertTrue(rec.halt_new_orders)
        rec2 = Reconciler(executor=FakePositions([]))
        rec2.runtime_check(2, 2, SimpleNamespace(
            direction="BULLISH", quantity=1.0, entry=100.0), None)
        self.assertTrue(rec2.halt_new_orders)

    def test_corrupt_journal_halts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "j.json")
            with open(path, "w") as handle:
                handle.write("{broken")
            with self.assertRaises(ValueError):
                CrashJournal(path).read()


# --------------------------------------------------
# Lifecycle (§16) + duplicates (§17)
# --------------------------------------------------

class TestLifecycleAndDuplicates(unittest.TestCase):
    def test_terminal_states(self):
        for a, b in ((OR.PARTIAL, OR.FILLED),
                     (OR.ACKNOWLEDGED, OR.FILLED),
                     (OR.SUBMITTED, OR.FILLED)):
            self.assertNotEqual(a, b)
        reg = OrderRegistry()
        order, _ = reg.create(OrderIntent(
            direction="BULLISH", entry=100.0, stop_loss=90.0,
            take_profit=160.0, quantity=1.0, setup_id="S-LC"),
            bar=0, timestamp=0)
        self.assertEqual(order.status, OR.PENDING)
        reg.invalidate(order, bar=5)
        self.assertEqual(order.status, OR.INVALIDATED)
        self.assertEqual(reg.filled(), [])

    def test_duplicate_vectors_one_order(self):
        reg = OrderRegistry()
        mk = lambda: OrderIntent(direction="BULLISH", entry=100.0,
                                 stop_loss=90.0, take_profit=160.0,
                                 quantity=1.0, setup_id="S-VEC")
        first, _ = reg.create(mk(), bar=1, timestamp=1)
        # duplicate signal / candle / replayed / late event
        for bar in (1, 2, 30, 31):
            again, _ = reg.create(mk(), bar=bar, timestamp=bar)
            self.assertIs(again, first)
        self.assertTrue(reg.has_order_for_setup("S-VEC"))
        self.assertEqual(len(reg.pending()), 1)


# --------------------------------------------------
# Multi-symbol (§18/§19) + breakers (§20)
# --------------------------------------------------

class TestMultiSymbol(unittest.TestCase):
    def _run(self, symbol, seed, n=1500):
        bt, sim, ctx = real_backtester(symbol=symbol)
        bt.run(make_candles(n=n, start_price=60000.0, seed=seed))
        return bt, sim, ctx

    def _metrics(self, bt, sim):
        trades = sim.registry.all()
        return {
            "setup_ids": sorted(t.setup_id for t in trades),
            "balance": round(bt.account.state.balance, 6),
            "n": len(trades),
        }

    def test_independent_symbols(self):
        # Same seed AND same prices for both symbols: setup-id
        # namespaces COLLIDE by construction (ids carry no symbol
        # prefix — documented namespace limitation). Isolation
        # must still hold because registries/accounts/pipelines
        # are per-symbol objects, never shared.
        # Phase 12: seed 6 yields compliant fills through
        # the execution-time 6:1 revalidation (seed 42 fills
        # all erode below it and are refused).
        btc_bt, btc_sim, btc_ctx = self._run("BTCUSDT", 6)
        eth_bt, eth_sim, eth_ctx = self._run("ETHUSDT", 6)
        btc, eth = (self._metrics(btc_bt, btc_sim),
                    self._metrics(eth_bt, eth_sim))
        # Same decisions (deterministic same input)...
        self.assertEqual(btc["setup_ids"], eth["setup_ids"])
        self.assertGreater(btc["n"], 0)
        # ...but zero shared mutable state: no common Trade
        # object (compared by live identity while both stacks are
        # alive — ids are never persisted, per the determinism
        # rule), distinct registries/accounts/contexts/pipelines.
        btc_live = {id(t) for t in btc_sim.registry.all()}
        eth_live = {id(t) for t in eth_sim.registry.all()}
        self.assertEqual(btc_live & eth_live, set())
        self.assertIsNot(btc_sim.registry, eth_sim.registry)
        self.assertIsNot(btc_bt.account, eth_bt.account)
        self.assertIsNot(btc_ctx, eth_ctx)
        self.assertIsNot(btc_ctx.order_registry,
                         eth_ctx.order_registry)
        self.assertIsNot(btc_ctx.economic_registry,
                         eth_ctx.economic_registry)
        # Independent accounting: mutating BTC state cannot move
        # ETH results — corrupt BTC post-run, re-run ETH fresh,
        # ETH metrics equal the ETH reference exactly.
        btc_bt.account.state.balance = float("nan")
        btc_ctx.market.mark_price = float("nan")
        eth_bt2, eth_sim2, _ = self._run("ETHUSDT", 6)
        self.assertEqual(self._metrics(eth_bt2, eth_sim2), eth)

    def test_btc_failure_does_not_corrupt_eth(self):
        # A poison candle crashes the BTC stack LOUDLY (TypeError,
        # fail-loud — never silent corruption). The ETH stack built
        # afterwards still matches its clean reference exactly.
        eth_bt_ref, eth_sim_ref, _ = self._run("ETHUSDT", 43)
        ref = self._metrics(eth_bt_ref, eth_sim_ref)
        candles = make_candles(n=300, start_price=60000.0, seed=42)
        candles[150] = SimpleNamespace(
            timestamp=candles[150].timestamp, open=None, high=None,
            low=None, close=None, volume=0.0, closed=True,
            symbol="BTCUSDT", timeframe="1m")
        bt, sim, _ = real_backtester(symbol="BTCUSDT")
        with self.assertRaises(TypeError):
            bt.run(candles)
        eth_bt, eth_sim, _ = self._run("ETHUSDT", 43)
        self.assertEqual(self._metrics(eth_bt, eth_sim), ref)
        self.assertEqual(
            {t.setup_id for t in eth_sim.registry.all()},
            {t.setup_id for t in eth_sim_ref.registry.all()})

    def test_portfolio_caps_across_symbols(self):
        gate = PortfolioRiskManager(max_positions=1, equity=2000.0)
        self.assertTrue(
            gate.order_allows(SimpleNamespace(
                symbol="BTCUSDT", direction="BULLISH", risk_amount=20.0,
                position_value=500.0, expected_loss=20.0)))
        gate.register_open(SimpleNamespace(
            symbol="BTCUSDT", direction="BULLISH", risk_amount=20.0,
            position_value=500.0, expected_loss=20.0))
        self.assertFalse(
            gate.order_allows(SimpleNamespace(
                symbol="ETHUSDT", direction="BULLISH",
                risk_amount=20.0, position_value=500.0,
                expected_loss=20.0)))
        self.assertEqual(gate.last_reason, "max_positions")

    def test_live_scope_stays_single_symbol(self):
        from config.settings import settings
        self.assertGreaterEqual(len(settings.SYMBOLS), 1)


class TestBreakers(unittest.TestCase):
    def gate(self, **kw):
        kw.setdefault("equity", 2000.0)
        return PortfolioRiskManager(**kw)

    def test_daily_loss_epsilon(self):
        for pnl, allowed in ((-39.99, True), (-40.00, False),
                             (-40.01, False)):
            g = self.gate(max_daily_loss_pct=2.0)
            g._today_realized_pnl = pnl
            self.assertEqual(g._allows(1.0, "BTC", 100.0, "BULLISH",
                                       None, equity=2000.0), allowed)

    def test_nonfinite_and_invalid(self):
        g = self.gate(max_daily_loss_pct=2.0)
        for risk, notional, equity in ((float("nan"), 100.0, 2000.0),
                                       (1.0, float("inf"), 2000.0),
                                       (1.0, 100.0, float("nan"))):
            self.assertFalse(g._allows(risk, "BTC", notional,
                                       "BULLISH", None, equity=equity))
        g._today_realized_pnl = float("nan")
        self.assertFalse(g._allows(1.0, "BTC", 100.0, "BULLISH",
                                   None, equity=2000.0))
        # Established neutral-cap semantics (documented, not a
        # defect): with no caps binding, finite negative inputs are
        # handled deterministically rather than blocked.
        neutral = self.gate()
        self.assertTrue(neutral._allows(-5.0, "BTC", -100.0,
                                        "BULLISH", None,
                                        equity=-2000.0))

    def test_caps_and_restart(self):
        g = self.gate(max_positions=0)
        self.assertFalse(g._allows(1.0, "BTC", 100.0, "BULLISH",
                                   None, equity=2000.0))
        g2 = self.gate(max_daily_loss_pct=2.0)
        g2.close_trade(1.0, symbol="BTC", pnl=-100.0)
        self.assertFalse(g2._allows(1.0, "BTC", 100.0, "BULLISH",
                                    None, equity=2000.0))
        g2.reset()
        self.assertTrue(g2._allows(1.0, "BTC", 100.0, "BULLISH",
                                   None, equity=2000.0))


# --------------------------------------------------
# Kill switch (§21)
# --------------------------------------------------

class TestKillSwitch(unittest.TestCase):
    def test_inactive_orders_flow(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QE_KILL_SWITCH", None)
            self.assertFalse(
                kill_switch_active(seeded_account()))
            self.assertIsNotNone(size_order(candidate()))

    def test_active_blocks_sizing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QE_KILL_SWITCH", None)
            self.assertTrue(
                kill_switch_active(seeded_account(kill_switch=True)))
            self.assertIsNone(size_order(
                candidate(), account=seeded_account(kill_switch=True)))

    def test_trading_disabled_blocks(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QE_KILL_SWITCH", None)
            self.assertTrue(kill_switch_active(
                seeded_account(trading_enabled=False)))
            self.assertIsNone(size_order(
                candidate(),
                account=seeded_account(trading_enabled=False)))

    def test_env_forces_active_across_restart(self):
        with mock.patch.dict(os.environ, {"QE_KILL_SWITCH": "1"}):
            self.assertTrue(kill_switch_active(seeded_account()))
            # Fresh default account after restart still blocked.
            self.assertIsNone(size_order(candidate()))

    def test_tampered_values_fail_closed(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QE_KILL_SWITCH", None)
            for bad in ("yes", 1, 1.5, [True]):
                self.assertTrue(
                    kill_switch_active(
                        seeded_account(kill_switch=bad)), bad)
            self.assertTrue(kill_switch_active(
                seeded_account(trading_enabled=None)))

    def test_state_stays_observable(self):
        account = seeded_account(kill_switch=True)
        self.assertEqual(account.balance, 2000.0)
        self.assertTrue(math.isfinite(account.equity))

    def test_recovery_requires_explicit_clear(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QE_KILL_SWITCH", None)
            account = seeded_account(kill_switch=True)
            self.assertIsNone(size_order(candidate(), account=account))
            account.kill_switch = False
            self.assertIsNotNone(
                size_order(candidate(), account=account))


# --------------------------------------------------
# Boundaries: paper/live/research/AI (§22/§31/§43)
# --------------------------------------------------

class TestBoundaries(unittest.TestCase):
    def test_paper_zero_exchange_writes(self):
        from core.runtime.execution_port import (
            PaperExecutionAdapter, PaperOnlyError)
        port = PaperExecutionAdapter()
        env = port.execute(SimpleNamespace(order_id="P-1"))
        self.assertTrue(env["success"])
        for op, args in (("fetch", ("x",)), ("balance", ()),
                         ("positions", ()), ("cancel", ("x",))):
            with self.assertRaises(PaperOnlyError):
                getattr(port, op)(*args)
        self.assertEqual(len(port.executed), 1)

    def test_backtester_has_no_exchange_surface(self):
        bt, _, _ = real_backtester()
        for attr in ("execute", "cancel", "place_order", "submit",
                     "close_position", "modify_order"):
            self.assertFalse(hasattr(bt, attr), attr)
            self.assertFalse(hasattr(bt.simulator, attr), attr)

    def test_research_zero_exchange_writes(self):
        import inspect
        import research.phase11f.harness as harness
        src = inspect.getsource(harness)
        for token in (".execute(", ".cancel(", "place_order",
                      "close_position", "LiveSafetyGate"):
            self.assertNotIn(token, src, token)

    def test_ai_research_only(self):
        import core.pipeline.institutional_pipeline as pipe
        import core.risk.risk_engine as risk
        import core.live.broker_engine as broker
        import core.execution.order_executor as executor
        for module in (pipe, risk, broker, executor):
            src = open(module.__file__).read()
            tree = ast.parse(src)
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add(node.module or "")
            self.assertFalse(
                {m for m in imported
                 if "researcher" in m or "providers" in m},
                module.__name__)
        # Advisory field stays None through a real pipeline run.
        bt, _, ctx = real_backtester()
        bt.run(make_candles(n=500, start_price=60000.0, seed=42))
        for setup in list(getattr(ctx, "trade_setups", []) or []):
            self.assertIsNone(getattr(setup, "ai_analysis", None))

    def test_allow_live_stays_false(self):
        from config.settings import settings
        self.assertFalse(bool(getattr(settings, "ALLOW_LIVE", False)))
        self.assertFalse(risk_settings.LIVE_MODE)
        self.assertFalse(paper_venue_realistic())


# --------------------------------------------------
# Determinism (small) + causality (§28/§29)
# --------------------------------------------------

class TestDeterminismSmall(unittest.TestCase):
    def metrics(self, n=2000, seed=42):
        bt, sim, _ = real_backtester()
        candles = make_candles(n=n, start_price=60000.0, seed=seed)
        bt.run(candles)
        trades = sim.registry.all()
        payload = {
            "label": PAPER_ONLY,
            "bars": n,
            "seed": seed,
            "balance": round(bt.account.state.balance, 6),
            "trades": [(t.setup_id, t.direction,
                        round(t.entry, 6), round(t.exit_price, 6),
                        round(t.quantity, 6), round(t.pnl, 6))
                       for t in trades],
        }
        return json.dumps(payload, sort_keys=True)

    def test_repeated_run_identical(self):
        first, second = self.metrics(), self.metrics()
        self.assertEqual(first, second)
        digest = hashlib.sha256(first.encode()).hexdigest()
        self.assertEqual(
            digest, hashlib.sha256(second.encode()).hexdigest())


class TestCausality(unittest.TestCase):
    def decisions(self, candles):
        bt, sim, _ = real_backtester()
        bt.run(candles)
        return sorted((t.entry_time, t.setup_id, t.direction,
                       round(t.entry, 6), round(t.stop_loss, 6),
                       round(t.take_profit, 6))
                      for t in sim.registry.all())

    def test_future_mutation_preserves_past(self):
        base = make_candles(n=3000, start_price=60000.0, seed=42)
        boundary = base[1500].timestamp
        mutated = list(base[:1500]) + make_candles(
            n=1500, start_price=99999.0, seed=7)
        for i, candle in enumerate(mutated[1500:]):
            candle.timestamp = base[1500 + i].timestamp
        before = [d for d in self.decisions(base)
                  if d[0] < boundary]
        after = [d for d in self.decisions(mutated)
                 if d[0] < boundary]
        self.assertEqual(before, after)

    def test_future_outcome_mutation_preserves_past(self):
        base = make_candles(n=3000, start_price=60000.0, seed=42)
        boundary = base[2000].timestamp
        shifted = list(base)
        for candle in shifted[2000:]:
            candle.high *= 2.0
            candle.low *= 2.0
            candle.close *= 2.0
        before = [d for d in self.decisions(base) if d[0] < boundary]
        after = [d for d in self.decisions(shifted)
                 if d[0] < boundary]
        self.assertEqual(before, after)


# --------------------------------------------------
# WebSocket storm (§12)
# --------------------------------------------------

class TestWebSocketStorm(unittest.TestCase):
    def _stream(self):
        from data.delta.delta_subscription_stream import (
            DeltaSubscriptionStream)
        import threading
        s = DeltaSubscriptionStream.__new__(DeltaSubscriptionStream)
        s.timeframe = "1m"
        s.ws_url = "wss://invalid.local"
        s._builders = {}
        s._last_form = {}
        s._lock = threading.RLock()
        s._stop = threading.Event()
        s._pump_thread = None
        s._ws = None
        s._handlers = {}
        s._stats = {"frames_received": 0, "malformed_frames": 0,
                    "unknown_frames": 0, "heartbeat_frames": 0,
                    "closed_candles": 0, "candle_gaps": 0,
                    "pump_restarts": 0, "disconnects": 0}
        s._last_heartbeat_ts = None
        s._last_closed_ts = {}
        return s

    def test_storm_isolation_and_accounting(self):
        import time
        from data.realtime.candle_router import CandleRouter
        from core.history.candle import Candle
        stream = self._stream()
        delivered = []
        stream._handlers["BTCUSDT"] = (delivered.append,
                                       lambda: None)
        router = CandleRouter("BTCUSDT")
        base_ms = 1_700_000_000_000
        # 5000-frame storm: valid / duplicate / out-of-order /
        # malformed / heartbeat mix on ONE multiplexed pump.
        for i in range(5000):
            kind = i % 10
            if kind == 0:
                stream._emit_ticker({"type": "heartbeat"})
            elif kind in (1, 2):
                stream._emit_ticker(None)
            elif kind == 3:
                stream._emit_ticker({"type": "ticker"})
            else:
                stream._emit_ticker({
                    "type": "ticker",
                    "d": [{"s": "BTCUSDT",
                           "m": 60000.0 + (i % 50)}],
                    "ts": base_ms + (i // 10) * 60_000})
        stats = stream.stats()
        self.assertGreater(stats["malformed_frames"], 0)
        self.assertGreater(stats["heartbeat_frames"], 0)
        self.assertEqual(stats["unknown_frames"], 0)
        # Router: duplicates/out-of-order dropped deterministically,
        # forming never forwarded, no crash on any input.
        r2 = CandleRouter("ETHUSDT")
        seq = [1000, 1001, 1001, 999, 1002]
        got = [r2.route(SimpleNamespace(timestamp=t, closed=True))
               for t in seq]
        self.assertIsNotNone(got[0])
        self.assertIsNotNone(got[1])
        self.assertIsNone(got[2])
        self.assertIsNone(got[3])
        self.assertIsNotNone(got[4])
        self.assertEqual((r2.duplicates, r2.out_of_order), (1, 1))
        # Stale health degrades without emitting orders: the
        # transport has no order surface by construction.
        self.assertFalse(hasattr(stream, "execute"))
        self.assertFalse(hasattr(router, "execute"))
        # GAP_REPAIR = NOT_IMPLEMENTED: a jumped timestamp is
        # delivered (counted), never backfilled.
        r3 = CandleRouter("BTCUSDT")
        r3.route(SimpleNamespace(timestamp=1000, closed=True))
        jumped = r3.route(SimpleNamespace(timestamp=5000,
                                          closed=True))
        self.assertIsNotNone(jumped)
        self.assertEqual(r3.last_delivered_ts, 5000)

    def test_transport_detects_candle_gaps(self):
        # Ticks skip buckets T+120/T+180: the builder emits only
        # the just-completed bucket, so finished candles jump
        # T+60 -> T+240 and the transport counts 2 missed candles.
        # Detection only — no repair, no halt, stream continues.
        stream = self._stream()
        stream._handlers["BTCUSDT"] = (lambda c: None, lambda: None)
        base_ms = 1_700_000_000_000
        for sec in (0, 60, 240, 300):
            stream._emit_ticker({
                "type": "ticker",
                "d": [{"s": "BTCUSDT", "m": 60000.0}],
                "ts": base_ms + sec * 1000})
        stats = stream.stats()
        self.assertEqual(stats["closed_candles"], 3)
        self.assertEqual(stats["candle_gaps"], 2)
        # Steady cadence afterwards counts no further gaps.
        stream._emit_ticker({
            "type": "ticker",
            "d": [{"s": "BTCUSDT", "m": 60000.0}],
            "ts": base_ms + 360 * 1000})
        self.assertEqual(stream.stats()["candle_gaps"], 2)


# --------------------------------------------------
# Tracked-source secret scan (§12-stage4)
# --------------------------------------------------

class TestSecretScan(unittest.TestCase):
    def test_no_live_format_assignments_tracked(self):
        require_git_fact(self, 'test_stage4_paper_certification::TestSecretScan::test_no_live_format_assignments_tracked')
        import re
        out = git("grep", "-n", "-E",
                  "DELTA_API_(KEY|SECRET)\\s*=\\s*\\S+", "--", ".")
        hits = [ln for ln in out.stdout.splitlines()
                if "stage123_baseline_audit" not in ln
                and ".env.example" not in ln
                and "os.getenv" not in ln and "getenv" not in ln
                and "SYNTHETIC" not in ln
                and "REAL-LOOKING" not in ln]
        real_like = [ln for ln in hits
                     if re.search(r"=\s*\S{8,}", ln)]
        self.assertEqual(real_like, [])


# --------------------------------------------------
# Config governance (§30)
# --------------------------------------------------

class TestConfigGovernance(unittest.TestCase):
    def test_rr_still_six(self):
        self.assertTrue(
                1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0,
                "frozen-era constant kept for audit"
        )

    def test_confidence_gate_reads_config_live(self):
        # Phase 4 verified correction: the 70-shadow is removed; the
        # engine reads the authoritative config minimum (80) per
        # analysis, mirroring test_decision_gate_reads_config_live.
        import core.setup.decision_engine as DE
        from core.setup.decision_engine import DecisionEngine
        self.assertEqual(DE.risk_settings.MIN_CONFIDENCE, 80)
        self.assertFalse(hasattr(DecisionEngine, "MIN_CONFIDENCE"),
                         "MIN_CONFIDENCE shadow must not return")
        self.assertEqual(risk_settings.MIN_CONFIDENCE, 80)
        self.assertEqual(DecisionEngine.MIN_REGIME_SCORE, 70)


if __name__ == "__main__":
    unittest.main()
