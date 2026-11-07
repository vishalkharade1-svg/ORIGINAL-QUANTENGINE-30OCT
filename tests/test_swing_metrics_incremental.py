"""
====================================================

QuantEngine

Swing Metrics Incremental TR Contract Tests

Run with:

    python -m unittest tests.test_swing_metrics_incremental -v

Proves the TR memo ("incremental swing ATR", STATUS 87) is
behavior-identical to the classic per-call true-range loop:
the atr result at EVERY index in a sliding feed equals a
reference implementation that recomputes each TR from the raw
bars (same for impulse/displacement/volume metrics). Also
proves the memo is correctly reused across a sliding window
and cleared by reset().

Stdlib only -- no network, no pipeline.

====================================================
"""

import unittest

from core.market_structure.swing_metrics import SwingMetrics


class _Bar:

    def __init__(
        self,
        timestamp,
        open,
        high,
        low,
        close,
        volume,
    ):

        self.timestamp = timestamp

        self.open = open

        self.high = high

        self.low = low

        self.close = close

        self.volume = volume


def _reference_atr(bars, index, atr_period=14):
    """The pre-incremental SwingMetrics.atr algorithm."""

    if index < atr_period:
        return None

    total = 0.0

    for i in range(index - atr_period + 1, index + 1):

        high = bars[i].high

        low = bars[i].low

        prev_close = bars[i - 1].close

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )

        total += tr

    return total / atr_period


def _reference_metrics(bars, index, atr_period=14):

    atr = _reference_atr(bars, index, atr_period)

    impulse = 0.0 if atr is None or atr == 0 else (bars[index].high - bars[index].low) / atr

    candle = bars[index]

    body = abs(candle.close - candle.open)

    rng = candle.high - candle.low

    displacement = 0.0 if rng == 0 else body / rng

    start = max(0, index - 20)

    total = 0.0

    count = 0

    for i in range(start, index):

        total += bars[i].volume

        count += 1

    avg = total / count if count else 0.0

    volume_ratio = 1.0 if avg <= 0 else bars[index].volume / avg

    return {

        "impulse": impulse,

        "displacement": displacement,

        "volume_ratio": volume_ratio,

        "atr_score": min(20.0, impulse * 10.0),

        "volume_score": min(15.0, volume_ratio * 7.5),

        "liquidity_score": 0.0,

        "bos_score": 0.0,

        "htf_score": 0.0,

        "time_score": 5.0,

    }


def _bars(n):

    bars = []

    for i in range(n):

        base = 49000.0 + i

        bars.append(
            _Bar(
                timestamp=i + 1,
                open=base,
                high=base + ((i * 7) % 41),
                low=base - ((i * 5) % 37),
                close=base + ((i * 3) % 29) - 4,
                volume=100.0 + ((i * 11) % 900),
            )
        )

    return bars


class TestSwingMetricsIncremental(unittest.TestCase):

    def test_atr_bit_identical_across_full_window(self):

        bars = _bars(200)

        metrics = SwingMetrics()

        for index in range(14, 200):

            with self.subTest(index=index):

                self.assertEqual(
                    metrics.atr(bars, index),
                    _reference_atr(bars, index),
                )

    def test_incremental_sliding_window_matches_reference(self):

        # Feed a growing then sliding history the way scan() does:
        # one bar per step, window capped at max_candles.
        history = _bars(160)

        metrics = SwingMetrics()

        window = []

        for i, bar in enumerate(history):

            window.append(bar)

            if len(window) > 100:

                window.pop(0)

            # Every index in the live window must match the raw
            # per-call recomputation on the SAME window.
            for index in range(14, len(window)):

                self.assertEqual(
                    metrics.atr(window, index),
                    _reference_atr(window, index),
                    f"mismatch at step {i} index {index}",
                )

    def test_calculate_identical_to_reference(self):

        bars = _bars(120)

        metrics = SwingMetrics()

        for index in (20, 60, 100, 119):

            with self.subTest(index=index):

                self.assertEqual(
                    metrics.calculate(bars, index),
                    _reference_metrics(bars, index),
                )

    def test_reset_clears_memo_and_stays_identical(self):

        bars = _bars(80)

        metrics = SwingMetrics()

        first = metrics.calculate(bars, 60)

        metrics.reset()

        again = metrics.calculate(bars, 60)

        self.assertEqual(again, first)

        self.assertEqual(again, _reference_metrics(bars, 60))


if __name__ == "__main__":

    unittest.main()