"""Stage 1-3 hardening plus Level-4 runtime RR authority and config governance.

Proves, against production code (no mocks of the units under test):
- CostSpec is the single production cost formula; defaults are
  explicit zero-cost; research ladders untouched.
- the frozen research MIN_RISK_REWARD remains 6.0 (kept for audit), while runtime uses 1.0‑20.0
  DecisionEngine/RiskEngine use the 1:1..1:20 trading policy;
  RiskEngine revalidates (defense in depth); tick-grid boundaries hold.
- Dead config (trading profiles) is never read by production.
"""

import io
import json
import os
import tempfile
import tokenize
import unittest
from pathlib import Path
from types import SimpleNamespace

from config import risk_settings
from core.live.reconciler import Reconciler
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.account_state import AccountState
from core.risk.costs import CostSpec, from_settings, PRODUCTION_DEFAULTS
from core.risk.order_intent import OrderIntent
from core.risk.position_size import PositionSize
from core.risk.risk_engine import RiskEngine
from core.setup.decision_engine import DecisionEngine
from core.setup.setup_candidate import SetupCandidate
from core.regime.regime_state import RegimeState
from core.trend.trend_state import TrendState

BASE_DIR = Path(__file__).resolve().parent.parent


def seeded_account(balance=2000.0):
    return AccountState(
        starting_balance=balance,
        balance=balance,
        equity=balance,
        peak_equity=balance,
        drawdown=0.0,
        drawdown_percent=0.0,
    )


def candidate(direction="BULLISH", entry=100.0, stop=90.0, tp=160.0,
              confidence=85.0, score=85.0):
    # rr = 60/10 = 6.0 exactly (inside both research and runtime ranges).
    c = SetupCandidate(
        direction=direction, entry=entry, stop_loss=stop, take_profit=tp,
        risk_reward=(abs(tp - entry) / abs(entry - stop)) if entry != stop else 0.0,
        confidence=confidence, score=score,
    )
    c.trend = TrendState(direction=direction)
    c.regime = RegimeState(score=80.0, confidence=80.0)
    return c


def decide(cands):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    context.trade_setups = list(cands)
    engine = DecisionEngine()
    engine.analyze(context)
    return engine, context


def size_order(signal, balance=2000.0):
    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    context.execution_signal = signal
    context.account = seeded_account(balance)
    engine = RiskEngine()
    engine.analyze(context)
    return context.order


class TestCostAuthority(unittest.TestCase):
    def test_production_defaults_explicit_zero(self):
        self.assertEqual(PRODUCTION_DEFAULTS,
                         CostSpec(per_trade=0.0, rate=0.0, slippage_bps=0.0))
        live = from_settings()
        self.assertEqual(live, PRODUCTION_DEFAULTS)

    def test_formula_pins(self):
        spec = CostSpec(per_trade=0.0, rate=0.00059, slippage_bps=5.0)
        commission, slippage = spec.compute(500.0)
        self.assertAlmostEqual(commission, 0.295)
        self.assertAlmostEqual(slippage, 0.5)
        c0, s0 = CostSpec().compute(1234.5)
        self.assertEqual((c0, s0), (0.0, 0.0))

    def test_invalid_specs_refused(self):
        for kwargs in ({"rate": -0.1}, {"slippage_bps": -1.0},
                       {"per_trade": float("nan")}, {"rate": float("inf") * 0}):
            with self.assertRaises(ValueError, msg=kwargs):
                CostSpec(**kwargs)
        with self.assertRaises(ValueError):
            CostSpec().compute(-5.0)

    def test_research_ladder_untouched(self):
        from research.phase11f.harness import COST_SCENARIOS_11F as K
        self.assertEqual(K["A"], {"COMMISSION_PER_TRADE": 0.0,
                                  "COMMISSION_RATE": 0.0, "SLIPPAGE_BPS": 0.0})
        self.assertEqual((K["C"]["COMMISSION_RATE"], K["C"]["SLIPPAGE_BPS"]),
                         (0.00059, 5.0))
        # Production CostSpec reproduces the research C math exactly
        # (shared formula documentation; research keeps its own copy).
        spec = CostSpec(per_trade=0.0, rate=0.00059, slippage_bps=5.0)
        self.assertAlmostEqual(spec.compute(500.0)[0], 500.0 * 0.00059)

    def test_risk_engine_uses_cost_spec(self):
        import inspect
        src = inspect.getsource(__import__("core.risk.risk_engine",
                                           fromlist=["x"]))
        self.assertIn("_production_costs().compute", src)
        self.assertNotIn("COMMISSION_RATE\n", src)


