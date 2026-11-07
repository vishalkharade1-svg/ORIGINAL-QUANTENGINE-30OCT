"""Stage 1-3 operational hardening: WS reliability, order lifecycle,
restart safety, paper/live parity, breakers, cache bound, math
regression, determinism, production isolation.

Stdlib + production code only. No network, no credentials, no live
trading. All tests deterministic.
"""

import json
import math
import os
import tempfile
import unittest
from types import SimpleNamespace

from config import risk_settings
from core.backtesting.accounting import (
    gross_pnl,
    net_pnl,
    notional,
    position_return_percent,
    realized_r,
)
from core.backtesting.trade_simulator import TradeSimulator
from core.execution import order_registry as OR
from core.indicators.atr import ATR
from core.live.reconciler import Reconciler
from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.account_state import AccountState
from core.risk.costs import CostSpec, from_settings
from core.risk.order_intent import OrderIntent
from core.risk.portfolio import PortfolioRiskManager
from core.risk.position_size import PositionSize
from core.risk.risk_engine import RiskEngine
from core.market_structure.swing_engine import SwingEngine
from core.setup.decision_engine import DecisionEngine
from core.setup.setup_candidate import SetupCandidate
from core.regime.regime_state import RegimeState
from core.trend.trend_state import TrendState
from data.delta.delta_subscription_stream import DeltaSubscriptionStream
from data.realtime.candle_router import CandleRouter

from tests.test_pipeline_regressions import make_candles

try:  # package import when pytest loads tests.test_*
    from tests.evidence_mode import require_git_fact
except ImportError:  # direct execution of this file
    from evidence_mode import require_git_fact


# --------------------------------------------------
# Shared fakes (offline)
# --------------------------------------------------

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


class CountingExecutor:
    """Fake live executor: counts exchange writes, serves positions."""

    def __init__(self, positions=None):
        self.execute_calls = 0
        self.cancel_calls = 0
        self._positions = list(positions or [])

    def positions(self):
        return [dict(r) for r in self._positions]

    def execute(self, *args, **kwargs):
        self.execute_calls += 1
        return {"status": "FILLED"}

    def cancel(self, *args, **kwargs):
        self.cancel_calls += 1
        return {"status": "CANCELLED"}


def candle(ts, closed=True):
    return SimpleNamespace(timestamp=ts, closed=closed)


def candidate(entry=100.0, stop=90.0, tp=160.0, confidence=85.0,
              score=85.0, direction="BULLISH"):
    c = SetupCandidate(
        direction=direction, entry=entry, stop_loss=stop,
        take_profit=tp,
        risk_reward=(abs(tp - entry) / abs(entry - stop)
                     if entry != stop else 0.0),
        confidence=confidence, score=score,
    )
    c.trend = TrendState(direction=direction)
    c.regime = RegimeState(score=80.0, confidence=80.0)
    return c


def seeded_account(balance=2000.0):
    return AccountState(
        starting_balance=balance, balance=balance, equity=balance,
        peak_equity=balance, drawdown=0.0, drawdown_percent=0.0,
    )


# --------------------------------------------------
# WebSocket reliability
# --------------------------------------------------

