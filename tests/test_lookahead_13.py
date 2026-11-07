"""
====================================================

QuantEngine

Phase 13 -- multi-boundary lookahead adversarial test.

Dataset A: deterministic synthetic history through the
real pipeline + backtester.
Dataset B_k: byte-identical through boundary T_k, wildly
divergent only AFTER T_k (rally / crash / flat futures).

For every boundary, all decision artifacts dated
strictly before T_k must be byte-identical across A and
B_k: created orders (ids + economics), fills (ids +
prices + PnL), and their deterministic serialization.
Anything earlier changing is a CAUSALITY FAILURE.

Stdlib only. No network. No strategy change (the
frozen BREAKOUT production default runs as-is).

====================================================
"""

import json
import unittest

from tests.test_pipeline_regressions import make_candles


def run_history(candles):
    from core.market_state import MarketState
    from core.pipeline.pipeline_context import PipelineContext
    from core.pipeline.institutional_pipeline import (
        InstitutionalPipeline,
    )
    from core.events.event_bus import EventBus
    from core.backtesting.trade_simulator import TradeSimulator
    from backtesting.backtester import Backtester

    context = PipelineContext()
    context.market = MarketState(symbol="TEST", timeframe="1m")
    pipeline = InstitutionalPipeline(context)
    bus = EventBus()
    pipeline.subscribe(bus)
    simulator = TradeSimulator()
    backtester = Backtester(pipeline, bus, simulator)
    backtester.run(list(candles))
    return backtester, simulator, context


def snapshot_before(backtester, simulator, context, boundary):
    orders = sorted(
        (
            o.order_id,
            o.setup_id,
            o.direction,
            round(float(o.entry), 9),
            round(float(o.stop_loss), 9),
            round(float(o.take_profit), 9),
            getattr(o, "created_bar", None),
            o.status,
        )
        for o in context.order_registry.all()
        if (getattr(o, "created_bar", 10 ** 9) or 0) < boundary
    )
    fills = sorted(
        (
            t.trade_id,
            t.setup_id,
            t.direction,
            round(float(t.entry), 9),
            round(float(t.exit_price or 0.0), 9),
            round(float(t.pnl), 9),
            t.entry_time,
        )
        for t in simulator.registry.all()
        if (t.entry_time or 0) < boundary
    )
    return {"orders": orders, "fills": fills}


def serialize(snapshot):
    return json.dumps(snapshot, sort_keys=True, default=str)


class TestMultiBoundaryLookahead(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        base = list(make_candles(n=900, start_price=60000.0,
                                 seed=42))
        cls.base = base
        cls.futures = {
            "rally": list(make_candles(n=300, start_price=200000.0,
                                       seed=11)),
            "crash": list(make_candles(n=300, start_price=5000.0,
                                       seed=12)),
            "flat": list(make_candles(n=300, start_price=60000.0,
                                      seed=13)),
        }
        # Retimestamp futures to continue each boundary's
        # clock without overlap (strictly-after-T data).
        cls._ts = [c.timestamp for c in base]

    def _variant(self, boundary, future):
        tail = []
        step = 60
        start = self._ts[boundary - 1] + step
        for i, candle in enumerate(self.futures[future]):
            candle.timestamp = start + i * step
            tail.append(candle)
        return list(self.base[:boundary]) + tail

    def _check_boundary(self, boundary):
        ref_bt, ref_sim, ref_ctx = run_history(self.base)
        ref = snapshot_before(ref_bt, ref_sim, ref_ctx, boundary)
        ref_ser = serialize(ref)
        for name in ("rally", "crash", "flat"):
            with self.subTest(boundary=boundary, future=name):
                bt, sim, ctx = run_history(
                    self._variant(boundary, name))
                snap = snapshot_before(bt, sim, ctx, boundary)
                self.assertEqual(snap, ref)
                self.assertEqual(serialize(snap), ref_ser)

    def test_boundary_400(self):
        self._check_boundary(400)

    def test_boundary_600(self):
        self._check_boundary(600)

    def test_boundary_800(self):
        self._check_boundary(800)


if __name__ == "__main__":
    unittest.main()
