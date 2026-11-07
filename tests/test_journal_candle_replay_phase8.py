"""Normalized journal replay must preserve finality and gaps."""

import tempfile
import unittest
from pathlib import Path

from data.delta.event_journal import NormalizedEventJournal
from data.delta.journal_candle_replay import replay_verified_candles
from data.delta.market_events import normalize_candlestick_frame


T = 1_775_815_500_000_000


def event(start, publish, *, volume=2):
    frame = {"type": "candlestick_1m", "o": 100, "h": 102, "l": 99, "c": 101,
             "res": "1m", "sy": "BTCUSDT", "cst": start, "ts": publish}
    if volume is not None:
        frame["v"] = volume
    return normalize_candlestick_frame(frame, receipt_timestamp=publish + 1)


class TestJournalCandleReplay(unittest.TestCase):
    def test_only_previous_causally_closed_candle_is_replayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = NormalizedEventJournal(Path(tmp) / "events.jsonl")
            journal.append(event(T, T + 1))
            journal.append(event(T + 60_000_000, T + 60_000_001))
            candles, report = replay_verified_candles(journal, symbol="BTCUSDT", resolution="1m")
            self.assertEqual(len(candles), 1)
            self.assertTrue(candles[0].closed)
            self.assertEqual(candles[0].timestamp, T // 1_000_000)
            self.assertEqual(report.delivered, 1)

    def test_gap_and_missing_volume_never_enter_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = NormalizedEventJournal(Path(tmp) / "events.jsonl")
            journal.append(event(T, T + 1, volume=None))
            journal.append(event(T + 120_000_000, T + 120_000_001, volume=2))
            candles, report = replay_verified_candles(journal, symbol="BTCUSDT", resolution="1m")
            self.assertEqual(candles, [])
            self.assertEqual(report.delivered, 0)


if __name__ == "__main__":
    unittest.main()
