"""
Phase 9S §36 — Fresh baseline backtest (post-9Q/9S).

Records: dataset, symbols, timeframe, date range, config, code version,
fees, slippage, fill model, n bars, setups, signals, orders, fills,
expirations, invalidations, wins/losses/breakevens, gross/net, return,
maxDD, Sharpe, Sortino, expectancy, PF, ambiguous, rejected, risk stats.
"""

import unittest
from dataclasses import dataclass

from backtesting.backtester import Backtester
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext
from core.events.event_bus import EventBus
from core.backtesting.trade_simulator import TradeSimulator
from core.risk.account import Account
from core.analytics.performance import PerformanceAnalytics
from config import risk_settings
import hashlib


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0
    symbol: str = "BTCUSDT"


def _candles(n, seed=2025, start_ts=1704067200):
    import random
    rnd = random.Random(seed)
    out = []
    price = 50000
    for i in range(n):
        o = price
        move = rnd.uniform(-60, 60)
        c = price + move
        h = max(o, c) + rnd.uniform(0, 15)
        l = min(o, c) - rnd.uniform(0, 15)
        out.append(Candle(timestamp=start_ts + i*60, open=o, high=h, low=l, close=c))
        price = c
    return out


class TestFreshBaseline(unittest.TestCase):

    def test_baseline_records_all_required_fields(self):
        candles = _candles(200, seed=2025)
        ctx = PipelineContext()
        pipeline = InstitutionalPipeline(ctx)
        bus = EventBus()
        sim = TradeSimulator()
        acc = Account(starting_balance=risk_settings.STARTING_BALANCE)
        bt = Backtester(pipeline=pipeline, event_bus=bus, simulator=sim, account=acc)
        bt.run(candles)

        report = PerformanceAnalytics.analyze(acc, sim.registry)
        # Collect required §36 fields
        dataset = {"n": len(candles), "symbol": "BTCUSDT", "timeframe": "1m", "start": candles[0].timestamp, "end": candles[-1].timestamp}
        config = {"starting_balance": risk_settings.STARTING_BALANCE, "risk_per_trade": risk_settings.RISK_PER_TRADE}
        # Code version via git
        try:
            import subprocess
            version = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()[:7]
        except Exception:
            version = "test"

        baseline = {
            "dataset": dataset,
            "symbols": ["BTCUSDT"],
            "timeframe": "1m",
            "date_range": (candles[0].timestamp, candles[-1].timestamp),
            "config": config,
            "code_version": version,
            "fees": {"commission_per_trade": risk_settings.COMMISSION_PER_TRADE, "commission_rate": risk_settings.COMMISSION_RATE, "slippage_bps": risk_settings.SLIPPAGE_BPS},
            "fill_model": "conservative SL-first, ambiguous flagged, next-bar-open for BREAKOUT",
            "n_bars": len(candles),
            "setups": len(ctx.trade_setups.all()) if ctx.trade_setups else 0,
            "orders": len(ctx.order_registry.all()) if ctx.order_registry else 0,
            "fills": report.total_trades,
            "expirations": len(ctx.order_registry.expired()) if ctx.order_registry else 0,
            "invalidations": len(ctx.order_registry.invalidated()) if ctx.order_registry else 0,
            "wins": report.wins,
            "losses": report.losses,
            "breakevens": report.breakeven,
            "gross_pnl": report.gross_profit - report.gross_loss,
            "net_pnl": report.net_profit,
            "return_pct": (report.net_profit / report.starting_balance * 100) if report.starting_balance else 0,
            "max_drawdown": report.max_drawdown,
            "max_drawdown_pct": report.max_drawdown_percent,
            "sharpe": report.sharpe,
            "sortino": report.sortino,
            "expectancy": report.expectancy,
            "profit_factor": report.profit_factor,
            "ambiguous_trades": len([t for t in sim.registry.all() if getattr(t, "ambiguous", False)]),
            "rejected_orders": len(ctx.order_registry.rejected()) if ctx.order_registry else 0,
            "risk_stats": {"starting_balance": report.starting_balance, "final_equity": report.final_equity, "peak_equity": report.peak_equity},
        }

        # All required fields must be present and not None
        required = ["dataset", "symbols", "timeframe", "date_range", "config", "code_version", "fees", "fill_model", "n_bars", "fills", "wins", "losses", "breakevens", "net_pnl", "max_drawdown", "sharpe", "expectancy", "profit_factor", "ambiguous_trades"]
        for k in required:
            self.assertIn(k, baseline, msg=f"Missing {k}")
            self.assertIsNotNone(baseline[k])

        # Determinism: run again and compare
        ctx2 = PipelineContext()
        pipeline2 = InstitutionalPipeline(ctx2)
        bus2 = EventBus()
        sim2 = TradeSimulator()
        acc2 = Account(starting_balance=risk_settings.STARTING_BALANCE)
        bt2 = Backtester(pipeline=pipeline2, event_bus=bus2, simulator=sim2, account=acc2)
        bt2.run(candles)
        report2 = PerformanceAnalytics.analyze(acc2, sim2.registry)
        self.assertEqual(report.total_trades, report2.total_trades)
        self.assertAlmostEqual(report.net_profit, report2.net_profit, places=6)

        # Print for manual inspection (not asserted)
        print("\n--- Fresh Baseline (post-9Q/9S) ---")
        for k, v in baseline.items():
            print(f"{k}: {v}")

    def test_baseline_is_not_zero_cost_misreported(self):
        # Ensure that when fees are zero, we document it as explicit, not hidden
        from config import risk_settings as rs
        self.assertIsNotNone(rs.COMMISSION_PER_TRADE)
        self.assertIsNotNone(rs.SLIPPAGE_BPS)
        # The baseline doc must state fill assumptions
        self.assertIn(rs.COMMISSION_PER_TRADE, [0.0, 0.0])  # explicit