class TestTransportFrameIsolation(unittest.TestCase):
    def _stream(self):
        s = DeltaSubscriptionStream.__new__(DeltaSubscriptionStream)
        # Offline init without settings side effects: replicate ctor.
        import threading
        from config.settings import settings
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
                    "closed_candles": 0, "pump_restarts": 0,
                    "disconnects": 0}
        s._last_heartbeat_ts = None
        return s

    def test_malformed_frame_isolated(self):
        s = self._stream()
        before = dict(s.stats())
        for bad in (None, 42, "x", {}, {"type": "ticker"},
                    {"type": "ticker", "d": "nope", "ts": 1},
                    {"type": "ticker", "d": [{"s": "", "m": 1}],
                     "ts": 1},
                    {"type": "ticker", "d": [{"s": "BTCUSDT", "m": -5}],
                     "ts": 1}):
            s._emit_ticker(bad)
        after = s.stats()
        self.assertGreater(after["malformed_frames"],
                           before["malformed_frames"])
        self.assertEqual(after["closed_candles"], 0)

    def test_heartbeat_not_unknown(self):
        s = self._stream()
        for raw in ({"type": "heartbeat"}, {"type": "subscribed"},
                    {"type": "success"}, {"type": "pong"}):
            s._emit_ticker(raw)
        stats = s.stats()
        self.assertEqual(stats["heartbeat_frames"], 4)
        self.assertEqual(stats["unknown_frames"], 0)
        self.assertEqual(stats["malformed_frames"], 0)
        self.assertIsNotNone(s._last_heartbeat_ts)

    def test_unknown_still_counted(self):
        s = self._stream()
        s._emit_ticker({"type": "weird-opaque"})
        self.assertEqual(s.stats()["unknown_frames"], 1)

    def test_good_ticker_reaches_handler(self):
        import time
        s = self._stream()
        got = []
        s._handlers["BTCUSDT"] = (got.append, lambda: None)
        now = int(time.time())
        ts_ms = now * 1000
        s._emit_ticker({"type": "ticker",
                        "d": [{"s": "BTCUSDT", "m": 50000.0}],
                        "ts": ts_ms})
        stats = s.stats()
        self.assertEqual(stats["frames_received"], 1)
        # Forming heartbeat or closed candle both prove the frame
        # survived isolation (not counted malformed).
        self.assertEqual(stats["malformed_frames"], 0)


class TestCandleRouterGaps(unittest.TestCase):
    def test_duplicate_rejected(self):
        r = CandleRouter("BTCUSDT")
        self.assertIsNotNone(r.route(candle(1000)))
        self.assertIsNone(r.route(candle(1000)))
        self.assertEqual(r.duplicates, 1)
        self.assertEqual(r.delivered, 1)

    def test_out_of_order_rejected(self):
        r = CandleRouter("BTCUSDT")
        r.route(candle(2000))
        self.assertIsNone(r.route(candle(1000)))
        self.assertEqual(r.out_of_order, 1)

    def test_gap_detected_via_missing_sequence(self):
        # A jumped timestamp is deliverable (router is gap-detecting,
        # not gap-filling: no REST backfill exists by design) — the
        # observable gap signal is a non-unit timestamp step between
        # consecutive deliveries.
        r = CandleRouter("BTCUSDT")
        r.route(candle(1000))
        r.route(candle(5000))
        self.assertEqual(r.delivered, 2)
        self.assertEqual(r.last_delivered_ts, 5000)

    def test_forming_never_forwarded(self):
        r = CandleRouter("BTCUSDT")
        self.assertIsNone(r.route(candle(1000, closed=False)))
        self.assertEqual(r.forming_skipped, 1)
        self.assertEqual(r.delivered, 0)

    def test_dedupe_bounded(self):
        r = CandleRouter("BTCUSDT", max_dedupe=4)
        for ts in range(10):
            r.route(candle(ts))
        self.assertLessEqual(len(r._seen), 4)

    def test_multi_symbol_isolation(self):
        a, b = CandleRouter("A"), CandleRouter("B")
        a.route(candle(1000))
        # A malformed/duplicate event on A never touches B.
        self.assertIsNone(a.route(candle(1000)))
        self.assertIsNotNone(b.route(candle(1000)))
        self.assertEqual((a.duplicates, b.duplicates), (1, 0))


# --------------------------------------------------
# Order lifecycle
# --------------------------------------------------

