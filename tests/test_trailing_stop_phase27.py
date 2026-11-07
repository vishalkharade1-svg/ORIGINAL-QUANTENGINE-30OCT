"""
Phase 27 trailing-stop primitive contract tests.

These tests only exercise deterministic functions that are pure (no
setup/open_trade interaction) and therefore do not depend on the
open_trade signature changes introduced in Phase 27.
"""

import unittest
from core.backtesting.trailing_stop import round_stop_to_tick, evaluate_trailing_stop, TrailingStopConfig


class TestTickRounding(unittest.TestCase):

    def test_bullish_rounds_down(self):
        self.assertEqual(round_stop_to_tick(102.74, 0.5, True), 102.5)
        self.assertEqual(round_stop_to_tick(102.76, 0.5, True), 102.5)

    def test_bearish_rounds_up(self):
        self.assertEqual(round_stop_to_tick(97.26, 0.5, False), 97.5)
        self.assertEqual(round_stop_to_tick(97.74, 0.5, False), 98.0)


class TestEvaluateTrailingStop(unittest.TestCase):

    def test_invalid_method_fails_closed(self):
        # Passing an unsupported method forces config.validate() to raise ValueError.
        _ = evaluate_trailing_stop(
            direction="BULLISH",
            entry=100.0,
            initial_stop=95.0,
            current_stop=95.0,
            close=105.0,
            activated=False,
            peak_price=105.0,
            config=TrailingStopConfig(
                activation_r=1.0,
                distance_r=0.5,
                method="TRAILING_TIGHT",
                step_r=0.0,
                tick_size=0.5,
            ),
        )


if __name__ == "__main__":
    unittest.main()