"""Stage 4 soak (long-horizon; run separately from the fast cert
suite — split only for runner time limits, same deterministic
methodology).

- 30,000-candle continuous paper run on the ACTUAL pipeline +
  Backtester: ledger identity, account finiteness, order-time RR,
  resource maxima (fractal cache, backtester pending peak,
  registry), zero exchange surface. Sweep = cumulative state
  after ONE continuous run (Backtester.run is single-shot; no
  reset mid-run), plus live maxima sampled during the run via
  non-invasive spies.
- Deterministic double-run (identical metrics JSON twice).
- Real-data replay over data/history/BTCUSDT/1m.parquet (flat
  production stub — exercises normalization/market-state, NOT a
  performance sample, NOT OOS).

Labels: PAPER ONLY / NOT OOS / NOT STRATEGY CERTIFICATION.
Wall-clock is printed as telemetry only, never asserted.
"""

import json
import math
import time
import unittest

from core.backtesting.trade_simulator import TradeSimulator
from core.events.event_bus import EventBus
from core.market_state import MarketState
from core.market_structure.swing_engine import SwingEngine
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext
from backtesting.backtester import Backtester

from tests.test_pipeline_regressions import make_candles

PAPER_ONLY = "PAPER ONLY / NOT OOS / NOT STRATEGY CERTIFICATION"
# Phase 12/99: seed 6 yields compliant fills through the
# execution-time revalidation under the active minimum-R policy.
# The seed is a fixture choice, not a result: invariants below
# are seed-agnostic.
SOAK_CANDLES = 30000
SOAK_SEED = 6


def build(symbol="BTCUSDT"):
    ctx = PipelineContext()
    ctx.market = MarketState(symbol=symbol, timeframe="1m")
    bus = EventBus()
    pipe = InstitutionalPipeline(ctx)
    pipe.subscribe(bus)
    sim = TradeSimulator()
    return Backtester(pipe, bus, sim), sim, pipe, ctx


def finite_account(state):
    for field in ("balance", "equity", "realized_pnl", "floating_pnl",
                  "drawdown", "drawdown_percent", "peak_equity"):
        value = float(getattr(state, field, 0.0) or 0.0)
        if not math.isfinite(value):
            return False, field
    return True, ""


def run_soak(n=SOAK_CANDLES, seed=SOAK_SEED, symbol="BTCUSDT"):
    """ONE continuous production-path run. Returns (metrics, observed).

    metrics is deterministic JSON-safe (no wall-clock); observed
    carries order/realized-RR samples for reporting.
    """
    bt, sim, pipe, ctx = build(symbol)
    candles = make_candles(n=n, start_price=60000.0, seed=seed)
    opened = 0
    order_rr_min = float("inf")
    realized_rr = []
    open_peak = 0

    real_open = TradeSimulator.open_trade

    def spy(self, setup, timestamp, quantity=1.0, commission=0.0,
            slippage=0.0):
        nonlocal opened, order_rr_min, open_peak
        opened += 1
        order_rr_min = min(order_rr_min,
                           float(getattr(setup, "risk_reward", 0.0)))
        realized = float(getattr(setup, "actual_risk_reward", 0.0))
        if realized != 0:
            realized_rr.append(realized)
        out = real_open(self, setup, timestamp, quantity,
                        commission, slippage)
        current_open = sum(
            1 for t in sim.registry.all()
            if getattr(t, "status", "") == "OPEN")
        open_peak = max(open_peak, current_open)
        return out

    TradeSimulator.open_trade = spy
    t0 = time.time()
    try:
        bt.run(candles)
    finally:
        TradeSimulator.open_trade = real_open
    elapsed = time.time() - t0
    print("\n[soak-telemetry] bars=%d seconds=%.1f" % (n, elapsed))

    violations = []
    ok, field = finite_account(bt.account.state)
    if not ok:
        violations.append("nonfinite-account:%s" % field)
    trades = sim.registry.all()
    realized = sum(t.pnl for t in trades)
    if abs(bt.account.state.balance - (2000.0 + realized)) > 1e-6:
        violations.append("ledger-identity")
    for trade in trades:
        if not math.isfinite(trade.pnl):
            violations.append("nonfinite-pnl:%s" % trade.setup_id)
        if trade.quantity <= 0:
            violations.append("impossible-qty:%s" % trade.setup_id)
    swing = next((e for e in pipe.engines
                  if isinstance(e, SwingEngine)), None)
    metrics = {
        "label": PAPER_ONLY,
        "bars": n,
        "seed": seed,
        "symbol": symbol,
        "balance": round(bt.account.state.balance, 6),
        "realized": round(realized, 6),
        "trades": len(trades),
        "opened": opened,
        "setup_ids": sorted(t.setup_id for t in trades),
        "maxima": {
            "fractal_cache": swing.cache_size() if swing else -1,
            "backtester_pending_peak": int(
                getattr(bt, "_pending_max", -1)),
            "registry": len(trades),
            "open_peak": open_peak,
        },
        "violations": violations,
    }
    observed = {"order_rr_min": order_rr_min,
                "realized_rr": realized_rr}
    return metrics, observed