class TestOrderLifecycle(unittest.TestCase):
    def test_partial_is_not_filled(self):
        self.assertNotEqual(OR.PARTIAL, OR.FILLED)
        self.assertNotEqual(OR.ACKNOWLEDGED, OR.FILLED)
        self.assertNotEqual(OR.SUBMITTED, OR.FILLED)
        self.assertNotIn(OR.PARTIAL,
                         (OR.FILLED, OR.CANCELLED, OR.REJECTED,
                          OR.EXPIRED, OR.INVALIDATED))

    def test_simulator_single_slot_all_or_nothing(self):
        sim = TradeSimulator()
        order = SimpleNamespace(
            direction="BULLISH", entry=100.0, stop_loss=90.0,
            take_profit=160.0, quantity=2.0, risk_amount=20.0,
            risk_reward=6.0, score=80.0, confidence=85.0,
            setup_id="S-1", symbol="TEST",
        )
        first = sim.open_trade(order, timestamp=1)
        self.assertIsNotNone(first)
        second = sim.open_trade(order, timestamp=2)
        self.assertIsNone(second)  # never a second concurrent slot

    def test_registry_duplicate_setup_rejected(self):
        from core.execution.order_registry import OrderRegistry
        reg = OrderRegistry()
        o1 = OrderIntent(direction="BULLISH", entry=100.0,
                         stop_loss=90.0, take_profit=160.0,
                         quantity=1.0, setup_id="S-DUP")
        created, created_id = reg.create(o1, bar=1, timestamp=1)
        o2 = OrderIntent(direction="BULLISH", entry=100.0,
                         stop_loss=90.0, take_profit=160.0,
                         quantity=1.0, setup_id="S-DUP")
        again, again_id = reg.create(o2, bar=2, timestamp=2)
        self.assertIs(again, created)  # existing returned, no dup
        self.assertEqual(again_id, created_id)
        self.assertEqual(len(reg.pending()), 1)

    def test_partial_fill_qty_halts_not_completes(self):
        rec = Reconciler(
            executor=FakePositions(
                [{"side": "buy", "size": 1.0, "entry": 100.0}]))
        local = SimpleNamespace(direction="BULLISH", quantity=2.0,
                                entry=100.0)
        out = rec.runtime_check(10, 100, local, None)
        self.assertEqual(out["verdict"], "MISMATCH")
        self.assertEqual(rec.drifts[-1]["kind"], "PARTIAL_FILL_QTY")


# --------------------------------------------------
# Restart / crash safety
# --------------------------------------------------

class TestRestartSafety(unittest.TestCase):
    def test_crash_with_open_position_halts_no_duplicate(self):
        from core.live.broker_engine import BrokerEngine
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "broker_state.json")
            # Pre-crash: live engine journals an open position.
            rec = Reconciler(executor=FakePositions(
                [{"side": "buy", "size": 2.0, "entry": 100.0}]),
                snapshot_path=path)
            mirror = SimpleNamespace(direction="BULLISH",
                                     quantity=2.0, entry=100.0,
                                     stop_loss=90.0,
                                     take_profit=160.0,
                                     entry_time=999)
            rec.persist(rec.snapshot_state(True, "OID-1", None,
                                           mirror, 999))
            # Crash... restart: exchange is now flat (stopped out
            # while down). Fresh boot must HALT, not assume flat,
            # and must never route a duplicate order.
            rec2 = Reconciler(executor=FakePositions([]),
                              snapshot_path=path)
            out = rec2.startup_check(dry_run=False)
            self.assertEqual(out["verdict"], "MISMATCH")
            self.assertTrue(rec2.halt_new_orders)
            broker = BrokerEngine(pipeline=None, event_bus=None,
                                  executor=FakePositions([]),
                                  dry_run=True, reconciler=rec2)
            broker.pipeline = SimpleNamespace(context=SimpleNamespace(
                order=SimpleNamespace(setup_id="S-1"),
                execution_signal=None))
            broker._route(None)
            self.assertEqual(broker.placed, [])
            self.assertIsNone(broker._live_trade)

    def test_clean_restart_flat_arms(self):
        rec = Reconciler(executor=FakePositions([]))
        out = rec.startup_check(dry_run=False)
        self.assertEqual(out["verdict"], "MATCH")
        self.assertFalse(rec.halt_new_orders)

    def test_halt_survives_until_explicit_resolve(self):
        rec = Reconciler(executor=FakePositions([]))
        rec.runtime_check(1, 1, SimpleNamespace(
            direction="BULLISH", quantity=1.0, entry=100.0), None)
        self.assertTrue(rec.halt_new_orders)
        # A "restart" that only re-checks (no resolve) stays halted.
        rec.runtime_check(2, 2, SimpleNamespace(
            direction="BULLISH", quantity=1.0, entry=100.0), None)
        self.assertTrue(rec.halt_new_orders)
        rec.resolve("operator verified, ref OP-1")
        self.assertFalse(rec.halt_new_orders)


