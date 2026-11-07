"""Authoritative data-quality gate at the verified strategy boundary."""

import unittest

from core.history.candle import Candle
from data.delta.market_state_store import AuthoritativeMarketState, DataQuality
from data.delta.market_events import normalize_candlestick_frame
from data.delta.verified_strategy_dispatch import VerifiedStrategyDispatcher


def state(*, stale=False, gap="CONTINUOUS", volume=True):
    candles = {}
    if volume:
        observed = normalize_candlestick_frame({
            "type": "candlestick_1m", "o": 100, "h": 101, "l": 99,
            "c": 100, "v": 1, "res": "1m", "sy": "BTCUSD",
            "cst": 1_700_000_000_000_000, "ts": 1_700_000_000_000_001,
        }, receipt_timestamp=1_700_000_000_000_002, venue="DELTA_INDIA")
        candles = {"1m": observed}
    return AuthoritativeMarketState(
        venue="DELTA_INDIA", instrument="BTCUSD", last_trade=None, candles=candles,
        volume_available=volume, order_book=None,
        data_quality=DataQuality(
            latest_receipt_timestamp=1, stale=stale,
            sequence_status="UNAVAILABLE", gap_status=gap,
            rejected_events=0,
        ),
    )


def candle(*, closed=True):
    return Candle(1, 100, 101, 99, 100, 1, closed=closed, symbol="BTCUSD")


class TestVerifiedStrategyDispatcher(unittest.TestCase):
    def test_only_continuous_fresh_volume_state_reaches_callback(self):
        received = []
        dispatcher = VerifiedStrategyDispatcher(received.append)
        decision = dispatcher.dispatch(candle(), state())
        self.assertTrue(decision.allowed)
        self.assertEqual(received, [candle()])

    def test_missing_state_stale_gap_or_volume_each_fail_closed(self):
        dispatcher = VerifiedStrategyDispatcher(lambda _: self.fail("must not deliver"))
        cases = [
            (None, "MARKET_DATA_UNAVAILABLE"),
            (state(stale=True), "MARKET_DATA_STALE"),
            (state(gap="DATA_GAP_UNREPAIRED"), "MARKET_DATA_GAP_OR_UNKNOWN"),
            (state(volume=False), "MARKET_DATA_VOLUME_UNAVAILABLE"),
        ]
        for market_state, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(dispatcher.dispatch(candle(), market_state).reason, reason)

    def test_forming_candle_is_never_delivered(self):
        dispatcher = VerifiedStrategyDispatcher(lambda _: self.fail("must not deliver"))
        decision = dispatcher.dispatch(candle(closed=False), state())
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "MARKET_DATA_CANDLE_NOT_CLOSED")

    def test_every_decision_emits_structured_nonsecret_observability_record(self):
        records = []
        dispatcher = VerifiedStrategyDispatcher(
            lambda _: None, on_decision=records.append,
        )
        dispatcher.dispatch(candle(), state())
        dispatcher.dispatch(candle(closed=False), state())
        self.assertEqual([(record.allowed, record.reason) for record in records], [
            (True, "MARKET_DATA_ACCEPTED"),
            (False, "MARKET_DATA_CANDLE_NOT_CLOSED"),
        ])
        self.assertEqual(records[0].symbol, "BTCUSD")
        self.assertEqual(records[0].state_venue, "DELTA_INDIA")

    def test_observability_failure_never_delivers_or_raises(self):
        def broken(_):
            raise RuntimeError("telemetry unavailable")

        dispatcher = VerifiedStrategyDispatcher(lambda _: self.fail("must not deliver"), on_decision=broken)
        decision = dispatcher.dispatch(candle(closed=False), state())
        self.assertFalse(decision.allowed)
        self.assertEqual(dispatcher.stats()["rejected"]["MARKET_DATA_OBSERVABILITY_ERROR"], 1)


if __name__ == "__main__":
    unittest.main()
