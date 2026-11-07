"""Replay engine smoke tests (Phase 11D: offline by default).

Importing this module performs ZERO disk/network I/O. The
original demo (local HistoryDatabase read) runs only when the
file is executed directly as a script AND the operator opts
in via QE_LIVE_SMOKE=1:

    QE_LIVE_SMOKE=1 python tests/test_replay_engine.py
"""

import os
import unittest

from core.history.candle import Candle
from core.replay.replay_engine import ReplayEngine


def _synthetic_candles(n=10):
    return [
        Candle(
            timestamp=1_700_000_000 + 60 * i,
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=10.0,
            closed=True,
            symbol="BTCUSDT",
        )
        for i in range(n)
    ]


class TestReplayEngineSmoke(unittest.TestCase):
    """Offline replay: synthetic candles, no database I/O."""

    def test_replay_iterates_all_candles(self):
        engine = ReplayEngine(_synthetic_candles(10))
        count = 0
        while not engine.finished():
            candle = engine.next()
            count += 1
            self.assertIsNotNone(candle)
        self.assertEqual(count, 10)
        self.assertEqual(engine.progress(), 100)


def _local_demo():
    """Manual operator demo: local history database replay."""

    from core.history.history_database import HistoryDatabase

    db = HistoryDatabase()

    data = db.get(

        "BTCUSDT",

        "1m",

        days=1,

    )

    engine = ReplayEngine(data)

    print()

    print("=" * 60)

    print("REPLAY")

    print("=" * 60)

    print()

    count = 0

    while not engine.finished():

        candle = engine.next()

        count += 1

        if count <= 5:

            print(candle)

    print()

    print("Processed :", count)

    print("Progress  :", engine.progress(), "%")


if __name__ == "__main__":
    if os.getenv("QE_LIVE_SMOKE", "") == "1":
        _local_demo()
    else:
        unittest.main()