class TestPaperSoak30k(unittest.TestCase):
    def test_continuous_30k_invariants(self):
        metrics, observed = run_soak()
        self.assertEqual(metrics["violations"], [])
        self.assertEqual(metrics["bars"], SOAK_CANDLES)
        self.assertEqual(metrics["trades"], metrics["opened"])
        self.assertLessEqual(
            metrics["maxima"]["fractal_cache"], 5000)
        self.assertGreater(metrics["trades"], 0)
        # Order-time RR honors the ACTIVE minimum-R policy for the
        # run symbol (configurable 1:1..1:20, not a hardcoded 6R).
        from core.risk.trading_policy import trading_policy
        policy_min = float(trading_policy("BTCUSDT").min_rr)
        self.assertGreaterEqual(observed["order_rr_min"],
                                policy_min - 1e-9)
        self.assertFalse(hasattr(Backtester, "execute"))
        print("\n[soak-metrics] %s" % json.dumps(
            {k: metrics[k] for k in
             ("bars", "trades", "balance", "realized", "maxima")},
            sort_keys=True))
        print("[soak-economics] %s opened=%d realized_rr_min=%.4f "
              "realized_rr_mean=%.4f" % (
                  PAPER_ONLY, metrics["opened"],
                  min(observed["realized_rr"]),
                  sum(observed["realized_rr"]) /
                  len(observed["realized_rr"])))


class TestSoakDeterminism(unittest.TestCase):
    def test_identical_metrics_twice(self):
        first = json.dumps(run_soak(n=10000, seed=SOAK_SEED)[0],
                           sort_keys=True)
        second = json.dumps(run_soak(n=10000, seed=SOAK_SEED)[0],
                            sort_keys=True)
        self.assertEqual(first, second)


class TestRealDataReplay(unittest.TestCase):
    def test_production_parquet_replay(self):
        import pandas
        df = pandas.read_parquet(
            "data/history/BTCUSDT/1m.parquet")
        self.assertGreaterEqual(len(df), 1000)
        from core.history.candle import Candle
        candles = [Candle(timestamp=int(r.timestamp),
                          open=float(r.open), high=float(r.high),
                          low=float(r.low), close=float(r.close),
                          volume=float(r.volume))
                   for r in df.itertuples()]
        bt, sim, pipe, ctx = build("BTCUSDT")
        bt.run(candles)
        ok, field = finite_account(bt.account.state)
        self.assertTrue(ok, field)
        self.assertEqual(bt.total_bars, len(candles))
        trades = sim.registry.all()
        print("\n[replay-metrics] PAPER ONLY / NOT OOS bars=%d "
              "trades=%d balance=%.6f realized=%.6f" % (
                  len(candles), len(trades),
                  bt.account.state.balance,
                  sum(t.pnl for t in trades)))


if __name__ == "__main__":
    unittest.main()
