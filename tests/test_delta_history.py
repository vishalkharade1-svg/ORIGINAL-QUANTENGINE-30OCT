"""Delta history smoke tests (offline by default).

Importing this module performs ZERO network I/O. The live
demo path (real /v2/history/candles download) runs only
when the file is executed directly as a script AND the
operator opts in via QE_LIVE_SMOKE=1:

    QE_LIVE_SMOKE=1 python tests/test_delta_history.py
"""

import os
import unittest

from core.exchanges.delta.delta_history import DeltaHistory


class _FakeRest:
    """Stub transport returning a canned candles payload."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get(self, endpoint, params=None):
        self.calls.append((endpoint, params))
        return {"result": self.rows}


def _rows():
    return [
        {
            "time": 1700000000 + 60 * i,
            "open": 100.0 + i,
            "high": 102.0 + i,
            "low": 99.0 + i,
            "close": 101.0 + i,
            "volume": 10.0,
        }
        for i in range(5)
    ]


class TestDeltaHistorySmoke(unittest.TestCase):
    """Offline history: stubbed REST, no network."""

    def test_canned_payload_maps_to_candles(self):
        history = DeltaHistory()
        history.rest = _FakeRest(_rows())
        candles = history.candles("BTCUSDT", "1m", days=1)
        self.assertEqual(len(candles), 5)
        self.assertEqual(candles[0].timestamp, 1700000000)
        self.assertAlmostEqual(candles[-1].close, 105.0)
        self.assertTrue(
            any(
                call[0] == "/v2/history/candles"
                for call in history.rest.calls
            )
        )


def _live_demo():
    """Manual operator demo: real network download + printout."""

    history = DeltaHistory()

    candles = history.candles(
        "BTCUSDT",
        "1m",
        days=1,
    )

    print(type(candles))
    print()

    if isinstance(candles, dict):
        print(candles.keys())
        print()
        print(candles)
    else:
        print(len(candles))
        print(candles[0])


if __name__ == "__main__":
    if os.getenv("QE_LIVE_SMOKE", "") == "1":
        _live_demo()
    else:
        unittest.main()
