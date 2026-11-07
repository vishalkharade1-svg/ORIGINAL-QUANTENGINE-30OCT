"""
====================================================

QuantEngine

Phase 12 -- market-data durability regression tests.

Proves (stdlib only, fake transports/feeds):

  ingestion:
    1. bulk load_history applies the same timestamp
       normalization as streaming (ms == s);
    2. malformed bulk bars fail loudly (NaN, inverted
       high/low, negative volume, bad timestamp);
    3. sparse paginated history is fully collected (the
       under-fetch fix: decrement by NEW candles);
  gaps:
    4. a skipped live bucket is detected and reported as
       DATA_GAP_UNREPAIRED (never silent);
    5. deterministic REST backfill repairs the range
       (normalize + validate + sort + dedupe) and clears
       the report; reruns are identical;
    6. without a fetcher nothing is fabricated;
    7. invalid fetched rows are rejected and the range
       stays unrepaired;
  router:
    8. duplicate/out-of-order/forming rules hold and the
       bounded eviction is deterministic.

====================================================
"""

import unittest

from data.candle_builder import CandleBuilder
from data.delta.delta_subscription_stream import (
    DeltaSubscriptionStream,
)
from data.realtime.candle_router import CandleRouter
from core.history.candle import Candle


def bulk_bar(ts, open_=100.0, high=105.0, low=99.0,
             close=102.0, volume=10.0):
    return {"time": ts, "open": open_, "high": high,
            "low": low, "close": close, "volume": volume}


class TestBulkNormalization(unittest.TestCase):

    def test_milliseconds_equal_seconds(self):
        base = 1788912000  # bucket-aligned epoch seconds
        seconds = [bulk_bar(base + 60 * i) for i in range(5)]
        millis = [bulk_bar((base + 60 * i) * 1000)
                  for i in range(5)]

        first = CandleBuilder(timeframe="1m")
        first.load_history(seconds)
        second = CandleBuilder(timeframe="1m")
        second.load_history(millis)

        self.assertEqual(
            [c.timestamp for c in first.history],
            [c.timestamp for c in second.history])
        self.assertEqual(
            [c.close for c in first.history],
            [c.close for c in second.history])

    def test_malformed_bulk_fails_loudly(self):
        builder = CandleBuilder(timeframe="1m")
        bad_nan = bulk_bar(1788912000)
        bad_nan["close"] = float("nan")
        with self.assertRaises(ValueError):
            builder.load_history([bad_nan])

        bad_shape = bulk_bar(1788912000, high=90.0, low=99.0)
        with self.assertRaises(ValueError):
            builder.load_history([bad_shape])

        bad_volume = bulk_bar(1788912000, volume=-1.0)
        with self.assertRaises(ValueError):
            builder.load_history([bad_volume])

        bad_time = bulk_bar("not-a-time")
        with self.assertRaises(ValueError):
            builder.load_history([bad_time])


class SparseLoader:

    """HistoricalLoader with a scripted sparse transport."""

    def __init__(self, batches):
        from data.historical_loader import HistoricalLoader

        class Scripted(HistoricalLoader):

            def _fetch(self, symbol, resolution, start, end):
                self.calls.append((start, end))
                if not self.batches:
                    return {"result": []}
                return {"result": self.batches.pop(0)}

        self.inner = Scripted()
        self.inner.calls = []
        self.inner.batches = [list(batch) for batch in batches]

    def paginated(self, total):
        return self.inner.candles_paginated(
            "TEST", resolution="1m", total_candles=total,
            request_delay=0)


def sparse_batch(base, count):
    return [bulk_bar(base - 60 * i) for i in range(count)]


class TestSparsePagination(unittest.TestCase):

    def test_thin_batches_fully_collected(self):
        # Three thin batches (10 + 10 + 5); the old
        # `remaining -= batch_size` accounting stopped after
        # the first batch thinking 25 rows arrived.
        batches = [sparse_batch(1788912000, 10),
                   sparse_batch(1788912000 - 600, 10),
                   sparse_batch(1788912000 - 1200, 5)]
        loader = SparseLoader(batches)
        result = loader.paginated(25)
        self.assertEqual(len(result["result"]), 25)


def tick(symbol, ts, price):
    return {"type": "ticker", "d": [{"s": symbol, "m": price}],
            "ts": ts}


class GapStream(DeltaSubscriptionStream):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.closed = []

    def _route(self, candle):
        if candle.closed:
            self.closed.append(candle)


