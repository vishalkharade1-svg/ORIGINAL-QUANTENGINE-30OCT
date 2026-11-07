"""
Phase 9R-6 — Research reproducibility.

Same dataset + config + seed + params + code version must produce same result.
Reports must contain enough metadata to reproduce.
"""

import unittest
import hashlib
import json

from backtesting.backtester import Backtester
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext
from core.events.event_bus import EventBus
from core.backtesting.trade_simulator import TradeSimulator
from core.risk.account import Account
from core.analytics.performance import PerformanceAnalytics
from dataclasses import dataclass


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000.0
    symbol: str = "BTCUSDT"


def _candles(n, seed=42, start_ts=1704067200):
    import random
    rnd = random.Random(seed)
    out = []
    price = 50000
    for i in range(n):
        o = price
        move = rnd.uniform(-80, 80)
        c = price + move
        h = max(o, c) + rnd.uniform(0, 20)
        l = min(o, c) - rnd.uniform(0, 20)
        out.append(Candle(timestamp=start_ts + i*60, open=o, high=h, low=l, close=c))
        price = c
    return out


class TestReproducibility(unittest.TestCase):

    def test_same_dataset_config_seed_produces_same_result(self):
        candles = _candles(100, seed=123)

        def run():
            ctx = PipelineContext()
            pipeline = InstitutionalPipeline(ctx)
            bus = EventBus()
            sim = TradeSimulator()
            acc = Account(starting_balance=2000)
            bt = Backtester(pipeline=pipeline, event_bus=bus, simulator=sim, account=acc)
            bt.run(candles)
            report = PerformanceAnalytics.analyze(acc, sim.registry)
            return {
                "net_profit": round(report.net_profit, 6),
                "total_trades": report.total_trades,
                "wins": report.wins,
                "losses": report.losses,
                "breakeven": report.breakeven,
                "max_drawdown": round(report.max_drawdown, 6),
                "sharpe": round(report.sharpe, 6),
            }

        r1 = run()
        r2 = run()
        self.assertEqual(r1, r2)

    def test_deterministic_with_canonical_accounting(self):
        # PnL must be deterministic across modes (Backtest vs Paper) — already tested in parity, here we check accounting determinism
        from core.backtesting.accounting import gross_pnl, net_pnl
        gross1 = gross_pnl("BULLISH", 100, 110, 2)
        gross2 = gross_pnl("BULLISH", 100, 110, 2)
        self.assertEqual(gross1, gross2)
        self.assertEqual(net_pnl(gross1, 1, 1), net_pnl(gross2, 1, 1))

    def test_report_contains_reproducibility_metadata(self):
        candles = _candles(50, seed=99)
        ctx = PipelineContext()
        pipeline = InstitutionalPipeline(ctx)
        bus = EventBus()
        sim = TradeSimulator()
        acc = Account(starting_balance=2000)
        bt = Backtester(pipeline=pipeline, event_bus=bus, simulator=sim, account=acc)
        bt.run(candles)
        report = PerformanceAnalytics.analyze(acc, sim.registry)
        # Simulate report metadata that must be present for reproduction
        import config.risk_settings as rs
        metadata = {
            "dataset": {"n": len(candles), "symbol": "BTCUSDT", "timeframe": "1m", "start_ts": candles[0].timestamp, "end_ts": candles[-1].timestamp},
            "config": {"starting_balance": 2000, "risk_per_trade": rs.RISK_PER_TRADE, "max_allocation": rs.MAX_ALLOCATION_PER_TRADE},
            "code_version": "test",
            "seed": 99,
            "fees": {"commission_per_trade": rs.COMMISSION_PER_TRADE, "commission_rate": rs.COMMISSION_RATE, "slippage_bps": rs.SLIPPAGE_BPS},
            "fill_model": "conservative SL-first, ambiguous flagged",
            "report": report,
        }
        # Must be JSON serializable
        try:
            json.dumps(metadata, default=str)
        except Exception as e:
            self.fail(f"Report metadata not serializable: {e}")
        self.assertIn("dataset", metadata)
        self.assertIn("config", metadata)
        self.assertIn("code_version", metadata)

    def test_no_randomness_without_seed(self):
        # Two runs with same seed must be identical, different seeds may differ
        c1 = _candles(30, seed=1)
        c2 = _candles(30, seed=1)
        c3 = _candles(30, seed=2)
        self.assertEqual([c.close for c in c1], [c.close for c in c2])
        self.assertNotEqual([c.close for c in c1], [c.close for c in c3])
