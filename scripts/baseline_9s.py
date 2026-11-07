"""
Fresh baseline backtest — Phase 9S §36.

Deterministic, post-9Q/9S, with explicit realism gate:
- fees, slippage, fill, gap, intrabar (conservative + ambiguous), min-qty
- Records all required §36 fields to docs/audit/baseline_9s.json
"""

import json
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass

from backtesting.backtester import Backtester
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext
from core.events.event_bus import EventBus
from core.backtesting.trade_simulator import TradeSimulator
from core.risk.account import Account
from core.analytics.performance import PerformanceAnalytics
from config import risk_settings

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "docs" / "audit" / "baseline_9s.json"


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0
    symbol: str = "BTCUSDT"


def make_candles(n, seed=2025, start_ts=1704067200):
    import random
    rnd = random.Random(seed)
    out = []
    price = 50000
    for i in range(n):
        o = price
        move = rnd.uniform(-70, 70)
        c = price + move
        h = max(o, c) + rnd.uniform(0, 20)
        l = min(o, c) - rnd.uniform(0, 20)
        out.append(Candle(timestamp=start_ts + i*60, open=o, high=h, low=l, close=c))
        price = c
    return out


def run_baseline():
    candles = make_candles(500, seed=2025)
    ctx = PipelineContext()
    pipeline = InstitutionalPipeline(ctx)
    bus = EventBus()
    sim = TradeSimulator()
    acc = Account(starting_balance=risk_settings.STARTING_BALANCE)
    bt = Backtester(pipeline=pipeline, event_bus=bus, simulator=sim, account=acc)
    t0 = time.time()
    bt.run(candles)
    elapsed = time.time() - t0

    report = PerformanceAnalytics.analyze(acc, sim.registry)
    try:
        version = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()[:7]
    except Exception:
        version = "unknown"

    # Order lifecycle counts
    order_reg = ctx.order_registry
    filled = len([o for o in order_reg.all() if o.status == "FILLED"]) if order_reg else 0
    expired = len(order_reg.expired()) if order_reg else 0
    invalidated = len(order_reg.invalidated()) if order_reg else 0
    rejected = len(order_reg.rejected()) if order_reg else 0
    pending = len(order_reg.pending()) if order_reg else 0

    ambiguous = len([t for t in sim.registry.all() if getattr(t, "ambiguous", False)])

    baseline = {
        "dataset": {"n": len(candles), "symbol": "BTCUSDT", "timeframe": "1m", "start_ts": candles[0].timestamp, "end_ts": candles[-1].timestamp, "start_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(candles[0].timestamp)), "end_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(candles[-1].timestamp))},
        "symbols": ["BTCUSDT"],
        "timeframe": "1m",
        "date_range": [candles[0].timestamp, candles[-1].timestamp],
        "config": {
            "starting_balance": risk_settings.STARTING_BALANCE,
            "risk_per_trade": risk_settings.RISK_PER_TRADE,
            "max_allocation": risk_settings.MAX_ALLOCATION_PER_TRADE,
            "leverage": risk_settings.LEVERAGE,
            "entry_mode": risk_settings.ENTRY_MODE,
            "max_wait_bars": risk_settings.MAX_WAIT_BARS,
            "entry_delay_bars": risk_settings.ENTRY_DELAY_BARS,
        },
        "code_version": version,
        "fees": {"commission_per_trade": risk_settings.COMMISSION_PER_TRADE, "commission_rate": risk_settings.COMMISSION_RATE, "slippage_bps": risk_settings.SLIPPAGE_BPS},
        "fill_model": "conservative SL-first, ambiguous flagged, limit touch low<=entry<=high, next-bar-open for BREAKOUT",
        "n_bars": len(candles),
        "elapsed_seconds": round(elapsed, 3),
        "setups": len(ctx.trade_setups.all()) if ctx.trade_setups else 0,
        "signals": len([s for s in (ctx.execution_signals or [])]) if ctx.execution_signals else 0,
        "orders": len(order_reg.all()) if order_reg else 0,
        "fills": report.total_trades,
        "expirations": expired,
        "invalidations": invalidated,
        "rejected_orders": rejected,
        "pending_orders": pending,
        "filled_orders": filled,
        "wins": report.wins,
        "losses": report.losses,
        "breakevens": report.breakeven,
        "gross_profit": round(report.gross_profit, 2),
        "gross_loss": round(report.gross_loss, 2),
        "gross_pnl": round(report.gross_profit - report.gross_loss, 2),
        "net_pnl": round(report.net_profit, 2),
        "return_pct": round(report.net_profit / report.starting_balance * 100, 4) if report.starting_balance else 0,
        "max_drawdown": round(report.max_drawdown, 2),
        "max_drawdown_pct": round(report.max_drawdown_percent, 4),
        "sharpe": round(report.sharpe, 4),
        "sortino": round(report.sortino, 4),
        "expectancy": round(report.expectancy, 4),
        "profit_factor": round(report.profit_factor, 4) if report.profit_factor != float("inf") else "inf",
        "payoff_ratio": round(report.payoff_ratio, 4),
        "win_rate": round(report.win_rate, 2),
        "avg_win": round(report.avg_win, 2),
        "avg_loss": round(report.avg_loss, 2),
        "avg_bars_held": round(report.avg_bars_held, 2),
        "best_trade": round(report.best_trade, 2),
        "worst_trade": round(report.worst_trade, 2),
        "ambiguous_trades": ambiguous,
        "rejected_trades": 0,
        "risk_stats": {"starting_balance": report.starting_balance, "final_equity": round(report.final_equity, 2), "peak_equity": round(report.peak_equity, 2)},
        "notes": "Post-9Q Wilder ATR, causal displacement, canonical accounting, breakeven, timestamp canonical, CandleBuilder RLock, settings type safety, position sizing explicit, capital floor, intrabar conservative, walk-forward disjoint, Sharpe on returns, REST 429, WS reconnect. Zero-cost baseline (commission/slippage 0) — explicit, not misreported as live.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2)
    print(f"Baseline written to {OUT}")
    print(json.dumps(baseline, indent=2))
    return baseline


if __name__ == "__main__":
    run_baseline()
