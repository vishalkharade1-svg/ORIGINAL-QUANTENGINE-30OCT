"""History storage smoke tests (offline by default).

The parquet round-trip test runs against an isolated
temporary ROOT (never the repo's data/history/) and skips
cleanly when pandas/pyarrow are unavailable, so collection
stays deterministic with or without the optional parquet
engine. The live demo path (real download + repo save)
runs only when the file is executed directly as a script
AND the operator opts in via QE_LIVE_SMOKE=1:

    QE_LIVE_SMOKE=1 python tests/test_history_storage.py
"""

import os
import unittest

try:
    import pandas  # noqa: F401

    import pyarrow  # noqa: F401

    HAS_PARQUET = True
except Exception:
    HAS_PARQUET = False

from core.history.candle import Candle
from core.history.history_storage import HistoryStorage


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


@unittest.skipUnless(
    HAS_PARQUET, "pandas/pyarrow unavailable for parquet round-trip"
)
class TestHistoryStorageSmoke(unittest.TestCase):
    """Offline parquet round-trip in an isolated tmp ROOT."""

    def test_save_load_round_trip(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            real_root = HistoryStorage.ROOT
            HistoryStorage.ROOT = Path(tmp)
            try:
                storage = HistoryStorage()
                storage.save("BTCUSDT", "1m", _candles(10))
                self.assertTrue(storage.exists("BTCUSDT", "1m"))
                df = storage.load("BTCUSDT", "1m")
                self.assertEqual(len(df), 10)
                self.assertAlmostEqual(
                    float(df["close"].iloc[-1]), 110.0
                )
            finally:
                HistoryStorage.ROOT = real_root


def _live_demo():
    """Manual operator demo: real download + repo save/load."""

    from core.exchanges.delta.delta_history import DeltaHistory

    history = DeltaHistory()

    storage = HistoryStorage()

    candles = history.candles(

        "BTCUSDT",

        "1m",

        days=1,

    )

    storage.save(

        "BTCUSDT",

        "1m",

        candles,

    )

    df = storage.load(

        "BTCUSDT",

        "1m",

    )

    print()

    print("=" * 60)

    print("ROWS")

    print("=" * 60)

    print(len(df))

    print()

    print(df.head())


if __name__ == "__main__":
    if os.getenv("QE_LIVE_SMOKE", "") == "1":
        _live_demo()
    else:
        unittest.main()