class TestGapRepair(unittest.TestCase):

    def _gapped_stream(self):
        stream = GapStream()
        base = 1788912000
        # Bucket B0 closes...
        for ts in (base + 5, base + 20, base + 40):
            stream._emit_ticker(tick("BTC", ts, 100.0))
        # ...then the feed jumps two buckets ahead.
        for ts in (base + 185, base + 200, base + 250):
            stream._emit_ticker(tick("BTC", ts, 101.0))
        return stream, base

    def test_gap_detected_and_reported_unrepaired(self):
        stream, _ = self._gapped_stream()
        stats = stream.stats()
        self.assertEqual(stats["candle_gaps"], 2)
        status = stream.gap_status()
        self.assertEqual(status["status"], "DATA_GAP_UNREPAIRED")
        self.assertIn("BTC", status["symbols"])
        self.assertEqual(
            status["symbols"]["BTC"]["unrepaired_candles"], 2)

    def test_repair_backfills_and_clears(self):
        stream, base = self._gapped_stream()

        def fetcher(symbol, after_ts, before_ts):
            self.assertEqual(symbol, "BTC")
            # Millisecond unit on purpose: repair must
            # normalize exactly like the live path.
            return [
                {"time": (base + 60) * 1000, "open": 100.0,
                 "high": 101.0, "low": 99.5, "close": 100.5,
                 "volume": 3.0},
                {"time": (base + 120) * 1000, "open": 100.5,
                 "high": 102.0, "low": 100.0, "close": 101.0,
                 "volume": 4.0},
            ]

        first = stream.repair_gaps("BTC", fetcher=fetcher)
        self.assertEqual(first["ranges_repaired"], 1)
        self.assertEqual(first["candles_repaired"], 2)
        self.assertEqual(first["candles_rejected"], 0)
        self.assertEqual(first["unrepaired"], [])
        self.assertTrue(all(c.closed for c in first["repaired"]))
        self.assertEqual(
            [c.timestamp for c in first["repaired"]],
            [base + 60, base + 120])

        # Deterministic rerun: nothing left to repair, same
        # shape (no duplication, no fabrication).
        second = stream.repair_gaps("BTC", fetcher=fetcher)
        self.assertEqual(second["ranges_repaired"], 0)
        self.assertEqual(second["candles_repaired"], 0)
        self.assertEqual(
            stream.gap_status()["status"], "CONTINUOUS")

    def test_no_fetcher_fabricates_nothing(self):
        stream, _ = self._gapped_stream()
        report = stream.repair_gaps("BTC")
        self.assertEqual(report["repaired"], [])
        self.assertEqual(len(report["unrepaired"]), 1)
        self.assertIn("DATA_GAP_UNREPAIRED", report["reason"])
        self.assertEqual(
            stream.gap_status()["status"], "DATA_GAP_UNREPAIRED")

    def test_invalid_rows_rejected_range_survives(self):
        stream, base = self._gapped_stream()

        def bad_fetcher(symbol, after_ts, before_ts):
            return [
                # Outside the missed range (rewrites live!).
                {"time": base, "open": 1.0, "high": 2.0,
                 "low": 0.5, "close": 1.5, "volume": 1.0},
                # Misaligned bucket.
                {"time": base + 61, "open": 1.0, "high": 2.0,
                 "low": 0.5, "close": 1.5, "volume": 1.0},
                # Impossible OHLC.
                {"time": base + 60, "open": 5.0, "high": 4.0,
                 "low": 6.0, "close": 5.0, "volume": 1.0},
                # Non-finite.
                {"time": base + 120, "open": float("nan"),
                 "high": 2.0, "low": 0.5, "close": 1.5,
                 "volume": 1.0},
            ]

        report = stream.repair_gaps("BTC", fetcher=bad_fetcher)
        self.assertEqual(report["candles_repaired"], 0)
        self.assertEqual(report["candles_rejected"], 4)
        self.assertEqual(len(report["unrepaired"]), 1)
        self.assertEqual(
            stream.gap_status()["status"], "DATA_GAP_UNREPAIRED")


class TestRouterBound(unittest.TestCase):

    def test_rules_and_deterministic_eviction(self):
        router = CandleRouter("BTC", max_dedupe=4)

        def closed(ts):
            return Candle(timestamp=ts, open=1.0, high=1.0,
                          low=1.0, close=1.0, volume=1.0,
                          closed=True, symbol="BTC")

        # Forming never delivered.
        forming = closed(100)
        forming.closed = False
        self.assertIsNone(router.route(forming))
        self.assertEqual(router.forming_skipped, 1)

        # Closed delivered once; replay is a duplicate.
        self.assertIsNotNone(router.route(closed(100)))
        self.assertIsNone(router.route(closed(100)))
        self.assertEqual(router.duplicates, 1)

        # Older than delivered is out of order.
        self.assertIsNone(router.route(closed(50)))
        self.assertEqual(router.out_of_order, 1)

        # Bounded eviction is SAFE: after 4 newer
        # timestamps the oldest leaves the dedupe memory, but
        # the last-delivered watermark still rejects its
        # replay as out-of-order (never re-admitted). The
        # bound is a memory optimization, not a correctness
        # hole -- pinned here so a silent change breaks
        # loudly.
        for ts in (200, 300, 400, 500):
            self.assertIsNotNone(router.route(closed(ts)))
        self.assertIsNone(router.route(closed(100)))
        self.assertEqual(router.out_of_order, 2)
        self.assertEqual(router.delivered, 5)


if __name__ == "__main__":
    unittest.main()
