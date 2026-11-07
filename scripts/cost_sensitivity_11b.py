"""
Phase 11B-J — Cost-sensitivity runner (RESEARCH ONLY).

Re-runs the frozen Gate A 5000-bar snapshot under four
controlled cost scenarios WITHOUT touching production
configuration (config/risk_settings.py stays zero-cost)
and WITHOUT changing strategy logic, entries, or exits.

Cost model (production code path, unchanged):
    commission = COMMISSION_PER_TRADE
               + position_value * COMMISSION_RATE
    slippage   = 2 * position_value * SLIPPAGE_BPS / 10000

Scenarios (assumptions LABELED, grounded Sept 2026):
  A zero      canonical baseline (prod config as-is)
  B small     maker-like 0.02% + 1 bp slippage
  C moderate  taker-like 0.05% + 2 bp slippage
  D adverse   0.059% (0.05% + 18% GST, India taker
              all-in) + 5 bp slippage

Fee grounding: delta.exchange/fees and reviews, Sept
2026 -- futures maker 0.02%, taker 0.05%, +18% GST on
fees for Indian users. Slippage figures are MODELED
assumptions (thin 1m books), not exchange quotes.

Usage:
    python -m scripts.cost_sensitivity_11b      # all scenarios
    python -m scripts.cost_sensitivity_11b B    # one scenario

Stdout is JSON (captured into evidence). No network, no
LIVE, no orders placed -- pure backtest replay.
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import risk_settings
from core.analytics.performance import PerformanceAnalytics
from core.backtesting.trade_simulator import TradeSimulator
from core.events.event_bus import EventBus
from core.market_state import MarketState
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext
from core.risk.account import Account
from data.candle_builder import CandleBuilder
from backtesting.backtester import Backtester
from scripts.verify_gate_a import RAW_PATH

SCENARIOS = {
    "A_zero": {
        "label": "canonical zero-cost baseline",
        "COMMISSION_PER_TRADE": 0.0,
        "COMMISSION_RATE": 0.0,
        "SLIPPAGE_BPS": 0.0,
    },
    "B_small": {
        "label": "maker-like 0.02% + 1bp slippage (assumed)",
        "COMMISSION_PER_TRADE": 0.0,
        "COMMISSION_RATE": 0.0002,
        "SLIPPAGE_BPS": 1.0,
    },
    "C_moderate": {
        "label": "taker-like 0.05% + 2bp slippage (assumed)",
        "COMMISSION_PER_TRADE": 0.0,
        "COMMISSION_RATE": 0.0005,
        "SLIPPAGE_BPS": 2.0,
    },
    "D_adverse": {
        "label": "0.059% all-in India taker + 5bp slippage (assumed)",
        "COMMISSION_PER_TRADE": 0.0,
        "COMMISSION_RATE": 0.00059,
        "SLIPPAGE_BPS": 5.0,
    },
}


def run_scenario(raw, key):
    spec = SCENARIOS[key]
    saved = (
        risk_settings.COMMISSION_PER_TRADE,
        risk_settings.COMMISSION_RATE,
        risk_settings.SLIPPAGE_BPS,
    )
    risk_settings.COMMISSION_PER_TRADE = spec["COMMISSION_PER_TRADE"]
    risk_settings.COMMISSION_RATE = spec["COMMISSION_RATE"]
    risk_settings.SLIPPAGE_BPS = spec["SLIPPAGE_BPS"]
    try:
        # Same construction as scripts/verify_gate_a.py
        # (fresh pipeline/sim/account per run), plus cost
        # attribution from the booked trades.
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
        acc = Account(
            starting_balance=risk_settings.STARTING_BALANCE
        )
        bt = Backtester(
            pipeline=pipeline,
            event_bus=bus,
            simulator=sim,
            account=acc,
        )
        bt.run(candles)
        report = PerformanceAnalytics.analyze(acc, sim.registry)
        trades = sim.registry.all()
        result = {
            "orders": len(ctx.order_registry.all())
            if ctx.order_registry
            else 0,
            "fills": report.total_trades,
            "wins": report.wins,
            "losses": report.losses,
            "breakevens": report.breakeven,
            "gross_pnl": round(
                report.gross_profit - report.gross_loss, 6
            ),
            "total_commission": round(
                sum(t.commission for t in trades), 6
            ),
            "total_slippage": round(
                sum(t.slippage for t in trades), 6
            ),
            "net_pnl": round(report.net_profit, 6),
            "final_balance": round(report.final_balance, 6),
            "return": round(
                report.net_profit / report.starting_balance * 100, 6
            )
            if report.starting_balance
            else 0,
            "drawdown": round(report.max_drawdown, 6),
            "sharpe": round(report.sharpe, 6),
            "sortino": round(report.sortino, 6),
            "expectancy": round(report.expectancy, 6),
            "profit_factor": round(report.profit_factor, 6)
            if report.profit_factor != float("inf")
            else "inf",
        }
    finally:
        (
            risk_settings.COMMISSION_PER_TRADE,
            risk_settings.COMMISSION_RATE,
            risk_settings.SLIPPAGE_BPS,
        ) = saved

    # Re-derive cost attribution from the booked trades.
    # run_from_raw returns aggregates; totals below come
    # from the same deterministic run shape (fills/wins).
    result["scenario"] = key
    result["assumption"] = spec["label"]
    result["cost_inputs"] = {
        k: spec[k]
        for k in (
            "COMMISSION_PER_TRADE",
            "COMMISSION_RATE",
            "SLIPPAGE_BPS",
        )
    }
    return result


def main():
    wanted = sys.argv[1:] or sorted(SCENARIOS)
    for key in wanted:
        if key not in SCENARIOS:
            raise SystemExit(f"unknown scenario {key!r}")

    with open(RAW_PATH) as handle:
        data = json.load(handle)
    raw = data["raw"]

    output = {
        "dataset": {
            "bars": len(raw),
            "symbol": data.get("symbol"),
            "timeframe": data.get("timeframe", "1m"),
        },
        "frozen_baseline": {
            "entry_mode": "BREAKOUT_CONTINUATION",
            "starting_balance": 2000,
            "risk_per_trade": 0.01,
            "max_allocation": 500,
            "leverage": 10,
            "max_wait_bars": 30,
            "entry_delay_bars": 1,
        },
        "scenarios": {},
    }

    for key in wanted:
        output["scenarios"][key] = run_scenario(raw, key)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
