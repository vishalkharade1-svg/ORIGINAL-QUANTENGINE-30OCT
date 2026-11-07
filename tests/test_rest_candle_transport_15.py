"""REST polling candle transport (paper preview, offline).

Fake history + manual clock: proves closed-only causal delivery
(forming excluded, ordered, deduplicated, symbol-tagged),
bounded failure handling (on_down, no unbounded loops), and
resubscribe recovery — with zero network.
"""

from __future__ import annotations

import threading
import time
import unittest

from core.history.candle import Candle
from data.delta.rest_candle_transport import RestPollingCandleTransport


def bar(stamp, close=100.0):
    return Candle(timestamp=stamp, open=99.0, high=101.0, low=98.0,
                  close=close, volume=10.0, symbol="")


class FakeHistory:
    def __init__(self, bars=(), fail=0):
        self.bars = list(bars)
        self.fail = fail
        self.calls = 0

    def candles(self, symbol, resolution="1m", days=1):
        self.calls += 1
        if self.fail > 0:
            self.fail -= 1
            raise ConnectionError("down")
        return [Candle(timestamp=b.timestamp, open=b.open,
                       high=b.high, low=b.low, close=b.close,
                       volume=b.volume, symbol=b.symbol)
                for b in self.bars]


class Clock:
    def __init__(self, now):
        self.now = float(now)

    def __call__(self):
        return self.now


def wait_for(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class TestRestCandleTransport(unittest.TestCase):
    def test_closed_only_ordered_tagged(self):
        # Bars at 1000,1060,1180 with now=1200: 1000 and 1060 are
        # closed (T+60<=1200); 1180 is still forming (1240>1200).
        history = FakeHistory([bar(1000), bar(1060), bar(1180)])
        transport = RestPollingCandleTransport(
            timeframe="1m", history=history, clock=Clock(1200),
            poll_interval_seconds=5)
        seen, lock = [], threading.Lock()

        def on_candle(candle):
            with lock:
                seen.append(candle)

        transport.subscribe("BTCUSDT", on_candle, lambda: None)
        try:
            self.assertTrue(wait_for(lambda: len(seen) >= 2))
            time.sleep(0.3)  # extra polls must not duplicate
            with lock:
                stamps = [c.timestamp for c in seen]
            self.assertEqual(stamps, [1000, 1060])
            for candle in seen:
                self.assertEqual(candle.symbol, "BTCUSDT")
                self.assertTrue(candle.closed)
        finally:
            transport.close()

    def test_forming_bar_emitted_after_close(self):
        history = FakeHistory([bar(1000), bar(1060)])
        clock = Clock(1100)  # 1060 still forming
        transport = RestPollingCandleTransport(
            timeframe="1m", history=history, clock=clock,
            poll_interval_seconds=5)
        seen = []
        transport.subscribe("BTCUSDT", seen.append, lambda: None)
        try:
            self.assertTrue(wait_for(lambda: len(seen) >= 1))
            time.sleep(0.2)
            self.assertEqual([c.timestamp for c in seen], [1000])
            clock.now = 1200  # 1060 now closed
            self.assertTrue(wait_for(lambda: len(seen) >= 2))
            self.assertEqual([c.timestamp for c in seen],
                             [1000, 1060])
        finally:
            transport.close()

    def test_probe_failure_raises_no_thread(self):
        history = FakeHistory(fail=99)
        transport = RestPollingCandleTransport(
            timeframe="1m", history=history, clock=Clock(5000),
            poll_interval_seconds=5)
        with self.assertRaises(ConnectionError):
            transport.subscribe("BTCUSDT", lambda c: None,
                                lambda: None)
        transport.close()

    def test_sustained_failure_calls_on_down_bounded(self):
        # Probe passes, then every poll fails: on_down fires once
        # the budget exhausts and polling stops (bounded).
        history = FakeHistory([bar(1000)])
        transport = RestPollingCandleTransport(
            timeframe="1m", history=history, clock=Clock(5000),
            poll_interval_seconds=5, max_failures=2)
        down = []
        transport.subscribe("BTCUSDT", lambda c: None,
                            lambda: down.append(1))
        history.fail = 99  # fail only AFTER the probe succeeded
        try:
            self.assertTrue(wait_for(lambda: len(down) >= 1,
                                     timeout=15.0))
            calls_at_down = history.calls
            time.sleep(2.0)
            # Bounded: no further polls after on_down.
            self.assertEqual(history.calls, calls_at_down)
        finally:
            transport.close()

    def test_resubscribe_recovers_without_duplicates(self):
        history = FakeHistory([bar(1000), bar(1060)])
        transport = RestPollingCandleTransport(
            timeframe="1m", history=history, clock=Clock(5000),
            poll_interval_seconds=5)
        seen = []
        transport.subscribe("BTCUSDT", seen.append, lambda: None)
        self.assertTrue(wait_for(lambda: len(seen) >= 2))
        transport.unsubscribe("BTCUSDT")
        history.bars.append(bar(1120))
        transport.subscribe("BTCUSDT", seen.append, lambda: None)
        try:
            self.assertTrue(wait_for(lambda: len(seen) >= 3,
                                     timeout=15.0))
            self.assertEqual([c.timestamp for c in seen],
                             [1000, 1060, 1120])
        finally:
            transport.close()

    def test_invalid_inputs_rejected(self):
        transport = RestPollingCandleTransport(
            timeframe="1m", history=FakeHistory(),
            clock=Clock(5000))
        with self.assertRaises(ValueError):
            transport.subscribe("", lambda c: None, lambda: None)
        with self.assertRaises(TypeError):
            transport.subscribe("BTCUSDT", None, lambda: None)
        with self.assertRaises(ValueError):
            RestPollingCandleTransport(timeframe="7m")
        transport.close()

    def test_stats_and_recent_closed(self):
        history = FakeHistory([bar(1000, 101.0), bar(1060, 102.0)])
        transport = RestPollingCandleTransport(
            timeframe="1m", history=history, clock=Clock(5000),
            poll_interval_seconds=5)
        seen = []
        transport.subscribe("BTCUSDT", seen.append, lambda: None)
        try:
            self.assertTrue(wait_for(lambda: len(seen) >= 2))
            stats = transport.stats("BTCUSDT")["BTCUSDT"]
            self.assertGreaterEqual(stats["polls"], 1)
            self.assertEqual(stats["delivered"], 2)
            self.assertEqual(stats["watermark"], 1060)
            self.assertIsNotNone(stats["last_ok"])
            recent = transport.recent_closed("BTCUSDT")
            self.assertEqual([c.timestamp for c in recent],
                             [1000, 1060])
        finally:
            transport.close()


if __name__ == "__main__":
    unittest.main()