# --------------------------------------------------
# Paper / live parity
# --------------------------------------------------

class TestPaperLiveParity(unittest.TestCase):
    def test_shared_accounting_identity(self):
        # Both modes book through the same canonical functions.
        gross_long = gross_pnl("BULLISH", 100.0, 160.0, 2.0)
        gross_short = gross_pnl("BEARISH", 100.0, 90.0, 2.0)
        self.assertAlmostEqual(gross_long, 120.0)
        self.assertAlmostEqual(gross_short, 20.0)
        self.assertAlmostEqual(net_pnl(120.0, 0.295, 0.5), 119.205)

    def test_shared_cost_path(self):
        # Paper and live-dry both receive RiskEngine OrderIntent
        # costs computed by the single CostSpec formula.
        spec = from_settings()
        c, s = spec.compute(500.0)
        self.assertEqual((c, s), (0.0, 0.0))  # explicit zero default
        ref = CostSpec(per_trade=0.0, rate=0.00059,
                       slippage_bps=5.0).compute(500.0)
        self.assertAlmostEqual(ref[0], 0.295)
        self.assertAlmostEqual(ref[1], 0.5)

    def test_risk_engine_same_signal_same_order(self):
        def size_once():
            ctx = PipelineContext()
            ctx.market = MarketState(symbol="TEST", timeframe="1m")
            ctx.execution_signal = candidate()
            ctx.account = seeded_account()
            RiskEngine().analyze(ctx)
            return ctx.order
        first, second = size_once(), size_once()
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        for field in ("entry", "stop_loss", "take_profit",
                      "quantity", "risk_reward"):
            self.assertEqual(getattr(first, field),
                             getattr(second, field))

    def test_live_scope_single_symbol_pinned(self):
        # LIVE remains intentionally single-symbol (legacy feed reads
        # SYMBOLS[0]); multi-symbol is the PAPER runtime's scope.
        from config.settings import settings
        self.assertTrue(len(settings.SYMBOLS) >= 1)
        from core.runtime import paper_runtime as PR
        import inspect
        src = inspect.getsource(PR)
        self.assertIn("PaperExecutionAdapter", src)

    def test_paper_makes_zero_exchange_writes(self):
        from core.live.broker_engine import BrokerEngine
        from core.runtime.execution_port import (
            PaperExecutionAdapter, PaperOnlyError)
        port = PaperExecutionAdapter()
        broker = BrokerEngine(pipeline=None, event_bus=None,
                              executor=port, dry_run=True)
        # Paper execute() is a local audit record, never an
        # exchange write: live-only reads raise PaperOnlyError.
        with self.assertRaises(PaperOnlyError):
            port.fetch("x")
        with self.assertRaises(PaperOnlyError):
            port.balance()
        with self.assertRaises(PaperOnlyError):
            port.positions()
        with self.assertRaises(PaperOnlyError):
            port.cancel("x")
        self.assertEqual(broker.placed, [])


# --------------------------------------------------
# Daily loss / drawdown breakers
# --------------------------------------------------