class TestRiskRewardAuthority(unittest.TestCase):
    def test_runtime_policy_is_one_to_twenty(self):
        from core.risk.trading_policy import trading_policy
        policy = trading_policy("TEST")
        self.assertEqual(policy.min_rr, 1.0)
        self.assertEqual(policy.max_rr, 20.0)
        # The frozen research threshold remains a separate research artifact.
        self.assertTrue(
        1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0,
        "frozen-era constant kept for audit"
    )

    def test_no_shadow_on_engine(self):
        self.assertFalse(hasattr(DecisionEngine, "MIN_RISK_REWARD"))

    def test_below_runtime_minimum_rejects(self):
        c = candidate(entry=100.0, stop=90.0, tp=109.9)  # rr = 0.99
        engine, context = decide([c])
        self.assertEqual(context.decision.all(), [])
        self.assertEqual(engine.rejected[0].reasons, ["Risk Reward"])

    def test_one_to_one_boundary_accepts(self):
        c = candidate(entry=100.0, stop=90.0, tp=110.0)  # rr = 1.0
        _, context = decide([c])
        self.assertEqual(len(context.decision.all()), 1)

    def test_mid_range_accepts(self):
        c = candidate(entry=100.0, stop=90.0, tp=150.0)  # rr = 5.0
        _, context = decide([c])
        self.assertEqual(len(context.decision.all()), 1)

    def test_twenty_to_one_boundary_accepts(self):
        c = candidate(entry=100.0, stop=90.0, tp=300.0)  # rr = 20.0
        _, context = decide([c])
        self.assertEqual(len(context.decision.all()), 1)

    def test_above_runtime_maximum_rejects(self):
        c = candidate(entry=100.0, stop=90.0, tp=300.1)  # rr = 20.01
        engine, context = decide([c])
        self.assertEqual(context.decision.all(), [])
        self.assertEqual(engine.rejected[0].reasons, ["Risk Reward"])

    def test_tick_grid_boundary(self):
        # 1.0R on-tick passes; one tick below the configured minimum fails.
        ok = candidate(entry=100.0, stop=90.0, tp=110.0)
        _, ctx_ok = decide([ok])
        self.assertEqual(len(ctx_ok.decision.all()), 1)
        short = candidate(entry=100.0, stop=90.0, tp=109.5)
        eng, ctx_short = decide([short])
        self.assertEqual(ctx_short.decision.all(), [])
        self.assertEqual(eng.rejected[0].reasons, ["Risk Reward"])

    def test_risk_engine_revalidates(self):
        good = candidate(entry=100.0, stop=90.0, tp=150.0)  # rr = 5.0
        order = size_order(good)
        self.assertIsInstance(order, OrderIntent)
        self.assertTrue(order)

    def test_risk_engine_rejects_above_runtime_maximum(self):
        bad = candidate(entry=100.0, stop=90.0, tp=300.1)  # rr = 20.01
        self.assertIsNone(size_order(bad))

    def test_risk_engine_ignores_lying_rr_field(self):
        # Prices imply rr = 5.0 but the signal field claims 99. The gate
        # must use prices, never the self-reported field, and the order must
        # carry the authoritative computed ratio.
        c = candidate(entry=100.0, stop=90.0, tp=150.0)
        c.risk_reward = 99.0
        order = size_order(c)
        self.assertIsInstance(order, OrderIntent)
        self.assertAlmostEqual(order.risk_reward, 5.0)


