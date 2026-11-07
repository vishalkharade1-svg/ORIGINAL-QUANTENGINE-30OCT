"""Phase 23 verified transport tests: the 6D seam over the verified chain.

Locks the ``VerifiedPublicCandleTransport`` contract: only fail-closed
verified closed candles and freshness-only forming ticks flow to 6D
workers; mark-price, volume-unavailable, continuity-broken, duplicate
and unhandled frames never deliver.  All frames are documented public
fixture shapes; nothing live.
"""

from __future__ import annotations

import unittest

from data.realtime.verified_transport import (
    VerifiedPublicCandleTransport,
    verified_public_candle_transport_factory,
)

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


class _Sink:
    def __init__(self):
        self.candles = []
        self.downs = 0

    def on_candle(self, candle):
        self.candles.append(candle)

    def on_down(self):
        self.downs += 1

    def closed(self):
        return [c for c in self.candles if c.closed]

    def forming(self):
        return [c for c in self.candles if not c.closed]


def _candle_frame(**overrides):
    return dict(FRAME, **overrides)


class TestVerifiedPublicCandleTransportSeam(unittest.TestCase):
    def test_subscription_seam_fails_closed_on_invalid_callbacks(self):
        transport = VerifiedPublicCandleTransport()
        sink = _Sink()
        with self.assertRaises(ValueError):
            transport.subscribe("", sink.on_candle, sink.on_down)
        with self.assertRaises(ValueError):
            transport.subscribe("BTCUSD", None, sink.on_down)
        with self.assertRaises(ValueError):
            transport.subscribe("BTCUSD", sink.on_candle, None)
        transport.subscribe("BTCUSD", sink.on_candle, sink.on_down)
        with self.assertRaises(ValueError):
            transport.subscribe("BTCUSD", sink.on_candle, sink.on_down)
        self.assertEqual(transport.stats()["symbols"], ("BTCUSD",))

    def test_closed_candle_delivers_with_latest_forming_values(self):
        transport = VerifiedPublicCandleTransport()
        sink = _Sink()
        transport.subscribe("BTCUSD", sink.on_candle, sink.on_down)
        transport.ingest(_candle_frame(), receipt_timestamp=T + 2)
        transport.ingest(
            _candle_frame(h=103, c=102, v=2, ts=T + 2_000_000),
            receipt_timestamp=T + 2_000_003,
        )
        trigger = transport.ingest(
            _candle_frame(cst=T + 60_000_000, c=104, h=104,
                          ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        self.assertEqual(trigger["ingest_status"], "APPLIED")
        self.assertEqual(len(sink.forming()), 2)
        for tick in sink.forming():
            self.assertFalse(tick.closed)
        closed = sink.closed()
        self.assertEqual(len(closed), 1)
        candle = closed[0]
        self.assertTrue(candle.closed)
        self.assertEqual(candle.symbol, "BTCUSD")
        self.assertEqual(candle.timestamp, T_SECOND)
        self.assertEqual(
            (candle.open, candle.high, candle.low, candle.close,
             candle.volume),
            (100.0, 103.0, 99.0, 102.0, 2.0),
        )
        stats = transport.stats()
        self.assertEqual(stats["closed_delivered"], 1)
        self.assertEqual(stats["forming_delivered"], 2)
        self.assertEqual(stats["runtime_rejections"], {})

    def test_mark_price_frame_never_delivers_a_closed_candle(self):
        transport = VerifiedPublicCandleTransport()
        sink = _Sink()
        transport.subscribe("MARK:BTCUSD", sink.on_candle, sink.on_down)
        mark = "MARK:BTCUSD"
        transport.ingest(_candle_frame(sy=mark), receipt_timestamp=T + 2)
        transport.ingest(
            _candle_frame(sy=mark, cst=T + 60_000_000, ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        self.assertEqual(len(sink.closed()), 0)
        stats = transport.stats()
        self.assertEqual(
            stats["runtime_rejections"],
            {"mark-price candle cannot enter strategy runtime": 1},
        )
        self.assertEqual(stats["closed_delivered"], 0)

    def test_closed_candle_without_reported_volume_never_delivers(self):
        transport = VerifiedPublicCandleTransport()
        sink = _Sink()
        transport.subscribe("BTCUSD", sink.on_candle, sink.on_down)
        forming = dict(
            (key, value) for key, value in FRAME.items() if key != "v"
        )
        transport.ingest(forming, receipt_timestamp=T + 2)
        transport.ingest(
            _candle_frame(cst=T + 60_000_000, ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        self.assertEqual(len(sink.closed()), 0)
        stats = transport.stats()
        self.assertEqual(
            stats["runtime_rejections"],
            {"traded candle volume is unavailable": 1},
        )

    def test_gap_broken_continuity_closes_fail_closed(self):
        transport = VerifiedPublicCandleTransport()
        sink = _Sink()
        transport.subscribe("BTCUSD", sink.on_candle, sink.on_down)
        transport.ingest(_candle_frame(), receipt_timestamp=T + 2)
        transport.ingest(
            _candle_frame(cst=T + 180_000_000, ts=T + 180_000_001),
            receipt_timestamp=T + 180_000_002,
        )
        transport.ingest(
            _candle_frame(cst=T + 240_000_000, ts=T + 240_000_001),
            receipt_timestamp=T + 240_000_002,
        )
        self.assertEqual(len(sink.closed()), 0)
        self.assertEqual(len(sink.candles), 1)
        self.assertEqual(len(sink.forming()), 1)
        stats = transport.stats()
        self.assertEqual(stats["closed_delivered"], 0)
        self.assertGreaterEqual(len(stats["runtime_rejections"]), 1)
        self.assertEqual(stats["unrouted"], 0)

    def test_duplicate_and_unhandled_frames_never_deliver(self):
        transport = VerifiedPublicCandleTransport()
        sink = _Sink()
        transport.subscribe("BTCUSD", sink.on_candle, sink.on_down)
        transport.ingest(_candle_frame(), receipt_timestamp=T + 2)
        duplicate = transport.ingest(
            _candle_frame(), receipt_timestamp=T + 2_000_001,
        )
        self.assertEqual(duplicate["ingest_status"], "DUPLICATE_OR_OLD")
        unhandled = transport.ingest(
            {"type": "ticker"}, receipt_timestamp=T + 3,
        )
        self.assertEqual(unhandled["ingest_status"], "UNHANDLED")
        self.assertEqual(len(sink.closed()), 0)
        self.assertEqual(len(sink.forming()), 1)
        stats = transport.stats()
        self.assertEqual(stats["stream"]["duplicates_or_old"], 1)
        self.assertEqual(stats["stream"]["unhandled"], 1)
        self.assertEqual(stats["closed_delivered"], 0)

    def test_symbol_scope_isolation_and_unrouted_accounting(self):
        transport = VerifiedPublicCandleTransport()
        btc = _Sink()
        eth = _Sink()
        transport.subscribe("BTCUSD", btc.on_candle, btc.on_down)
        transport.subscribe("ETHUSD", eth.on_candle, eth.on_down)
        solo = VerifiedPublicCandleTransport()
        orphan = _Sink()
        solo.subscribe("BTCUSD", orphan.on_candle, orphan.on_down)
        solo.ingest(
            _candle_frame(sy="ETHUSD"), receipt_timestamp=T + 2,
        )
        self.assertEqual(orphan.candles, [])
        self.assertEqual(solo.stats()["unrouted"], 1)
        transport.ingest(
            _candle_frame(cst=T + 60_000_000, ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        transport.ingest(
            _candle_frame(cst=T + 120_000_000, ts=T + 120_000_001),
            receipt_timestamp=T + 120_000_002,
        )
        transport.ingest(
            _candle_frame(sy="ETHUSD", cst=T + 60_000_000,
                          ts=T + 60_000_003),
            receipt_timestamp=T + 60_000_004,
        )
        transport.ingest(
            _candle_frame(sy="ETHUSD", cst=T + 120_000_000,
                          ts=T + 120_000_003),
            receipt_timestamp=T + 120_000_004,
        )
        self.assertEqual(len(btc.forming()), 1)
        self.assertEqual(len(btc.closed()), 1)
        self.assertEqual(btc.closed()[0].symbol, "BTCUSD")
        self.assertEqual(len(eth.forming()), 1)
        self.assertEqual(len(eth.closed()), 1)
        self.assertEqual(eth.closed()[0].symbol, "ETHUSD")

    def test_notify_down_fans_out_tears_down_and_resubscribe_restores(self):
        # Phase 24 contract refinement (P24-1): notify_down tears down the
        # affected registrations so the worker's scheduled reconnect retry
        # can re-subscribe; frames received while torn down are unrouted
        # (fail-closed), and re-subscription restores delivery.
        transport = VerifiedPublicCandleTransport()
        btc = _Sink()
        eth = _Sink()
        transport.subscribe("BTCUSD", btc.on_candle, btc.on_down)
        transport.subscribe("ETHUSD", eth.on_candle, eth.on_down)
        transport.notify_down()
        self.assertEqual((btc.downs, eth.downs), (1, 1))
        # Both registrations are gone: frames during the outage are unrouted.
        transport.ingest(
            _candle_frame(sy="ETHUSD"), receipt_timestamp=T + 2,
        )
        self.assertEqual(eth.candles, [])
        self.assertEqual(transport.stats()["unrouted"], 1)
        # A repeated down signal for an already-torn-down symbol is a
        # no-op (no registration, no callback, no error).
        transport.notify_down(symbol="ETHUSD")
        self.assertEqual((btc.downs, eth.downs), (1, 1))
        # The worker's reconnect retry seam re-subscribes and delivery
        # resumes for NEW frames (an exact replay of an already-applied
        # frame stays stream-deduped: DUPLICATE_OR_OLD, no delivery).
        transport.subscribe("ETHUSD", eth.on_candle, eth.on_down)
        transport.ingest(
            _candle_frame(sy="ETHUSD", ts=T + 3_000_000),
            receipt_timestamp=T + 3,
        )
        self.assertEqual(len(eth.forming()), 1)
        self.assertEqual(transport.stats()["unrouted"], 1)
        transport.unsubscribe("ETHUSD")
        transport.ingest(
            _candle_frame(sy="ETHUSD", ts=T + 4_000_000),
            receipt_timestamp=T + 4,
        )
        self.assertEqual(len(eth.forming()), 1)
        self.assertEqual(len(btc.forming()), 0)

    def test_6d_worker_receives_only_verified_closed_candles(self):
        from data.realtime.subscription_manager import (
            MultiSymbolSubscriptionManager,
        )
        from data.realtime.subscription_state import SubscriptionStatus

        transport = VerifiedPublicCandleTransport()
        manager = MultiSymbolSubscriptionManager(
            transport_factory=lambda: transport,
            max_stale_seconds=600.0,
        )

        class _Instrument:
            symbol = "BTCUSD"

        delivered = []
        manager.candles_callback = delivered.append
        sync = manager.sync([_Instrument()])
        self.assertEqual(sync["added"], ["BTCUSD"])
        state = manager.statuses()["BTCUSD"]
        self.assertEqual(state.status, SubscriptionStatus.LIVE)

        transport.ingest(_candle_frame(), receipt_timestamp=T + 2)
        transport.ingest(
            _candle_frame(cst=T + 60_000_000, c=104, h=104,
                          ts=T + 60_000_001),
            receipt_timestamp=T + 60_000_002,
        )
        self.assertEqual(state.delivered, 1)
        self.assertEqual(state.forming_skipped, 1)
        self.assertEqual(len(delivered), 1)
        candle = delivered[0]
        self.assertTrue(candle.closed)
        self.assertEqual(candle.symbol, "BTCUSD")
        self.assertEqual(candle.timestamp, T_SECOND)

    def test_factory_shape(self):
        factory = verified_public_candle_transport_factory(resolution="1m")
        transport = factory()
        self.assertIsInstance(transport, VerifiedPublicCandleTransport)

    def test_paper_main_verified_transport_is_opt_in(self):
        from core.runtime.paper_main import build_paper_engine

        class _Universe:
            def refresh_discovery(self, client=None, normalizer=None):
                return {"explicit": True, "instruments": 0}

            def build_universe(self, timeframe="1m"):
                from core.universe.market_universe import MarketUniverse
                from core.universe.universe_policy import UniversePolicy
                return MarketUniverse(
                    policy=UniversePolicy(),
                    instruments=[],
                    timeframe=timeframe or "1m",
                    captured_at=0,
                )

        import os
        previous = os.environ.pop("QE_PAPER_VERIFIED_TRANSPORT", None)
        try:
            os.environ["QE_PAPER_VERIFIED_TRANSPORT"] = "1"
            engine, _manager = build_paper_engine(
                universe_manager=_Universe(),
            )
            engine.subscriptions._ensure_transport()
            transport = engine.subscriptions.transport
            self.assertIsInstance(transport, VerifiedPublicCandleTransport)
        finally:
            if previous is None:
                os.environ.pop("QE_PAPER_VERIFIED_TRANSPORT", None)
            else:
                os.environ["QE_PAPER_VERIFIED_TRANSPORT"] = previous
        engine_off, _manager_off = build_paper_engine(
            universe_manager=_Universe(),
        )
        engine_off.subscriptions._ensure_transport()
        self.assertEqual(
            engine_off.subscriptions.transport.__class__.__name__,
            "_AuthoritativeCandleTransportRequired",
        )


if __name__ == "__main__":
    unittest.main()