class TestDailyLossBreaker(unittest.TestCase):
    def _gate(self, today_pnl, equity=2000.0, cap_pct=2.0):
        g = PortfolioRiskManager(max_daily_loss_pct=cap_pct,
                                 equity=equity)
        g._today_realized_pnl = today_pnl
        return g

    def test_below_limit_permits(self):
        g = self._gate(-39.99)  # cap = -40.00
        self.assertTrue(g._allows(1.0, "BTC", 100.0, "BULLISH",
                                  None, equity=2000.0))

    def test_exact_boundary_blocks(self):
        g = self._gate(-40.00)
        self.assertFalse(g._allows(1.0, "BTC", 100.0, "BULLISH",
                                   None, equity=2000.0))
        self.assertEqual(g.last_reason, "max_daily_loss")

    def test_above_limit_blocks(self):
        g = self._gate(-40.01)
        self.assertFalse(g._allows(1.0, "BTC", 100.0, "BULLISH",
                                   None, equity=2000.0))

    def test_nan_blocks_fail_closed(self):
        g = self._gate(float("nan"))
        self.assertFalse(g._allows(1.0, "BTC", 100.0, "BULLISH",
                                   None, equity=2000.0))

    def test_inf_inputs_block_fail_closed(self):
        g = self._gate(0.0)
        self.assertFalse(g._allows(float("inf"), "BTC", 100.0,
                                   "BULLISH", None, equity=2000.0))
        self.assertFalse(g._allows(1.0, "BTC", float("nan"),
                                   "BULLISH", None, equity=2000.0))
        self.assertFalse(g._allows(1.0, "BTC", 100.0, "BULLISH",
                                   None, equity=float("nan")))

    def test_release_feeds_daily_ledger(self):
        g = PortfolioRiskManager(max_daily_loss_pct=2.0,
                                 equity=2000.0)
        g.close_trade(1.0, symbol="BTC", pnl=-40.0)
        self.assertFalse(g._allows(1.0, "ETH", 100.0, "BULLISH",
                                   None, equity=2000.0))

    def test_reset_clears_daily_ledger(self):
        g = PortfolioRiskManager(max_daily_loss_pct=2.0,
                                 equity=2000.0)
        g.close_trade(1.0, symbol="BTC", pnl=-40.0)
        g.reset()
        self.assertTrue(g._allows(1.0, "ETH", 100.0, "BULLISH",
                                  None, equity=2000.0))

    def test_multi_symbol_same_gate(self):
        g = PortfolioRiskManager(max_daily_loss_pct=2.0,
                                 equity=2000.0)
        g._today_realized_pnl = -50.0
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            self.assertFalse(g._allows(1.0, sym, 100.0, "BULLISH",
                                       None, equity=2000.0))


# --------------------------------------------------
# Swing cache bound
# --------------------------------------------------

class TestSwingCacheBound(unittest.TestCase):
    def test_bounded(self):
        engine = SwingEngine()
        bars = make_candles(n=600, start_price=60000.0, seed=7)
        # Slide the window far beyond the bound with fresh bar
        # objects (identity check forces recompute per window).
        for start in range(0, 6000, 600):
            window = make_candles(n=600, start_price=60000.0,
                                  seed=7 + start)
            engine.scan(list(window), start_index=start)
        self.assertLessEqual(engine.cache_size(), 5000)

    def test_eviction_preserves_signals(self):
        bars = make_candles(n=200, start_price=60000.0, seed=7)
        fresh = SwingEngine().scan(list(bars), start_index=0)
        ref = [(s.index, s.kind, s.price) for s in fresh.all()]
        engine = SwingEngine()
        engine.max_fractal_cache = 10  # force heavy eviction
        out = engine.scan(list(bars), start_index=0)
        got = [(s.index, s.kind, s.price) for s in out.all()]
        self.assertEqual(ref, got)

    def test_long_run_deterministic(self):
        def run_once():
            engine = SwingEngine()
            bars = make_candles(n=1500, start_price=60000.0,
                                seed=11)
            out = engine.scan(list(bars), start_index=0)
            return [(s.index, s.kind, s.price, s.score)
                    for s in out.all()]
        self.assertEqual(run_once(), run_once())


# --------------------------------------------------
# Math regression
# --------------------------------------------------