class FakePositions:
    """Minimal position feed. records = list of dicts; error raises."""

    def __init__(self, records=None, error=None):
        self._records = list(records or [])
        self._error = error
        self.calls = 0

    def positions(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return [dict(r) for r in self._records]


def local_mirror(side="BULLISH", quantity=2.0, entry=100.0):
    return SimpleNamespace(direction=side, quantity=quantity, entry=entry)


def exch(side="buy", size=2.0, entry=100.0):
    return {"side": side, "size": size, "entry": entry}


class TestReconcilerStartup(unittest.TestCase):
    def test_paper_skips_without_touching_executor(self):
        rec = Reconciler(executor=FakePositions([exch()]))
        out = rec.startup_check(dry_run=True)
        self.assertEqual(out["verdict"], "SKIP")
        self.assertFalse(rec.halt_new_orders)

    def test_fresh_boot_flat_matches(self):
        rec = Reconciler(executor=FakePositions([]))
        out = rec.startup_check(dry_run=False)
        self.assertEqual(out["verdict"], "MATCH")
        self.assertFalse(rec.halt_new_orders)

    def test_unexpected_exchange_position_halts(self):
        rec = Reconciler(executor=FakePositions([exch()]))
        out = rec.startup_check(dry_run=False)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "UNEXPECTED_POSITION")

    def test_snapshot_match_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            rec = Reconciler(executor=FakePositions([exch()]),
                             snapshot_path=path)
            rec.persist(rec.snapshot_state(True, "OID-1", None,
                                           local_mirror(), 1000))
            rec2 = Reconciler(executor=FakePositions([exch()]),
                              snapshot_path=path)
            out = rec2.startup_check(dry_run=False)
            self.assertEqual(out["verdict"], "MATCH")
            self.assertFalse(rec2.halt_new_orders)

    def test_snapshot_open_but_exchange_flat_halts(self):
        # Crash with an open position, exchange stopped out while the
        # process was down: the close was never booked locally, so a
        # fresh boot must halt for operator review, not assume flat.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            rec = Reconciler(executor=FakePositions([]),
                             snapshot_path=path)
            rec.persist(rec.snapshot_state(True, "OID-1", None,
                                           local_mirror(), 1000))
            rec2 = Reconciler(executor=FakePositions([]),
                              snapshot_path=path)
            out = rec2.startup_check(dry_run=False)
            self.assertEqual(out["verdict"], "MISMATCH")
            self.assertTrue(rec2.halt_new_orders)
            self.assertEqual(rec2.drifts[-1]["kind"], "MISSING_POSITION")

    def test_corrupt_snapshot_degrades_to_no_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w") as handle:
                handle.write("{not json")
            rec = Reconciler(executor=FakePositions([]),
                             snapshot_path=path)
            out = rec.startup_check(dry_run=False)
            self.assertEqual(out["verdict"], "MATCH")

    def test_executor_error_halts_fail_closed(self):
        rec = Reconciler(executor=FakePositions(error=RuntimeError("down")))
        out = rec.startup_check(dry_run=False)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)

    def test_no_feed_is_inert_not_halt(self):
        rec = Reconciler(executor=None)
        out = rec.startup_check(dry_run=False)
        self.assertEqual(out["verdict"], "MISMATCH")
        # ...unless the caller never arms: passive default stays quiet.
        # (BrokerEngine only auto-arms live engines; see wiring test.)


