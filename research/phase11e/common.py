"""Phase 11E shared research harness (research-only, read-only production use).

Mirrors the construction pattern of scripts/verify_gate_a.py and
scripts/cost_sensitivity_11b.py exactly: fresh CandleBuilder,
InstitutionalPipeline, TradeSimulator, Account, Backtester per
run. Production modules are imported, never modified; config
overrides (costs, sensitivity knobs) apply via try/finally
restoration inside research runs only.
"""

import json
import math
import random
from pathlib import Path

from config import risk_settings
from core.analytics.performance import PerformanceAnalytics
from core.backtesting.accounting import realized_r
from core.backtesting.trade_simulator import TradeSimulator
from core.events.event_bus import EventBus
from core.market_state import MarketState
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext
from core.risk.account import Account
from data.candle_builder import CandleBuilder
from backtesting.backtester import Backtester

RESEARCH_DIR = Path(__file__).resolve().parent
DATA_DIR = RESEARCH_DIR / "data"

COST_SCENARIOS = {
    "A_zero": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.0, "SLIPPAGE_BPS": 0.0},
    "B_small": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.0002, "SLIPPAGE_BPS": 1.0},
    "C_moderate": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.0005, "SLIPPAGE_BPS": 2.0},
    "D_adverse": {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.00059, "SLIPPAGE_BPS": 5.0},
}


# --------------------------------------------------
# Dataset loading + integrity (§4)
# --------------------------------------------------

def load_raw_bars(doc):
    """Normalize a dataset doc to chronological raw bar dicts.

    Accepts Gate A shape ({"raw": [...]}, newest-first) and the
    OOS-file/fresh shape ({"candles": [...]}, chronological).
    Returns (bars_chronological, meta).
    """
    if "raw" in doc:
        bars = list(reversed(doc["raw"]))
    else:
        bars = list(doc.get("candles", []))
    bars = sorted(bars, key=lambda b: int(b["time"]))
    return bars, {
        "symbol": doc.get("symbol"),
        "timeframe": doc.get("timeframe", "1m"),
    }


def validate_bars(bars):
    """Data-integrity audit. Returns a report dict (never raises
    on data problems — problems are recorded, not hidden)."""
    rep = {
        "n": len(bars),
        "chronological": True,
        "duplicates": 0,
        "out_of_order": 0,
        "gaps": 0,
        "missing_volume": 0,
        "invalid_ohlc": 0,
        "non_finite": 0,
        "first": bars[0]["time"] if bars else None,
        "last": bars[-1]["time"] if bars else None,
    }
    if not bars:
        return rep
    seen = set()
    prev = None
    for b in bars:
        try:
            ts = int(b["time"])
            vals = [float(b[k]) for k in ("open", "high", "low", "close")]
            vol = float(b.get("volume", 0.0))
        except (KeyError, TypeError, ValueError):
            rep["invalid_ohlc"] += 1
            continue
        if not all(math.isfinite(v) for v in vals + [vol]):
            rep["non_finite"] += 1
        if min(vals) <= 0 or max(vals) <= 0:
            rep["invalid_ohlc"] += 1
        if b.get("volume", None) is None:
            rep["missing_volume"] += 1
        if ts in seen:
            rep["duplicates"] += 1
        seen.add(ts)
        if prev is not None:
            if ts <= prev:
                rep["out_of_order"] += 1
                rep["chronological"] = False
            elif ts - prev > 60:
                rep["gaps"] += (ts - prev) // 60 - 1
        prev = ts
    return rep


# --------------------------------------------------
# Frozen backtest runner
# --------------------------------------------------

def run_backtest(raw_bars, setting_overrides=None):
    """Run the FROZEN pipeline over CHRONOLOGICAL raw bars.
    setting_overrides (e.g. costs, sensitivity knobs) are
    restored afterwards. Returns {"orders": [...], "trades":
    [...]} with plain-dict trades (gross backed out of booked
    modeled costs).
    """
    saved = {}
    for key, value in (setting_overrides or {}).items():
        saved[key] = getattr(risk_settings, key)
        setattr(risk_settings, key, value)
    try:
        builder = CandleBuilder(max_history=len(raw_bars) or 1)
        builder.load_history(list(raw_bars))
        candles = list(builder.history)
        market = MarketState(symbol="BTCUSDT")
        ctx = PipelineContext()
        ctx.market = market
        bus = EventBus()
        pipeline = InstitutionalPipeline(ctx)
        pipeline.subscribe(bus)
        sim = TradeSimulator()
        acc = Account(starting_balance=risk_settings.STARTING_BALANCE)
        bt = Backtester(pipeline=pipeline, event_bus=bus, simulator=sim, account=acc)
        bt.run(candles)
        orders = []
        if ctx.order_registry:
            for o in ctx.order_registry.all():
                orders.append({
                    "order_id": o.order_id,
                    "status": o.status,
                    "entry": float(o.entry),
                    "quantity": float(o.quantity),
                })
        trades = []
        for t in sim.registry.all():
            commission = float(getattr(t, "commission", 0.0) or 0.0)
            slippage = float(getattr(t, "slippage", 0.0) or 0.0)
            net = float(t.pnl)
            trades.append({
                "trade_id": t.trade_id,
                "direction": t.direction,
                "entry": float(t.entry),
                "exit": float(t.exit_price),
                "quantity": float(t.quantity),
                "entry_time": int(t.entry_time),
                "exit_time": int(getattr(t, "exit_time", 0) or 0),
                "stop": float(getattr(t, "stop_loss", 0.0) or 0.0),
                "take_profit": float(getattr(t, "take_profit", 0.0) or 0.0),
                "gross": net + commission + slippage,
                "commission": commission,
                "slippage": slippage,
                "net": net,
                "risk_amount": float(getattr(t, "risk_amount", 0.0) or 0.0),
            })
        return {"orders": orders, "trades": trades, "n_bars": len(candles)}
    finally:
        for key, value in saved.items():
            setattr(risk_settings, key, value)