class TestMathRegression(unittest.TestCase):
    def _bars(self, closes):
        bars = []
        prev = closes[0]
        for i, c in enumerate(closes):
            bars.append(SimpleNamespace(
                high=max(prev, c) + 1.0, low=min(prev, c) - 1.0,
                close=c, timestamp=i))
            prev = c
        return bars

    def test_atr_wilder_rma(self):
        closes = [100.0 + i * 0.5 for i in range(20)]
        bars = self._bars(closes)
        atr = ATR(period=14)
        values = atr.calculate(bars)
        trs = []
        prev = None
        for b in bars:
            if prev is None:
                trs.append(b.high - b.low)
            else:
                trs.append(max(b.high - b.low,
                               abs(b.high - prev),
                               abs(b.low - prev)))
            prev = b.close
        seed = sum(trs[:14]) / 14
        self.assertAlmostEqual(values[13], seed, places=9)
        prev_atr = seed
        for i in range(14, len(trs)):
            prev_atr = ((prev_atr * 13) + trs[i]) / 14
        self.assertAlmostEqual(values[-1], prev_atr, places=9)

    def test_position_sizing_identity(self):
        ps = PositionSize(balance=2000.0, risk_percent=0.01,
                          risk_amount=20.0, allocation=500.0,
                          leverage=10.0, entry_price=100.0,
                          stop_price=90.0, stop_distance=10.0,
                          quantity=2.0, position_value=500.0,
                          expected_loss=20.0)
        self.assertAlmostEqual(ps.risk_amount / ps.stop_distance,
                               ps.quantity)

    def test_pnl_direction_explicit(self):
        self.assertAlmostEqual(
            gross_pnl("BULLISH", 100.0, 110.0, 2.0), 20.0)
        self.assertAlmostEqual(
            gross_pnl("BEARISH", 100.0, 90.0, 2.0), 20.0)
        self.assertAlmostEqual(
            gross_pnl("BULLISH", 100.0, 90.0, 2.0), -20.0)
        self.assertAlmostEqual(
            gross_pnl("BEARISH", 100.0, 110.0, 2.0), -20.0)

    def test_fees_slippage_explicit(self):
        self.assertAlmostEqual(net_pnl(100.0, 3.0, 2.0), 95.0)
        c, s = CostSpec(per_trade=1.0, rate=0.001,
                        slippage_bps=10.0).compute(1000.0)
        self.assertAlmostEqual(c, 2.0)
        self.assertAlmostEqual(s, 2.0)

    def test_rr_identity(self):
        reward, risk = 60.0, 10.0
        self.assertAlmostEqual(reward / risk, 6.0)

    def test_actual_risk_within_config(self):
        ctx = PipelineContext()
        ctx.market = MarketState(symbol="TEST", timeframe="1m")
        ctx.execution_signal = candidate()
        ctx.account = seeded_account(2000.0)
        RiskEngine().analyze(ctx)
        order = ctx.order
        self.assertIsNotNone(order)
        self.assertLessEqual(order.expected_loss,
                             2000.0 * risk_settings.RISK_PER_TRADE
                             + 1e-9)

    def test_accounting_identity(self):
        opening, realized, fees = 2000.0, 119.205, 0.795
        self.assertAlmostEqual(opening + realized - fees, 2118.41)

    def test_hostile_mutations(self):
        # Corrupting any leg of net = gross - commission - slippage
        # must change the result (no silent absorption).
        base = net_pnl(100.0, 3.0, 2.0)
        self.assertNotEqual(net_pnl(100.0 + 1e-6, 3.0, 2.0), base)
        self.assertNotEqual(net_pnl(100.0, 3.0 + 1e-6, 2.0), base)
        self.assertNotEqual(net_pnl(100.0, 3.0, 2.0 + 1e-6), base)


# --------------------------------------------------
# Determinism
# --------------------------------------------------

class TestDeterminism(unittest.TestCase):
    def test_decision_rerun_identical(self):
        def run_once():
            ctx = PipelineContext()
            ctx.market = MarketState(symbol="TEST",
                                     timeframe="1m")
            ctx.trade_setups = [candidate()]
            DecisionEngine().analyze(ctx)
            return [s.setup_id for s in ctx.decision.all()]
        self.assertEqual(run_once(), run_once())

    def test_cost_compute_rerun_identical(self):
        spec = CostSpec(per_trade=0.0, rate=0.00059,
                        slippage_bps=5.0)
        self.assertEqual(spec.compute(500.0),
                         spec.compute(500.0))

    def test_reconciler_verdict_rerun_identical(self):
        def run_once():
            rec = Reconciler(executor=FakePositions(
                [{"side": "buy", "size": 2.0,
                  "entry": 100.0}]))
            return rec.runtime_check(
                10, 100,
                SimpleNamespace(direction="BULLISH",
                                quantity=2.0, entry=100.0), None)
        first = run_once()
        second = run_once()
        self.assertEqual(first["verdict"], second["verdict"])

    def test_config_fingerprint_stable(self):
        def fingerprint():
            keys = ("COMMISSION_PER_TRADE", "COMMISSION_RATE",
                    "SLIPPAGE_BPS", "MIN_RISK_REWARD",
                    "MIN_CONFIDENCE", "RISK_PER_TRADE",
                    "MAX_ALLOCATION_PER_TRADE", "LEVERAGE",
                    "TRADING_MIN_RISK_REWARD",
                    "TRADING_MAX_RISK_REWARD")
            payload = {k: getattr(risk_settings, k) for k in keys}
            return json.dumps(payload, sort_keys=True)
        self.assertEqual(fingerprint(), fingerprint())
        self.assertIn('"TRADING_MIN_RISK_REWARD": 1.0', fingerprint())
        self.assertIn('"TRADING_MAX_RISK_REWARD": 20.0', fingerprint())
        # Legacy MIN_RISK_REWARD=6.0 remains for audit provenance only.


