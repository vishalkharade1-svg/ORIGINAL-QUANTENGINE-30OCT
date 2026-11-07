"""
Real 5000-bar Delta historical baseline — Phase 9S §1

Uses HistoricalLoader.candles_paginated (real Delta API), not synthetic.
PAPER-only, never LIVE_EXECUTE.
Records all §1.1, §1.5 fields to docs/audit/baseline_9s_delta_5000.json/.md
"""

import json
import time
import subprocess
from pathlib import Path

from data.historical_loader import HistoricalLoader
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
from config.settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_JSON = BASE_DIR / "docs" / "audit" / "baseline_9s_delta_5000.json"
OUT_MD = BASE_DIR / "docs" / "audit" / "baseline_9s_delta_5000.md"


def main():
    symbol = settings.SYMBOLS[0] if settings.SYMBOLS else "BTCUSDT"
    timeframe = settings.TIMEFRAME
    requested = 5000

    print(f"=== Real Delta 5000-bar baseline ===")
    print(f"Symbol: {symbol}, Timeframe: {timeframe}, Requested: {requested}")

    loader = HistoricalLoader()
    t_fetch_start = time.time()

    # Verify API contract before fetching
    print(f"Fetching via HistoricalLoader.candles_paginated(symbol={symbol}, resolution={timeframe}, total_candles={requested})")
    try:
        history = loader.candles_paginated(symbol, resolution=timeframe, total_candles=requested)
    except Exception as e:
        print(f"FETCH FAILED: {e}")
        import traceback; traceback.print_exc()
        # Record failure
        result = {
            "error": str(e),
            "requested_bars": requested,
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "Delta /v2/history/candles via HistoricalLoader.candles_paginated",
        }
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_JSON, "w") as f:
            json.dump(result, f, indent=2)
        return

    fetch_elapsed = time.time() - t_fetch_start

    # Data integrity
    result_list = history.get("result", []) if isinstance(history, dict) else []
    # HistoricalLoader returns {"result": [...]} where each entry is a candle dict with time/open/high/low/close/volume
    # But our loader.candles_paginated returns the raw history dict; we need to extract
    # In test_backtester.py, they do history["result"] then CandleBuilder.load_history
    raw = history.get("result", []) if isinstance(history, dict) else []
    received = len(raw)
    print(f"Received {received} raw candles in {fetch_elapsed:.1f}s")

    # Check for duplicates, missing, etc. via CandleBuilder
    builder = CandleBuilder(max_history=len(raw) or 1)
    # load_history expects list of dicts with time/open/high/low/close
    # The API returns time as seconds? Let's check
    if raw:
        print(f"Sample raw: {raw[0]}")
        # Ensure time field exists
        for c in raw[:3]:
            print(f"  time={c.get('time')} open={c.get('open')} high={c.get('high')} low={c.get('low')} close={c.get('close')}")

    # Use builder to get usable bars (handles duplicates, ordering)
    try:
        builder.load_history(list(reversed(raw)) if raw else [])
        candles = list(builder.history)
        usable = len(candles)
        print(f"Usable bars after CandleBuilder: {usable}")
    except Exception as e:
        print(f"Builder failed: {e}")
        import traceback; traceback.print_exc()
        candles = []
        usable = 0

    # Timestamp range
    if candles:
        start_ts = candles[0].timestamp
        end_ts = candles[-1].timestamp
        # Check duplicate/missing
        timestamps = [c.timestamp for c in candles]
        dup = len(timestamps) - len(set(timestamps))
        # Missing buckets: expected n bars * 60s, but we check gaps > 60s
        missing = 0
        gaps = []
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i-1]
            if gap != 60:  # 1m
                missing += 1
                gaps.append((timestamps[i-1], timestamps[i], gap))
        print(f"Start: {start_ts} ({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(start_ts))})")
        print(f"End: {end_ts} ({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(end_ts))})")
        print(f"Duplicates: {dup}, Missing buckets: {missing}")
        if gaps[:3]:
            print(f"Sample gaps: {gaps[:3]}")
    else:
        start_ts = end_ts = 0
        dup = missing = 0

    # Trading configuration (explicit, from risk_settings)
    try:
        version = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()[:7]
    except Exception:
        version = "unknown"

    # Costs: use repository authoritative config (explicit, not invented)
    # risk_settings has 0.0 for all three — we document as explicit zero-cost
    fees = {
        "commission_per_trade": risk_settings.COMMISSION_PER_TRADE,
        "commission_rate": risk_settings.COMMISSION_RATE,
        "slippage_bps": risk_settings.SLIPPAGE_BPS,
    }
    # Per §1.3, if realistic non-zero is required but not in config, we STOP and report missing
    # Currently config is 0, so we will run with 0 and document as explicit zero-cost, not misreported as live
    print(f"Costs: {fees} — explicit from risk_settings, not invented")

    # Fill model (from risk_settings)
    fill_model = {
        "entry_mode": risk_settings.ENTRY_MODE,
        "next_bar_open": "BREAKOUT_CONTINUATION fills at next bar open",
        "sl_tp": "conservative SL-first, ambiguous flagged",
        "expiry": f"eligible_from_bar + {risk_settings.MAX_WAIT_BARS}",
        "invalidation": "structural stop breach",
        "fees": fees,
        "slippage": f"{risk_settings.SLIPPAGE_BPS} bps",
    }

    if not candles:
        print("No usable candles — cannot run backtest")
        result = {
            "requested_bars": requested,
            "received_bars": received,
            "usable_bars": usable,
            "duplicate_bars": dup,
            "missing_bars": missing,
            "timestamp_range": [start_ts, end_ts] if candles else [0,0],
            "timeframe": timeframe,
            "symbol": symbol,
            "source": "Delta /v2/history/candles via HistoricalLoader.candles_paginated",
            "api_errors": [],
            "gaps": gaps[:5] if 'gaps' in locals() else [],
            "error": "no usable candles",
        }
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_JSON, "w") as f:
            json.dump(result, f, indent=2)
        return

    # Run production pipeline via Backtester (same as live PAPER)
    market = MarketState(symbol=symbol)
    context = PipelineContext()
    context.market = market
    bus = EventBus()
    pipeline = InstitutionalPipeline(context)
    pipeline.subscribe(bus)
    sim = TradeSimulator()
    acc = Account(starting_balance=risk_settings.STARTING_BALANCE)
    bt = Backtester(pipeline=pipeline, event_bus=bus, simulator=sim, account=acc)

    t0 = time.time()
    bt.run(candles)
    elapsed = time.time() - t0

    report = PerformanceAnalytics.analyze(acc, sim.registry)

    # Order lifecycle counts
    order_reg = context.order_registry
    filled = len([o for o in order_reg.all() if o.status == "FILLED"]) if order_reg else 0
    expired = len(order_reg.expired()) if order_reg else 0
    invalidated = len(order_reg.invalidated()) if order_reg else 0
    rejected = len(order_reg.rejected()) if order_reg else 0

    ambiguous = len([t for t in sim.registry.all() if getattr(t, "ambiguous", False)])
    # R stats
    rs = [t.pnl / t.risk_amount if getattr(t, "risk_amount", 0) else 0 for t in sim.registry.all() if getattr(t, "risk_amount", 0)]
    avg_r = sum(rs)/len(rs) if rs else 0
    median_r = sorted(rs)[len(rs)//2] if rs else 0

    result = {
        "dataset": {"n": len(candles), "symbol": symbol, "timeframe": timeframe, "start_ts": start_ts, "end_ts": end_ts, "start_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(start_ts)), "end_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(end_ts))},
        "requested_bars": requested,
        "received_bars": received,
        "usable_bars": usable,
        "duplicate_bars": dup,
        "missing_bars": missing,
        "timestamp_range": [start_ts, end_ts],
        "timeframe": timeframe,
        "symbol": symbol,
        "source": "Delta /v2/history/candles via HistoricalLoader.candles_paginated",
        "api_errors": [],
        "gaps": gaps[:5] if 'gaps' in locals() else [],
        "configuration": {
            "starting_balance": risk_settings.STARTING_BALANCE,
            "risk_per_trade": risk_settings.RISK_PER_TRADE,
            "max_allocation": risk_settings.MAX_ALLOCATION_PER_TRADE,
            "leverage": risk_settings.LEVERAGE,
            "entry_mode": risk_settings.ENTRY_MODE,
            "max_wait_bars": risk_settings.MAX_WAIT_BARS,
            "entry_delay_bars": risk_settings.ENTRY_DELAY_BARS,
        },
        "code_commit": version,
        "dataset_identity": f"{symbol}-{timeframe}-{start_ts}-{end_ts}-{usable}",
        "fees": fees,
        "fill_model": fill_model,
        "n_bars": len(candles),
        "elapsed_seconds": round(elapsed, 3),
        "setups": len(context.trade_setups.all()) if context.trade_setups else 0,
        "orders": len(order_reg.all()) if order_reg else 0,
        "fills": report.total_trades,
        "expirations": expired,
        "invalidations": invalidated,
        "rejected_orders": rejected,
        "filled_orders": filled,
        "wins": report.wins,
        "losses": report.losses,
        "breakevens": report.breakeven,
        "gross_pnl": round(report.gross_profit - report.gross_loss, 2),
        "gross_profit": round(report.gross_profit, 2),
        "gross_loss": round(report.gross_loss, 2),
        "commissions": round(sum(getattr(t, "commission", 0) for t in sim.registry.all()), 2),
        "slippage": round(sum(getattr(t, "slippage", 0) for t in sim.registry.all()), 2),
        "net_pnl": round(report.net_profit, 2),
        "return_pct": round(report.net_profit / report.starting_balance * 100, 4) if report.starting_balance else 0,
        "max_drawdown": round(report.max_drawdown, 2),
        "max_drawdown_pct": round(report.max_drawdown_percent, 4),
        "max_drawdown_duration": None,
        "sharpe": round(report.sharpe, 4),
        "sortino": round(report.sortino, 4),
        "expectancy": round(report.expectancy, 4),
        "profit_factor": round(report.profit_factor, 4) if report.profit_factor != float("inf") else "inf",
        "win_rate": round(report.win_rate, 2),
        "loss_rate": round(100 - report.win_rate - (report.breakeven/report.total_trades*100 if report.total_trades else 0), 2),
        "breakeven_rate": round(report.breakeven/report.total_trades*100, 2) if report.total_trades else 0,
        "ambiguous_trades": ambiguous,
        "ambiguous_pct": round(ambiguous/report.total_trades*100, 2) if report.total_trades else 0,
        "average_R": round(avg_r, 4),
        "median_R": round(median_r, 4),
        "total_exposure": round(sum(getattr(t, "position_value", 0) for t in sim.registry.all()), 2),
        "maximum_exposure": round(max([getattr(t, "position_value", 0) for t in sim.registry.all()], default=0), 2),
        "reproducibility": {"dataset": f"{symbol}-{timeframe}-{start_ts}-{end_ts}", "config": "risk_settings as above", "code_version": version, "seed": "N/A (deterministic pipeline, no random seed)"},
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nWritten to {OUT_JSON}")
    print(json.dumps(result, indent=2))

    # Gate A: Save raw snapshot for determinism verification (exact same dataset)
    raw_out = BASE_DIR / "docs" / "audit" / "baseline_9s_delta_5000_raw.json"
    with open(raw_out, "w") as f:
        json.dump({"symbol": symbol, "timeframe": timeframe, "requested": requested, "received": received, "raw": raw}, f)
    print(f"Raw snapshot written to {raw_out} ({len(raw)} bars)")

    # Also write markdown
    md = f"""# Real Delta 5000-Bar Baseline

> Generated {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}, code {version}

## Dataset
- Symbol: {symbol}, Timeframe: {timeframe}, Source: Delta /v2/history/candles
- Requested: {requested}, Received: {received}, Usable: {usable}, Duplicates: {dup}, Missing: {missing}
- Range: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(start_ts))} to {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(end_ts))} ({start_ts} to {end_ts})

## Configuration
- STARTING_BALANCE={risk_settings.STARTING_BALANCE}, RISK_PER_TRADE={risk_settings.RISK_PER_TRADE}, MAX_ALLOCATION={risk_settings.MAX_ALLOCATION_PER_TRADE}, LEVERAGE={risk_settings.LEVERAGE}
- ENTRY_MODE={risk_settings.ENTRY_MODE}, MAX_WAIT_BARS={risk_settings.MAX_WAIT_BARS}, ENTRY_DELAY_BARS={risk_settings.ENTRY_DELAY_BARS}
- Fees: {fees} -- **explicit zero-cost** (from risk_settings, not invented; real Delta taker fee would be ~0.02% -- not configured, so 0 is documented)

## Fill Model
- {fill_model}

## Results
- n_bars: {len(candles)}, setups: {result['setups']}, orders: {result['orders']}, fills: {report.total_trades}, expirations: {expired}, invalidations: {invalidated}, rejected: {rejected}
- wins: {report.wins}, losses: {report.losses}, breakevens: {report.breakeven}, win_rate: {report.win_rate:.2f}%, breakeven_rate: {result['breakeven_rate']:.2f}%
- gross_profit: {report.gross_profit:.2f}, gross_loss: {report.gross_loss:.2f}, commissions: {result['commissions']}, slippage: {result['slippage']}, **net_pnl: {report.net_profit:.2f}**, return: {result['return_pct']:.4f}%
- max_drawdown: {report.max_drawdown:.2f} ({report.max_drawdown_percent:.4f}%), sharpe: {report.sharpe:.4f}, sortino: {report.sortino:.4f}, expectancy: {report.expectancy:.4f}, PF: {result['profit_factor']}
- ambiguous: {ambiguous} ({result['ambiguous_pct']:.2f}%), avg_R: {avg_r:.4f}, median_R: {median_r:.4f}
- total_exposure: {result['total_exposure']}, max_exposure: {result['maximum_exposure']}

## Reproducibility
- Dataset identity: {result['dataset_identity']}
- Second run must match all above counts and pnl within 1e-6 (deterministic pipeline).

## Notes
- Post-9Q Wilder ATR, causal displacement, canonical accounting, breakeven, timestamp canonical, etc. -- **0 trades is valid if the funnel is selective**; do not optimize strategy to look better.
- Real Delta 5000-bar baseline is the **final 9S proof** that the engine measures reality correctly.
"""
    with open(OUT_MD, "w") as f:
        f.write(md)
    print(f"Written to {OUT_MD}")


if __name__ == "__main__":
    main()
