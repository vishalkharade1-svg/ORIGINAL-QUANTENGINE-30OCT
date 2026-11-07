"""Delta public frames -> canonical strategy runtime end-to-end tests.

Pins the previously missing E2E boundary: the composition of
``DeltaPublicEventStream`` + ``ClosedCandleRouter`` + ``RuntimeCandleBridge``
+ ``MarketStateStore.snapshot`` + ``VerifiedStrategyDispatcher`` delivers
only verified closed traded-price candles with reported volume into the
canonical ``InstitutionalPipeline``.  All frames are documented public
shapes from the Phase-1 fixtures; nothing live, no credentials, and every
fail-closed branch is exercised end to end.
"""

from __future__ import annotations

import unittest

from data.delta.strategy_runtime_adapter import DeltaStrategyRuntimeAdapter
from core.market_state import MarketState
from core.pipeline.institutional_pipeline import InstitutionalPipeline
from core.pipeline.pipeline_context import PipelineContext

T = 1_775_814_834_503_627
T_SECOND = T // 1_000_000

FRAME = {
    "type": "candlestick_1m",
    "o": 100,
    "h": 101,
    "l": 99,
    "c": 100,
    "v": 1,
    "res": "1m",
    "sy": "BTCUSD",
    "cst": T,
    "ts": T + 1,
}


def _candle_frame(**overrides):
    return dict(FRAME, **overrides)


def _build_adapter(symbol="BTCUSD"):
    context = PipelineContext()
    context.market = MarketState(symbol=symbol)
    pipeline = InstitutionalPipeline(context)
    return DeltaStrategyRuntimeAdapter(pipeline), pipeline