def apply_costs(trades, scenario):
    """FIRST-ORDER cost overlay on FINAL-notional trades.

    NOT production-exact: production books commission/
    slippage on the pre-resize SIZER notional (risk_engine),
    which can exceed final notional after
    _resize_for_actual_entry. Use production reruns (run with
    cost overrides) for certified scenario economics; use
    this only for hypothetical overlays (execution
    variations) where final-notional basis is the documented
    assumption.
    """
    spec = COST_SCENARIOS[scenario]
    out = []
    for t in trades:
        pv = abs(t["quantity"]) * abs(t["entry"])
        commission = spec["COMMISSION_PER_TRADE"] + pv * spec["COMMISSION_RATE"]
        slippage = 2.0 * pv * spec["SLIPPAGE_BPS"] / 10000.0
        net = t["gross"] - commission - slippage
        row = dict(t)
        row["commission"] = commission
        row["slippage"] = slippage
        row["net"] = net
        row["pv"] = pv
        out.append(row)
    return out


# --------------------------------------------------
# Metrics (§6 table; production-compatible definitions)
# --------------------------------------------------

def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def trade_metrics(trades, starting_balance=2000.0):
    """Fold metrics with EXPLICIT P&L semantics (11E-Closure Issue 3).

    Each trade dict carries production-booked components:
      gross      = price-movement P&L before costs
                   (production: net + commission + slippage)
      commission = modeled fee booked on the trade (>= 0)
      slippage   = modeled slippage booked on the trade (>= 0)
      net        = gross - commission - slippage (authoritative)

    Output fields (unambiguous):
      gross_pnl  = sum of gross (price edge only, costs excluded)
      fees       = sum of commission
      slippage   = sum of slippage
      net_pnl    = gross_pnl - fees - slippage
    Expectancy, profit factor, Sharpe/Sortino, R-multiples and
    drawdown are computed on NET (the deployable figure).
    `net_consistency_diff` = |net_pnl - sum(input nets)|, which
    must be ~0 (production books net = gross - costs exactly).
    """
    nets = [t["net"] for t in trades]
    grosses = [t.get("gross", t["net"]) for t in trades]
    fees = [t.get("commission", 0.0) for t in trades]
    slips = [t.get("slippage", 0.0) for t in trades]
    n = len(nets)
    gross_pnl = sum(grosses)
    fee_sum = sum(fees)
    slip_sum = sum(slips)
    net = gross_pnl - fee_sum - slip_sum
    wins = sum(1 for x in nets if x > 0)
    losses = sum(1 for x in nets if x < 0)
    be = n - wins - losses
    gross_profit = sum(x for x in nets if x > 0)
    gross_loss = -sum(x for x in nets if x < 0)
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    # Max drawdown on the closed-trade equity curve.
    peak = 0.0
    dd = 0.0
    running = 0.0
    for x in nets:
        running += x
        peak = max(peak, running)
        dd = max(dd, peak - running)
    # Trade-based Sharpe/Sortino on pnl/notional (production formula).
    rets = []
    for t in trades:
        notion = abs(t["entry"]) * abs(t["quantity"])
        rets.append(t["net"] / notion if notion else 0.0)
    sd = _std(rets)
    sharpe = (_mean(rets) / sd * (len(rets) ** 0.5)) if sd > 0 else 0.0
    downside = [min(0.0, r) for r in rets]
    dsd = _std(downside)
    sortino = (_mean(rets) / dsd * (len(rets) ** 0.5)) if dsd > 0 else 0.0
    rs = [realized_r(t["net"], t.get("risk_amount", 0.0)) for t in trades if t.get("risk_amount", 0.0)]
    srs = sorted(rs)
    return {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "breakevens": be,
        "win_rate": (100.0 * wins / n) if n else 0.0,
        "gross_pnl": gross_pnl,
        "fees": fee_sum,
        "slippage": slip_sum,
        "net_pnl": net,
        "net_consistency_diff": abs(net - sum(nets)),
        "expectancy": (net / n) if n else 0.0,
        "profit_factor": pf,
        "max_drawdown": dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "avg_r": (_mean(rs)) if rs else 0.0,
        "median_r": (srs[len(srs) // 2]) if srs else 0.0,
        "largest_win": max(nets) if nets else 0.0,
        "largest_loss": min(nets) if nets else 0.0,
        "final_balance": starting_balance + net,
    }


def summarize_folds(fold_results):
    """Pool trade lists across folds (chronological concat)."""
    pooled = []
    for fr in fold_results:
        pooled.extend(fr["trades"])
    pooled.sort(key=lambda t: (t["exit_time"], t["entry_time"]))
    return pooled