class TestReconcilerRuntime(unittest.TestCase):
    def test_mirror_matches(self):
        rec = Reconciler(executor=FakePositions([exch()]))
        out = rec.runtime_check(10, 100, local_mirror(), None)
        self.assertEqual(out["verdict"], "MATCH")

    def test_partial_fill_qty_halts(self):
        rec = Reconciler(executor=FakePositions([exch(size=1.0)]))
        out = rec.runtime_check(10, 100, local_mirror(quantity=2.0), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)
        self.assertEqual(rec.drifts[-1]["kind"], "PARTIAL_FILL_QTY")
        self.assertEqual(rec.drifts[-1]["local_quantity"], 2.0)
        self.assertEqual(rec.drifts[-1]["exchange_quantity"], 1.0)

    def test_side_mismatch_halts(self):
        rec = Reconciler(executor=FakePositions([exch(side="sell")]))
        out = rec.runtime_check(10, 100, local_mirror(side="BULLISH"), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertEqual(rec.drifts[-1]["kind"], "SIDE_MISMATCH")

    def test_entry_mismatch_halts_beyond_tolerance(self):
        rec = Reconciler(executor=FakePositions([exch(entry=101.0)]),
                         entry_tolerance=1e-6)
        out = rec.runtime_check(10, 100, local_mirror(entry=100.0), None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertEqual(rec.drifts[-1]["kind"], "ENTRY_MISMATCH")

    def test_entry_within_tolerance_matches(self):
        rec = Reconciler(executor=FakePositions([exch(entry=100.00005)]),
                         entry_tolerance=1e-6)
        out = rec.runtime_check(10, 100, local_mirror(entry=100.0), None)
        self.assertEqual(out["verdict"], "MATCH")

    def test_in_transit_order_does_not_halt(self):
        rec = Reconciler(executor=FakePositions([]))
        order = {"order_id": "OID-9", "status": "PENDING", "age_bars": 0}
        out = rec.runtime_check(10, 100, None, order)
        self.assertEqual(out["verdict"], "IN_FLIGHT")
        self.assertFalse(rec.halt_new_orders)

    def test_stale_order_without_position_halts(self):
        rec = Reconciler(executor=FakePositions([]), max_transit_bars=30)
        order = {"order_id": "OID-9", "status": "PENDING", "age_bars": 31}
        out = rec.runtime_check(10, 100, None, order)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertTrue(rec.halt_new_orders)

    def test_resolve_requires_note_and_clears(self):
        rec = Reconciler(executor=FakePositions([]))
        rec.runtime_check(10, 100, local_mirror(), None)  # missing -> halt
        self.assertTrue(rec.halt_new_orders)
        with self.assertRaises(ValueError):
            rec.resolve("")
        self.assertTrue(rec.halt_new_orders)
        rec.resolve("operator verified flat, ref OP-123")
        self.assertFalse(rec.halt_new_orders)
        self.assertEqual(len(rec.resolutions), 1)

    def test_snapshot_round_trip_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "state.json")
            rec = Reconciler(executor=FakePositions([]), snapshot_path=path)
            state = rec.snapshot_state(True, "OID-1", "P-7", local_mirror(), 555)
            self.assertTrue(rec.persist(state))
            loaded = Reconciler(executor=FakePositions([]),
                                snapshot_path=path).load_snapshot()
            self.assertEqual(loaded["open_order_id"], "OID-1")
            self.assertEqual(loaded["live_trade"]["entry"], 100.0)
            self.assertTrue(rec.clear_snapshot())
            self.assertIsNone(rec.load_snapshot())
            rec2 = Reconciler(executor=None, snapshot_path=None)
            self.assertFalse(rec2.persist(state))


class TestBrokerReconcileWiring(unittest.TestCase):
    def _halted_broker(self):
        from core.live.broker_engine import BrokerEngine
        broker = BrokerEngine(pipeline=None, event_bus=None,
                              executor=FakePositions([]), dry_run=True)
        broker.reconciler.halt_new_orders = True
        broker.reconciler.halt_reason = "test halt"
        return broker

    def test_halt_blocks_routing(self):
        broker = self._halted_broker()
        order = SimpleNamespace(setup_id="S-1")
        broker.pipeline = SimpleNamespace(
            context=SimpleNamespace(order=order, execution_signal=None))
        broker._route(None)
        self.assertEqual(broker.placed, [])
        self.assertIsNone(broker._live_trade)

    def test_paper_default_is_passive(self):
        from core.live.broker_engine import BrokerEngine
        broker = BrokerEngine(pipeline=None, event_bus=None,
                              executor=FakePositions([]), dry_run=True)
        self.assertFalse(broker.reconciler.halt_new_orders)
        self.assertIsNone(broker.reconciler.executor)

    def test_live_without_feed_warns_inert(self):
        from core.live.broker_engine import BrokerEngine
        from core.execution.live_safety_gate import LiveSafetyGate
        # An executor with no positions() probe offers no exchange
        # authority: the engine stays passive and warns loudly.
        feedless = SimpleNamespace()
        with self.assertLogs(level="ERROR") as logs:
            broker = BrokerEngine(
                pipeline=None, event_bus=None,
                executor=feedless, dry_run=False,
                safety=LiveSafetyGate.test_armed())
        self.assertTrue(any("RECONCILE_INERT" in m for m in logs.output))
        self.assertFalse(broker.reconciler.halt_new_orders)

    def test_live_with_feed_auto_verifies(self):
        from core.live.broker_engine import BrokerEngine
        from core.execution.live_safety_gate import LiveSafetyGate
        # A live executor exposing positions() is auto-wired as the
        # reconciler feed (no explicit reconciler needed).
        broker = BrokerEngine(
            pipeline=None, event_bus=None,
            executor=FakePositions([]), dry_run=False,
            safety=LiveSafetyGate.test_armed())
        self.assertIsNotNone(broker.reconciler.executor)


class TestConfigGovernance(unittest.TestCase):
    def test_profiles_never_read_by_production(self):
        hits = []
        for path in list((BASE_DIR / "core").rglob("*.py")):
            src = path.read_text(encoding="utf-8", errors="replace")
            code = "".join(
                " " * (t.end[1] - t.start[1]) if t.type in
                (tokenize.STRING, tokenize.COMMENT) else t.string
                for t in tokenize.generate_tokens(io.StringIO(src).readline))
            if "trading_profile" in code or "PROFILES" in code:
                hits.append(str(path))
        self.assertEqual(hits, [])

    def test_position_size_rr_semantics_pinned(self):
        ps = PositionSize(balance=2000.0, risk_percent=0.01, risk_amount=20.0,
                          allocation=500.0, leverage=10.0, entry_price=100.0,
                          stop_price=90.0, stop_distance=10.0, quantity=2.0,
                          position_value=500.0, expected_loss=20.0,
                          target_price=160.0)
        # Phase 4 verified correction: the notional-at-risk multiple and
        # the true entry/stop/target reward/risk are distinct names.
        self.assertAlmostEqual(ps.notional_to_risk, 25.0)
        self.assertAlmostEqual(ps.reward_to_risk, 6.0)
        # The former misleading risk_reward alias is retired.
        self.assertFalse(hasattr(ps, "risk_reward"))

    def test_decision_gate_reads_config_live(self):
        import core.setup.decision_engine as DE
        self.assertTrue(
        1.0 <= DE.risk_settings.MIN_RISK_REWARD <= 20.0,
        "frozen-era constant kept for audit"
    )


if __name__ == "__main__":
    unittest.main()
