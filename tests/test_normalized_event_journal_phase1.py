"""Tests for the durable, fail-closed normalized event journal."""

import tempfile
import unittest
from pathlib import Path

from data.delta.event_journal import JournalCorruption, NormalizedEventJournal
from data.delta.market_events import normalize_candlestick_frame, normalize_trade_frame


T = 1_775_815_140_000_000


class TestNormalizedEventJournal(unittest.TestCase):
    def test_round_trip_is_ordered_and_restart_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            trade = normalize_trade_frame({
                "type": "trades", "p": "100", "s": "2", "r": "m",
                "sy": "BTCUSDT", "t": T, "ts": T + 1,
            }, receipt_timestamp=T + 2)
            candle = normalize_candlestick_frame({
                "type": "candlestick_1m", "o": 100, "h": 102, "l": 99,
                "c": 101, "v": 3, "res": "1m", "sy": "BTCUSDT",
                "cst": T, "ts": T + 3,
            }, receipt_timestamp=T + 4)
            journal = NormalizedEventJournal(path)
            self.assertEqual(journal.append(trade).ordinal, 1)
            self.assertEqual(journal.append(candle).ordinal, 2)
            records = list(NormalizedEventJournal(path).records())
            self.assertEqual([record.event_type for record in records], ["TRADE", "CANDLE"])
            self.assertEqual(records[1].event["volume"], 3.0)
            self.assertEqual(NormalizedEventJournal(path).append(trade).ordinal, 3)

    def test_partial_or_noncontiguous_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('{"schema_version":1,"ordinal":1', encoding="utf-8")
            with self.assertRaises(JournalCorruption):
                NormalizedEventJournal(path)
            path.write_text(
                '{"schema_version":1,"ordinal":2,"event_type":"TRADE","event":{}}\n',
                encoding="utf-8",
            )
            with self.assertRaises(JournalCorruption):
                list(NormalizedEventJournal(path).records())


if __name__ == "__main__":
    unittest.main()
