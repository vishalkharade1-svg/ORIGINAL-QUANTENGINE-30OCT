"""Phase 23 engine-level integration: verified transport -> paper runtime.

Drives the REAL ``RealTimeEngine`` assembly with the
``VerifiedPublicCandleTransport``: documented public fixture frames reach the
canonical multi-symbol runtime; the fail-closed matrix (mark-price,
volume-unavailable, gap-continuity, duplicates, unhandled) never delivers an
actionable candle into the paper path.  No live transport, no credentials,
zero exchange writes (dry-run by construction).
"""

from __future__ import annotations

import unittest

from data.realtime.verified_transport import VerifiedPublicCandleTransport
from data.realtime.stream_worker import SubscriptionWorker
from core.runtime.realtime_engine import RealTimeEngine
from core.runtime.pipeline_registry import PipelineRegistry
from core.universe.market_universe import MarketUniverse
from core.universe.universe_policy import UniversePolicy

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


class _Instrument:
    symbol = "BTCUSD"
    exchange = "DELTA"
    instrument_id = "BTCUSD"


class _FakeUniverseManager:
    """The documented explicit-cut duck used by offline engine tests."""

    def __init__(self):
        self.discovery_attempts = 0

    def refresh_discovery(self, client=None, normalizer=None):
        self.discovery_attempts += 1
        return {"explicit": True, "instruments": 1}

    def build_universe(self, timeframe="1m"):
        return MarketUniverse(
            policy=UniversePolicy(),
            instruments=[_Instrument()],
            timeframe=timeframe or "1m",
            captured_at=0,
        )


class TestVerifiedPaperEngineIntegration(unittest.TestCase):
    def _engine(self):
        transport = VerifiedPublicCandleTransport()
        engine = RealTimeEngine(
            universe_manager=_FakeUniverseManager(),
            transport_factory=lambda: transport,
            clock=lambda: float(T_SECOND),
        )
        return engine, transport

    def test_verified_frames_reach_the_real_paper_runtime(self):
        engine, transport = self._engine()
        engine.start()
        self.assertEqual(engine.registry.count, 1)
        engine.poll()

        transport.ingest(_candle_frame(), receipt_timestamp=T + 2)
        transport.ingest(
            _candle_frame(h=103, c=102, v=2, ts=T + 2_000_000),
            receipt_timestamp=T + 2_000_003,
        )
        transport.ingest(
            _candle_frame(cst=T + 60_000_000, c=104, h=104,
                          ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        self.assertEqual(engine.routed, 1)
        self.assertEqual(engine.unrouted, 0)
        self.assertEqual(engine.route_errors, 0)
        statuses = engine.statuses()
        self.assertEqual(len(statuses), 1)

    def test_fail_closed_frames_never_reach_the_paper_runtime(self):
        engine, transport = self._engine()
        engine.start()
        self.assertEqual(engine.registry.count, 1)
        engine.poll()

        mark = "MARK:BTCUSD"
        transport.ingest(_candle_frame(sy=mark), receipt_timestamp=T + 2)
        transport.ingest(
            _candle_frame(sy=mark, cst=T + 60_000_000, ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        transport.ingest(_candle_frame(), receipt_timestamp=T + 4)
        unhandled = transport.ingest(
            {"type": "ticker"}, receipt_timestamp=T + 5,
        )
        self.assertEqual(unhandled["ingest_status"], "UNHANDLED")
        self.assertEqual(engine.routed, 0)
        self.assertEqual(engine.route_errors, 0)
        stats = transport.stats()
        self.assertEqual(
            stats["runtime_rejections"],
            {"mark-price candle cannot enter strategy runtime": 1},
        )
        self.assertEqual(stats["closed_delivered"], 0)

    def test_worker_prevents_forming_ticks_from_reaching_strategy(self):
        transport = VerifiedPublicCandleTransport()
        sink = []
        worker = SubscriptionWorker(
            symbol="BTCUSD",
            transport=transport,
            clock=lambda: float(T_SECOND),
            on_closed_candle=lambda candle: sink.append(
                ("CLOSED", candle),
            ),
        )
        worker.start()
        transport.ingest(_candle_frame(), receipt_timestamp=T + 2)
        self.assertEqual(sink, [])
        self.assertEqual(worker.state.forming_skipped, 1)
        transport.ingest(
            _candle_frame(cst=T + 60_000_000, c=104, h=104,
                          ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        closed = [entry for entry in sink if isinstance(entry, tuple)]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0][1].symbol, "BTCUSD")
        self.assertEqual(closed[0][1].timestamp, T_SECOND)
        self.assertEqual(worker.state.delivered, 1)

    def test_registry_builds_an_isolated_symbol_pipeline(self):
        registry = PipelineRegistry(timeframe="1m")
        pipeline = registry.pipeline_for(_Instrument())
        self.assertIsNotNone(pipeline.world)


if __name__ == "__main__":
    unittest.main()
