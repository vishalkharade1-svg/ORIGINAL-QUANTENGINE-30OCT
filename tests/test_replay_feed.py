"""Replay feed smoke tests (offline by default).

Pure in-memory replay over synthetic candles; no database
or network at import or in tests. The local-database demo
runs only when the file is executed directly as a script
AND the operator opts in via QE_LIVE_SMOKE=1:

    QE_LIVE_SMOKE=1 python tests/test_replay_feed.py
"""

import os
import unittest

from core.history.candle import Candle
from core.replay.replay_engine import ReplayEngine
from core.replay.replay_feed import ReplayFeed


def _candles(n=10):
    return [
        Candle(
            timestamp=1700000000 + 60 * i,
            open=100.0 + i,
            high=102.0 + i,
            low=99.0 + i,
            close=101.0 + i,
            volume=10.0,
            closed=True,
            symbol="BTCUSDT",
        )
        for i in range(n)
    ]


class TestReplayFeedSmoke(unittest.TestCase):
    """Offline feed: synthetic candles, deterministic."""

    def test_feed_collects_replayed_candles(self):
        engine = ReplayEngine(_candles(10))
        feed = ReplayFeed()
        while not engine.finished():
            feed.add(engine.next())
        self.assertEqual(feed.size(), 10)
        self.assertIsNotNone(feed.latest())

    def test_feed_reset_clears(self):
        feed = ReplayFeed()
        for candle in _candles(5):
            feed.add(candle)
        self.assertEqual(feed.size(), 5)
        feed.reset()
        self.assertEqual(feed.size(), 0)


def _local_demo():
    """Manual operator demo: local database replay."""

    from core.history.history_database import HistoryDatabase

    db = HistoryDatabase()

    candles = db.get(

        "BTCUSDT",

        "1m",

        days=1,

    )

    engine = ReplayEngine(candles)

    feed = ReplayFeed()

    print()

    print("=" * 60)
    print("REPLAY FEED")
    print("=" * 60)

    while not engine.finished():

        candle = engine.next()

        feed.add(candle)

        if feed.size() <= 5:

            print(

                feed.size(),

                feed.latest(),

            )

    print()

    print("History Size:", feed.size())


if __name__ == "__main__":
    if os.getenv("QE_LIVE_SMOKE", "") == "1":
        _local_demo()
    else:
        unittest.main()