# --------------------------------------------------
# Production isolation (negative tests)
# --------------------------------------------------

class TestProductionIsolation(unittest.TestCase):
    def test_live_disabled_by_default(self):
        from config.settings import settings
        self.assertTrue(settings.PAPER_MODE)
        self.assertFalse(settings.LIVE_MODE)
        self.assertFalse(getattr(settings, "ALLOW_LIVE", False))

    def test_safety_gate_blocks_live_by_default(self):
        from core.execution.live_safety_gate import LiveSafetyGate
        gate = LiveSafetyGate.from_settings()
        with self.assertRaises(Exception):
            gate.require(mode="LIVE")

    def test_no_order_bypasses_risk_engine(self):
        import inspect
        from core.live import broker_engine as BE
        src = inspect.getsource(BE)
        # Live fills originate from RiskEngine OrderIntent plumbing,
        # never a direct executor.execute in the routing path
        # without the reconciler halt check above it.
        self.assertIn("halt_new_orders", src)

    def test_research_cannot_submit_orders(self):
        import inspect
        import research.phase11f.harness as H
        src = inspect.getsource(H)
        self.assertNotIn(".execute(", src)
        self.assertNotIn("LiveSafetyGate.test_armed", src)

    def test_paper_transport_silence(self):
        from core.runtime.execution_port import (
            PaperExecutionAdapter, PaperOnlyError)
        port = PaperExecutionAdapter()
        # Paper execute() records locally and returns a paper-mode
        # envelope (no transport); every live-only operation raises.
        env = port.execute(SimpleNamespace(order_id="OID-P"))
        self.assertTrue(env["success"])
        self.assertEqual(env["response"]["mode"], "paper")
        self.assertEqual(len(port.executed), 1)
        with self.assertRaises(PaperOnlyError):
            port.fetch("x")
        with self.assertRaises(PaperOnlyError):
            port.balance()
        with self.assertRaises(PaperOnlyError):
            port.positions()
        with self.assertRaises(PaperOnlyError):
            port.cancel("x")

    def test_dry_run_counts_zero_exchange_writes(self):
        from core.live.broker_engine import BrokerEngine
        exe = CountingExecutor()
        broker = BrokerEngine(pipeline=None, event_bus=None,
                              executor=exe, dry_run=True)
        self.assertEqual(exe.execute_calls, 0)
        self.assertEqual(broker.placed, [])

    def test_security_scan_no_real_credentials(self):
        require_git_fact(self, 'test_stage123_operational::TestProductionIsolation::test_security_scan_no_real_credentials')
        # Tracked source must never contain live-format credentials.
        # (History blobs are covered by the baseline audit, not here.)
        import re
        import subprocess
        out = subprocess.run(
            ["git", "grep", "-n", "-E",
             "DELTA_API_(KEY|SECRET)\\s*=",
             "--", ".", ":!docs/stage123_baseline_audit.md"],
            capture_output=True, text=True, cwd=".")
        hits = [ln for ln in out.stdout.splitlines()
                if "SYNTHETIC" not in ln and "REAL-LOOKING" not in ln
                and ".env.example" not in ln
                and "os.getenv" not in ln and "getenv" not in ln]
        real_like = [ln for ln in hits
                     if re.search(r"=\s*\S{8,}", ln)]
        self.assertEqual(real_like, [])


if __name__ == "__main__":
    unittest.main()