class TestDeltaStrategyRuntimeE2E(unittest.TestCase):
    def test_documented_public_frames_reach_the_canonical_strategy_runtime(self):
        adapter, pipeline = _build_adapter()
        forming = adapter.ingest_frame(_candle_frame(), receipt_timestamp=T + 2)
        self.assertEqual(forming.ingest_status, "APPLIED")
        self.assertFalse(forming.routed_to_runtime)
        self.assertFalse(forming.delivered_to_strategy)
        self.assertIsNone(forming.runtime_rejection)

        update = adapter.ingest_frame(
            _candle_frame(h=103, c=102, v=2, ts=T + 2_000_000),
            receipt_timestamp=T + 2_000_003,
        )
        self.assertFalse(update.routed_to_runtime)
        self.assertFalse(update.delivered_to_strategy)

        trigger = adapter.ingest_frame(
            _candle_frame(cst=T + 60_000_000, c=104, h=104,
                          ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        self.assertTrue(trigger.routed_to_runtime)
        self.assertTrue(trigger.delivered_to_strategy)
        self.assertIsNone(trigger.runtime_rejection)
        self.assertEqual(trigger.dispatch_record.reason, "MARKET_DATA_ACCEPTED")
        self.assertEqual(trigger.dispatch_record.candle_timestamp, T_SECOND)
        self.assertEqual(trigger.dispatch_record.state_venue, "DELTA")
        self.assertEqual(trigger.dispatch_record.state_instrument, "BTCUSD")
        self.assertEqual(trigger.venue, "DELTA")
        self.assertEqual(trigger.instrument, "BTCUSD")
        self.assertEqual(trigger.resolution, "1m")
        self.assertEqual(trigger.candle_start_timestamp, T_SECOND)

        delivered = adapter.delivered_events()
        self.assertEqual(len(delivered), 1)
        event = delivered[0]
        self.assertEqual(event.symbol, "BTCUSD")
        self.assertEqual(event.timeframe, "1m")
        candle = event.candle
        self.assertTrue(candle.closed)
        self.assertEqual(candle.timestamp, T_SECOND)
        self.assertEqual(
            (candle.open, candle.high, candle.low, candle.close, candle.volume),
            (100.0, 103.0, 99.0, 102.0, 2.0),
        )
        bars = list(pipeline.context.candles)
        self.assertEqual(len(bars), 1)

        stats = adapter.stats()
        self.assertEqual(stats["events_delivered_to_strategy"], 1)
        self.assertEqual(stats["router"], {"delivered": 1, "suppressed": 2})
        self.assertEqual(
            stats["stream"],
            {"applied": 3, "duplicates_or_old": 0, "rejected": 0, "unhandled": 0},
        )
        self.assertEqual(
            stats["dispatch"],
            {"delivered": 1, "callback_errors": 0, "rejected": {}},
        )

    def test_mark_price_candle_never_reaches_the_strategy_runtime(self):
        adapter, pipeline = _build_adapter(symbol="MARK:BTCUSD")
        mark = "MARK:BTCUSD"
        adapter.ingest_frame(_candle_frame(sy=mark), receipt_timestamp=T + 2)
        trigger = adapter.ingest_frame(
            _candle_frame(sy=mark, cst=T + 60_000_000, ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        self.assertTrue(trigger.routed_to_runtime)
        self.assertFalse(trigger.delivered_to_strategy)
        self.assertEqual(
            trigger.runtime_rejection,
            "mark-price candle cannot enter strategy runtime",
        )
        self.assertEqual(len(pipeline.context.candles), 0)
        self.assertEqual(adapter.delivered_events(), ())

    def test_closed_candle_without_reported_volume_is_never_delivered(self):
        adapter, pipeline = _build_adapter()
        forming = dict(
            (key, value) for key, value in FRAME.items() if key != "v"
        )
        adapter.ingest_frame(forming, receipt_timestamp=T + 2)
        trigger = adapter.ingest_frame(
            _candle_frame(cst=T + 60_000_000, ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        self.assertTrue(trigger.routed_to_runtime)
        self.assertFalse(trigger.delivered_to_strategy)
        self.assertEqual(
            trigger.runtime_rejection,
            "traded candle volume is unavailable",
        )
        self.assertEqual(len(pipeline.context.candles), 0)
        self.assertEqual(
            adapter.stats()["runtime_rejections"],
            {"traded candle volume is unavailable": 1},
        )

    def test_gap_broken_continuity_never_reaches_the_strategy_runtime(self):
        adapter, pipeline = _build_adapter()
        adapter.ingest_frame(_candle_frame(), receipt_timestamp=T + 2)
        jumped = adapter.ingest_frame(
            _candle_frame(cst=T + 180_000_000, ts=T + 180_000_001),
            receipt_timestamp=T + 180_000_002,
        )
        self.assertFalse(jumped.delivered_to_strategy)
        trigger = adapter.ingest_frame(
            _candle_frame(cst=T + 240_000_000, ts=T + 240_000_001),
            receipt_timestamp=T + 240_000_002,
        )
        self.assertFalse(trigger.routed_to_runtime)
        self.assertFalse(trigger.delivered_to_strategy)
        self.assertEqual(adapter.stats()["events_delivered_to_strategy"], 0)
        self.assertEqual(len(pipeline.context.candles), 0)

    def test_duplicate_and_unhandled_frames_are_suppressed_end_to_end(self):
        adapter, pipeline = _build_adapter()
        adapter.ingest_frame(_candle_frame(), receipt_timestamp=T + 2)
        duplicate = adapter.ingest_frame(
            _candle_frame(),
            receipt_timestamp=T + 2_000_001,
        )
        self.assertEqual(duplicate.ingest_status, "DUPLICATE_OR_OLD")
        unhandled = adapter.ingest_frame({"type": "ticker"}, receipt_timestamp=T + 3)
        self.assertEqual(unhandled.ingest_status, "UNHANDLED")
        self.assertFalse(unhandled.routed_to_runtime)
        self.assertFalse(unhandled.delivered_to_strategy)
        self.assertEqual(adapter.delivered_events(), ())
        self.assertEqual(len(pipeline.context.candles), 0)


    def test_adapter_constructor_is_fail_closed_about_its_wiring(self):
        pipeline = InstitutionalPipeline(PipelineContext())
        with self.assertRaises(ValueError):
            DeltaStrategyRuntimeAdapter(None)
        with self.assertRaises(ValueError):
            DeltaStrategyRuntimeAdapter(pipeline, require_volume="true")
        with self.assertRaises(ValueError):
            DeltaStrategyRuntimeAdapter(pipeline, require_volume=False)
        adapter, _ = _build_adapter()
        self.assertIsInstance(adapter, DeltaStrategyRuntimeAdapter)

    def test_delivered_records_carry_a_complete_provenance_trail(self):
        adapter, pipeline = _build_adapter()
        adapter.ingest_frame(_candle_frame(), receipt_timestamp=T + 2)
        forming = adapter.ingest_records()[-1]
        self.assertEqual(forming.provenance.receipt_timestamp, T + 2)
        self.assertIsNone(forming.provenance.candle_timestamp)
        trigger = adapter.ingest_frame(
            _candle_frame(cst=T + 60_000_000, c=104, h=104, ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        prov = trigger.provenance
        self.assertEqual(prov.receipt_timestamp, T + 60_000_002)
        self.assertEqual(prov.candle_timestamp, T_SECOND)
        self.assertEqual(prov.trigger_candle_timestamp, T_SECOND)
        event = adapter.delivered_events()[0]
        self.assertEqual(event.candle.timestamp, prov.candle_timestamp)
        self.assertEqual(adapter.stats()["runtime_rejections"], {})
        self.assertEqual(len(pipeline.context.candles), 1)


if __name__ == "__main__":
    unittest.main()
