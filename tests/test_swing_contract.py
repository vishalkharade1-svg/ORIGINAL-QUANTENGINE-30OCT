"""
====================================================

QuantEngine

Swing Structure Contract Tests

Run with:

    python -m unittest tests.test_swing_contract -v

Proves the swing stage contract:

1. NO LOOKAHEAD -- the critical regression:
   a) a swing is only "confirmed" once its right-hand
      confirmation window has elapsed (confirmation delay);
   b) a swing's score/institutional flag NEVER changes as later
      candles arrive -- the old `time_score` decayed with
      `len(bars)` so the same swing's score moved candle by
      candle using future bars.
2. `institutional` is reachable: a genuine impulse+volume swing
   crosses the 70 threshold (the old raw scale maxed at 40).
3. Determinism: identical input produces identical swings and
   scores.
4. Swing indices are absolute and monotonically increasing.

Stdlib + dataclasses only -- no network, no pipeline.

====================================================
"""

import unittest

from core.market_structure.swing import Swing
from core.market_structure.swing_registry import SwingRegistry
from core.market_structure.swing_engine import SwingEngine
from core.scoring.swing_score_engine import SwingScoreEngine
from core.registry.indexed_registry import IndexedRegistry

from tests.test_pipeline_regressions import make_candles


class TestSwingNoLookahead(unittest.TestCase):

    def test_swing_confirmation_requires_right_window(self):
        engine = SwingEngine(left=3, right=3)

        # Confirmation needs right=3 future bars. Swings can only
        # be reported for bars with a full right window
        # (i + right <= total - 1), so the newest reportable
        # swing index is total - 1 - right.
        registry = engine.scan(list(make_candles(n=30)), start_index=0)

        for swing in registry.all():
            self.assertLess(
                swing.index,
                30 - 3,
                "A swing must not exist before its right "
                "confirmation window has fully elapsed.",
            )

    def test_swing_score_is_stable_as_future_bars_arrive(self):
        # THE lookahead regression. Scan the same bars twice, with
        # 40 extra bars appended the second time. For every swing
        # index present in BOTH scans, score and institutional
        # flag must be bit-identical -- a swing may start existing
        # (confirmation) or be superseded by a more extreme swing
        # (duplicate filter), but an *existing* swing's score must
        # never depend on candles that arrive after it.
        bars = list(make_candles(n=300))

        first = SwingEngine().scan(bars, start_index=0)
        second = SwingEngine().scan(bars + list(make_candles(n=340)[0:40]), start_index=0)

        first_by_index = {
            s.index: s
            for s in first.all()
        }
        second_by_index = {
            s.index: s
            for s in second.all()
        }

        self.assertGreater(
            len(first_by_index),
            0,
            "Synthetic feed must produce swings for this test "
            "to be meaningful.",
        )

        common = set(first_by_index) & set(second_by_index)

        self.assertGreaterEqual(len(common), 1)

        for index in common:

            a = first_by_index[index]
            b = second_by_index[index]

            self.assertEqual(
                a.score,
                b.score,
                f"Swing #{index} score changed after 40 future "
                f"candles arrived (lookahead).",
            )

            self.assertEqual(
                a.institutional,
                b.institutional,
                f"Swing #{index} institutional flag flipped "
                f"based on future candles (lookahead).",
            )

    def test_indexes_are_absolute_and_monotonic(self):
        bars = list(make_candles(n=250))

        registry = SwingEngine().scan(bars, start_index=100)

        previous_index = -1

        for swing in registry.all():
            self.assertGreater(
                swing.index,
                previous_index,
            )
            previous_index = swing.index

        self.assertGreaterEqual(
            registry.latest().index,
            100,
            "Indices must be absolute session positions, not "
            "window-relative.",
        )


class TestSwingScoringContract(unittest.TestCase):

    def test_institutional_is_reachable(self):
        bars = list(make_candles(n=400))

        registry = SwingEngine().scan(bars, start_index=0)

        institutional = registry.institutional()

        self.assertGreater(
            len(institutional),
            0,
            "A feed with repeated 2% impulse bars + 3x volume "
            "must yield at least one institutional swing. Zero "
            "here means the score threshold is unreachable "
            "(old raw scale maxed at 40 < 70).",
        )

        for swing in institutional:
            self.assertGreaterEqual(swing.score, 70)
            self.assertTrue(swing.institutional)

    def test_maximum_component_sum_normalizes_to_100(self):
        from core.objects.market_object import MarketObject

        swing = MarketObject(
            object_type="SWING",
            symbol="TEST",
            timeframe="1m",
        )

        swing.metadata = {
            "atr_score": 20,
            "volume_score": 15,
            "liquidity_score": 0,
            "bos_score": 0,
            "htf_score": 0,
            "time_score": 5,
        }

        SwingScoreEngine().score(swing)

        self.assertAlmostEqual(swing.score, 100.0)
        self.assertAlmostEqual(swing.quality, 100.0)

    def test_determinism_same_input_same_swings(self):
        bars = list(make_candles(n=300))

        a = SwingEngine().scan(bars, start_index=0)
        b = SwingEngine().scan(bars, start_index=0)

        self.assertEqual(len(a.all()), len(b.all()))

        for x, y in zip(a.all(), b.all()):
            self.assertEqual(x.index, y.index)
            self.assertEqual(x.kind, y.kind)
            self.assertEqual(x.price, y.price)
            self.assertEqual(x.score, y.score)


# ==========================================================
# Registry-level sanity (no hidden state)
# ==========================================================

class TestSwingRegistryContract(unittest.TestCase):

    def test_scan_rebuilds_from_scratch_no_stale_state(self):
        bars = list(make_candles(n=150))

        engine = SwingEngine()

        engine.scan(bars, start_index=0)

        count_before = len(engine.registry.all())

        engine.scan(bars[:80], start_index=0)

        count_after = len(engine.registry.all())

        self.assertGreater(count_before, count_after)
        for swing in engine.registry.all():
            self.assertLess(swing.index, 80 - 3)

    def test_highs_lows_partition(self):
        bars = list(make_candles(n=200))

        registry = SwingEngine().scan(bars, start_index=0)

        for swing in registry.highs():
            self.assertEqual(swing.kind, "HIGH")

        for swing in registry.lows():
            self.assertEqual(swing.kind, "LOW")


if __name__ == "__main__":
    unittest.main()