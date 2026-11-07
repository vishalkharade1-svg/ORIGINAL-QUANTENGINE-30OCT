"""Replay must rebuild state without causing a runtime delivery."""

import tempfile
import unittest
from pathlib import Path

from data.delta.event_journal import NormalizedEventJournal
from data.delta.event_replay import replay_journal
from data.delta.market_events import normalize_candlestick_frame, normalize_l2_book_frame, normalize_trade_frame


T = 1_775_815_260_000_000


class TestEventReplay(unittest.TestCase):
    def test_replay_rebuilds_market_state_without_runtime_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = NormalizedEventJournal(Path(tmp) / "events.jsonl")
            journal.append(normalize_trade_frame({
                "type": "trades", "p": 100, "s": 2, "r": "t", "sy": "BTCUSDT", "t": T, "ts": T + 1,
            }, receipt_timestamp=T + 2))
            journal.append(normalize_candlestick_frame({
                "type": "candlestick_1m", "o": 100, "h": 102, "l": 99, "c": 101, "v": 3,
                "res": "1m", "sy": "BTCUSDT", "cst": T, "ts": T + 3,
            }, receipt_timestamp=T + 4))
            journal.append(normalize_l2_book_frame({
                "type": "ob_l2", "sy": "BTCUSDT", "ts": T + 5,
                "b": [["99", "2"]], "a": [["101", "4"]],
            }, receipt_timestamp=T + 6))
            store, report = replay_journal(journal)
            state = store.snapshot("DELTA", "BTCUSDT")
            self.assertEqual((report.records_seen, report.events_applied, report.duplicate_or_old), (3, 3, 0))
            self.assertEqual(state.last_trade.price, 100.0)
            self.assertEqual(state.candles["1m"].volume, 3.0)
            self.assertEqual(state.order_book.bids[0].price, 99.0)

    def test_replay_reports_old_candle_without_rewriting_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = NormalizedEventJournal(Path(tmp) / "events.jsonl")
            newer = normalize_candlestick_frame({
                "type": "candlestick_1m", "o": 110, "h": 112, "l": 109, "c": 111, "v": 4,
                "res": "1m", "sy": "BTCUSDT", "cst": T + 60_000_000, "ts": T + 60_000_001,
            }, receipt_timestamp=T + 60_000_002)
            older = normalize_candlestick_frame({
                "type": "candlestick_1m", "o": 100, "h": 102, "l": 99, "c": 101, "v": 3,
                "res": "1m", "sy": "BTCUSDT", "cst": T, "ts": T + 1,
            }, receipt_timestamp=T + 2)
            journal.append(newer)
            journal.append(older)
            store, report = replay_journal(journal)
            self.assertEqual(report.duplicate_or_old, 1)
            self.assertEqual(store.snapshot("DELTA", "BTCUSDT").candles["1m"].close, 111.0)


if __name__ == "__main__":
    unittest.main()
