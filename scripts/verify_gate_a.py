"""
Gate A — Repeat real 5000-bar test on same snapshot.

Loads docs/audit/baseline_9s_delta_5000_raw.json (exact same dataset),
runs the pipeline twice, and compares every required metric within tolerance.
"""

import json
from pathlib import Path

from data.candle_builder import CandleBuilder
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext
from core.market_state import MarketState
from core.events.event_bus import EventBus
from core.backtesting.trade_simulator import TradeSimulator
from backtesting.backtester import Backtester
from core.risk.account import Account
from core.analytics.performance import PerformanceAnalytics
from config import risk_settings

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_PATH = BASE_DIR / "docs" / "audit" / "baseline_9s_delta_5000_raw.json"


def run_from_raw(raw):
    builder = CandleBuilder(max_history=len(raw) or 1)
    builder.load_history(list(reversed(raw)))
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
    report = PerformanceAnalytics.analyze(acc, sim.registry)
    order_reg = ctx.order_registry
    filled = len([o for o in order_reg.all() if o.status == "FILLED"]) if order_reg else 0
    expired = len(order_reg.expired()) if order_reg else 0
    invalidated = len(order_reg.invalidated()) if order_reg else 0
    ambiguous = len([t for t in sim.registry.all() if getattr(t, "ambiguous", False)])
    rs = [t.pnl / t.risk_amount if getattr(t, "risk_amount", 0) else 0 for t in sim.registry.all() if getattr(t, "risk_amount", 0)]
    avg_r = sum(rs)/len(rs) if rs else 0
    median_r = sorted(rs)[len(rs)//2] if rs else 0
    return {
        "orders": len(order_reg.all()) if order_reg else 0,
        "fills": report.total_trades,
        "exits": report.total_trades,
        "wins": report.wins,
        "losses": report.losses,
        "breakevens": report.breakeven,
        "gross_pnl": round(report.gross_profit - report.gross_loss, 6),
        "net_pnl": round(report.net_profit, 6),
        "return": round(report.net_profit / report.starting_balance * 100, 6) if report.starting_balance else 0,
        "drawdown": round(report.max_drawdown, 6),
        "sharpe": round(report.sharpe, 6),
        "sortino": round(report.sortino, 6),
        "expectancy": round(report.expectancy, 6),
        "profit_factor": round(report.profit_factor, 6) if report.profit_factor != float("inf") else "inf",
        "avg_r": round(avg_r, 6),
        "median_r": round(median_r, 6),
        "ambiguous": ambiguous,
        "expirations": expired,
        "invalidations": invalidated,
        "filled_orders": filled,
        "trade_ids": [t.trade_id for t in sim.registry.all()],
        "order_ids": [o.order_id for o in order_reg.all()] if order_reg else [],
    }


def main():
    print("=== Gate A: Repeat 5000-bar on same snapshot ===")
    with open(RAW_PATH) as f:
        data = json.load(f)
    raw = data["raw"]
    print(f"Loaded snapshot: {len(raw)} bars, {data['symbol']} {data.get('timeframe', '1m')}")

    r1 = run_from_raw(raw)
    r2 = run_from_raw(raw)

    print("\nRun 1:", json.dumps(r1, indent=2))
    print("\nRun 2:", json.dumps(r2, indent=2))

    # Compare within tolerance 1e-6
    mismatches = []
    for k in r1:
        if k in ("trade_ids", "order_ids"):
            if r1[k] != r2[k]:
                mismatches.append(f"{k}: {r1[k]} != {r2[k]}")
        elif isinstance(r1[k], float):
            if abs(r1[k] - r2[k]) > 1e-6:
                mismatches.append(f"{k}: {r1[k]} != {r2[k]}")
        else:
            if r1[k] != r2[k]:
                mismatches.append(f"{k}: {r1[k]} != {r2[k]}")

    if mismatches:
        print("\n[FAIL] GATE A FAILED — Determinism mismatch:")
        for m in mismatches:
            print(f"  - {m}")
        raise SystemExit(1)
    else:
        print("\n[PASS] GATE A PASSED — All metrics match within 1e-6, trade/order IDs identical")
        print(f"  orders {r1['orders']}, fills {r1['fills']}, wins {r1['wins']}, losses {r1['losses']}, breakevens {r1['breakevens']}, net {r1['net_pnl']}")


if __name__ == "__main__":
    main()
