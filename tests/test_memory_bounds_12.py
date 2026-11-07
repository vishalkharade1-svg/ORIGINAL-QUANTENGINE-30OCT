"""
====================================================

QuantEngine

Phase 12 -- memory / long-run stability.

Proves (stdlib only, synthetic candles):

  1. the event dispatcher is explicitly bounded:
     overflow evicts oldest-first (deterministic FIFO)
     and counts every eviction (never silent);
  2. normal bus operation never evicts anything;
  3. the indicator cache key set never grows past the
     registered indicator names over a sustained run;
  4. an extended full-pipeline soak keeps engine state
     bounded (fractal memo cap, drained bus, bounded
     order registry) while remaining fully deterministic
     across two identical runs.

====================================================
"""

import unittest

from core.events.event_bus import EventBus
from core.events.event_dispatcher import EventDispatcher

from tests.test_pipeline_regressions import make_candles


class TestDispatcherBound(unittest.TestCase):

    def test_overflow_evicts_oldest_and_counts(self):
        dispatcher = EventDispatcher(maxlen=4)
        for index in range(6):
            dispatcher.push(index)
        self.assertEqual(len(dispatcher), 4)
        self.assertEqual(dispatcher.dropped, 2)
        self.assertEqual(
            [dispatcher.pop() for _ in range(4)],
            [2, 3, 4, 5])
        self.assertEqual(dispatcher.drain_dropped(), 2)
        self.assertEqual(dispatcher.dropped, 0)

    def test_normal_operation_never_evicts(self):
        bus = EventBus()
        seen = []
        bus.subscribe("CANDLE", seen.append)

        class Event:
            def __init__(self, index):
                self.event_type = "CANDLE"
                self.index = index

        for index in range(500):
            bus.publish(Event(index))

        self.assertEqual(len(seen), 500)
        self.assertEqual(
            [event.index for event in seen],
            list(range(500)))
        self.assertEqual(bus._dispatcher.dropped, 0)
        self.assertEqual(len(bus._dispatcher), 0)


def full_pipeline_run(candles):
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
    backtester.run(candles)
    return backtester, pipeline, bus


class TestCacheStability(unittest.TestCase):

    def test_indicator_keys_never_grow(self):
        candles = list(make_candles(n=150))
        backtester, pipeline, _ = full_pipeline_run(candles)

        registered = {item.name
                      for item in pipeline.indicators.indicators}
        self.assertEqual(len(registered), 6)
        self.assertEqual(set(backtester.pipeline.context
                             .indicators.data.keys()),
                         registered)

        bars = len(list(pipeline.context.candles))
        for name, series in (pipeline.context.indicators
                             .data.items()):
            self.assertLessEqual(len(series), bars)


class TestBoundedSoak(unittest.TestCase):

    def test_extended_run_stays_bounded_and_deterministic(self):
        candles = list(make_candles(n=1500))

        first, pipe_one, bus_one = full_pipeline_run(candles)
        second, _, _ = full_pipeline_run(candles)

        # Deterministic across identical runs.
        self.assertEqual(
            first.account.balance, second.account.balance)
        self.assertEqual(
            first.simulator.registry.count(),
            second.simulator.registry.count())

        # Bounded engine state after 1500 candles.
        swing_engine = None
        for engine in pipe_one.engines:
            if type(engine).__name__ == "SwingEngine":
                swing_engine = engine
        self.assertIsNotNone(swing_engine)
        self.assertLessEqual(swing_engine.cache_size(), 5000)

        registry = pipe_one.context.order_registry
        self.assertLessEqual(len(registry.all()),
                             len(candles))

        # Bus fully drained, nothing evicted.
        self.assertEqual(len(bus_one._dispatcher), 0)
        self.assertEqual(bus_one._dispatcher.dropped, 0)


if __name__ == "__main__":
    unittest.main()
