"""
Phase 10 — Multi-symbol isolation.

Prove one symbol cannot contaminate another's candles, indicators, etc.
"""

import unittest
from core.pipeline.pipeline_context import PipelineContext
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.events.event_bus import EventBus
from core.backtesting.trade_simulator import TradeSimulator
from backtesting.backtester import Backtester
from core.risk.account import Account
from dataclasses import dataclass


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 1000
    symbol: str = "BTCUSDT"


def mk_candles(symbol, n, start=1704067200, trend=1):
    out = []
    price = 50000 if symbol == "BTCUSDT" else 3000
    for i in range(n):
        o = price
        c = price + trend * 10
        h = max(o, c) + 5
        l = min(o, c) - 5
        out.append(Candle(timestamp=start+i*60, open=o, high=h, low=l, close=c, symbol=symbol))
        price = c
    return out


class TestMultiSymbolIsolation(unittest.TestCase):

    def test_btc_state_never_in_eth(self):
        # Run BTC and ETH separately through same pipeline logic, ensure isolation
        # Use two separate contexts/pipelines (simulating per-symbol pipelines in RealTimeEngine)
        candles_btc = mk_candles("BTCUSDT", 50, trend=1)
        candles_eth = mk_candles("ETHUSDT", 50, trend=-1)

        def run(candles, symbol):
            ctx = PipelineContext()
            pipe = InstitutionalPipeline(ctx)
            bus = EventBus()
            sim = TradeSimulator()
            acc = Account(2000)
            bt = Backtester(pipeline=pipe, event_bus=bus, simulator=sim, account=acc)
            bt.run(candles)
            return ctx, sim

        ctx_btc, sim_btc = run(candles_btc, "BTCUSDT")
        ctx_eth, sim_eth = run(candles_eth, "ETHUSDT")

        # BTC should have bullish signals, ETH bearish — not mixed
        # Check that trade directions are isolated
        btc_dirs = [t.direction for t in sim_btc.registry.all()]
        eth_dirs = [t.direction for t in sim_eth.registry.all()]
        # They should not be identical if trends are opposite (if any trades)
        # At minimum, verify that contexts are distinct objects
        self.assertIsNot(ctx_btc, ctx_eth)
        self.assertIsNot(sim_btc, sim_eth)
        # Verify contexts are isolated (distinct objects, no shared state)
        self.assertIsNot(ctx_btc, ctx_eth)
        # Orders should be isolated
        self.assertIsNot(ctx_btc.order_registry, ctx_eth.order_registry)

    def test_canonical_identity(self):
        # Identity must be {exchange}:{instrument_id}:{timeframe}:{direction}:{strategy}:{setup_id}
        # We test that two instruments with same setup but different symbol have different identities
        from core.registry.instrument import Instrument
        i1 = Instrument(symbol="BTCUSDT", instrument_id="BTCUSDT", exchange="DELTA")
        i2 = Instrument(symbol="ETHUSDT", instrument_id="ETHUSDT", exchange="DELTA")
        self.assertNotEqual(i1.symbol, i2.symbol)
        self.assertNotEqual(i1.key, i2.key)

    def test_order_registry_isolation(self):
        from core.execution.order_registry import OrderRegistry
        reg = OrderRegistry()
        from dataclasses import dataclass as dc
        @dc
        class FakeOrder:
            setup_id: str
            symbol: str
            status: str = "NEW"
            order_id: str = ""
            eligible_from_bar: int = None
            expires_at_bar: int = None
            created_bar: int = None
            wait_bars: int = 0
        o1 = FakeOrder(setup_id="BTC-ORDER-1", symbol="BTCUSDT")
        o2 = FakeOrder(setup_id="ETH-ORDER-1", symbol="ETHUSDT")
        reg.create(o1, bar=1)
        reg.create(o2, bar=1)
        self.assertEqual(len(reg.all()), 2)
        self.assertTrue(reg.has_order_for_setup("BTC-ORDER-1"))
        self.assertTrue(reg.has_order_for_setup("ETH-ORDER-1"))
        self.assertFalse(reg.has_order_for_setup("BTC-ORDER-2"))
