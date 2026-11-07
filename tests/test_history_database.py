"""History database smoke tests (offline by default).

The database reads from HistoryStorage; the offline test
pre-populates an isolated temporary ROOT with synthetic
1m candles, so get() never touches the network. Skips
cleanly when pandas/pyarrow are unavailable. The live demo
path runs only when the file is executed directly as a
script AND the operator opts in via QE_LIVE_SMOKE=1:

    QE_LIVE_SMOKE=1 python tests/test_history_database.py
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
from core.history.history_database import HistoryDatabase
from core.history.history_storage import HistoryStorage


def _candles(n=120):
    return [
        Candle(
            timestamp=1700000000 + 60 * i,
            open=100.0 + (i % 7),
            high=102.0 + (i % 7),
            low=99.0 + (i % 7),
            close=101.0 + (i % 7),
            volume=10.0,
            closed=True,
            symbol="BTCUSDT",
        )
        for i in range(n)
    ]


@unittest.skipUnless(
    HAS_PARQUET, "pandas/pyarrow unavailable for database read"
)
class TestHistoryDatabaseSmoke(unittest.TestCase):
    """Offline database read from pre-populated tmp storage."""

    def test_get_reads_local_storage_without_network(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            real_root = HistoryStorage.ROOT
            HistoryStorage.ROOT = Path(tmp)
            try:
                HistoryStorage().save("BTCUSDT", "1m", _candles(120))
                db = HistoryDatabase()
                # Point the database's history client at a
                # transport that fails loudly: any network
                # access fails this test immediately.
                class _NoNetwork:
                    def get(self, *args, **kwargs):
                        raise AssertionError(
                            "network accessed during offline read"
                        )

                db.history = _NoNetwork()
                candles = db.get("BTCUSDT", "1m", days=1)
                self.assertEqual(len(candles), 120)
                # 120 1m bars starting at :33:20 form 23 full
                # 5m buckets plus 2 partial edge buckets = 25.
                aggregated = db.get("BTCUSDT", "5m", days=1)
                self.assertEqual(len(aggregated), 25)
            finally:
                HistoryStorage.ROOT = real_root


def _live_demo():
    """Manual operator demo: local database reads per timeframe."""

    db = HistoryDatabase()

    for tf in [

        "1m",

        "5m",

        "15m",

        "45m",

        "2h",

        "1d",

    ]:

        candles = db.get(

            "BTCUSDT",

            tf,

            days=1,

        )

        print()

        print("=" * 60)

        print(tf)

        print("=" * 60)

        print(len(candles))


if __name__ == "__main__":
    if os.getenv("QE_LIVE_SMOKE", "") == "1":
        _live_demo()
    else:
        unittest.main()
