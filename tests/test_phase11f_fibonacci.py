"""Phase 11F-1 Fibonacci tests (causal anchors only, no strategy).

Fibonacci levels must never use a future swing. Every level's
causal timestamp is the max of its two anchor confirmations.
"""

import unittest

from research.phase11f import features as F
from research.phase11f import fibonacci as FIB


def _swing_bars():
    # Deterministic shape: valley at idx2, peak at idx6 (left=1/right=1).
    # lows:  idx2 = 90 is lower than idx1=100 and idx3=100.
    # highs: idx6 = 120 exceeds idx5=105 and idx7=105.
    lows = [100, 100, 90, 100, 100, 100, 100, 100, 100, 100, 100, 100]
    highs = [100, 100, 100, 100, 100, 105, 120, 105, 100, 100, 100, 100]
    bars = []
    for i in range(len(lows)):
        bars.append({"time": 1000 + 60 * i, "open": 100, "high": highs[i],
                     "low": lows[i], "close": 100, "volume": 10.0})
    return bars


class TestFibonacciFrozen(unittest.TestCase):
    def test_ratio_sets_frozen(self):
        self.assertEqual(FIB.FIB_RETRACE_RATIOS, (0.382, 0.5, 0.618, 0.786))
        self.assertEqual(FIB.FIB_EXTENSION_RATIOS, (1.272, 1.618))

    def test_custom_ratios_rejected(self):
        bars = _swing_bars()
        with self.assertRaises(ValueError):
            FIB.fib_retracements(bars, ratios=(0.5, 0.7))
        with self.assertRaises(ValueError):
            FIB.fib_extensions(bars, ratios=(1.5,))


class TestFibonacciCausal(unittest.TestCase):
    def test_no_levels_before_both_anchors_confirmed(self):
        bars = _swing_bars()
        # valley e=2 confirmed at 3; peak e=6 confirmed at 7.
        retr = FIB.fib_retracements(bars, left=1, right=1)
        for i in range(7):
            self.assertEqual(retr[i], [], "levels leak before confirmation at %d" % i)
        self.assertTrue(len(retr[7]) == 4)

    def test_causal_timestamp_is_max_confirmation(self):
        bars = _swing_bars()
        retr = FIB.fib_retracements(bars, left=1, right=1)
        for lvl in retr[7]:
            self.assertEqual(lvl["confirmed_index"], 7)
            self.assertLessEqual(lvl["confirmed_index"], 7)
            self.assertEqual(lvl["anchor_low_index"], 2)
            self.assertEqual(lvl["anchor_high_index"], 6)

    def test_retracement_levels_hand_computed(self):
        bars = _swing_bars()
        retr = FIB.fib_retracements(bars, left=1, right=1)
        # bullish impulse low=90 -> high=120; high confirmed later.
        by_ratio = {lvl["ratio"]: lvl["level"] for lvl in retr[7]}
        self.assertAlmostEqual(by_ratio[0.5], 105.0)
        self.assertAlmostEqual(by_ratio[0.618], 101.46)
        self.assertAlmostEqual(by_ratio[0.382], 108.54)
        for lvl in retr[7]:
            self.assertEqual(lvl["direction"], "bullish")

    def test_truncation_invariance(self):
        bars = _swing_bars()
        full = FIB.fib_retracements(bars, left=1, right=1)
        for i in (7, 9, 11):
            prefix = FIB.fib_retracements(bars[:i + 1], left=1, right=1)
            self.assertEqual(prefix[i], full[i])

    def test_future_anchor_mutation_detected(self):
        bars = _swing_bars()
        causal = FIB.fib_retracements(bars, left=1, right=1)
        # At bar 5 the peak (e=6) has not even formed: no levels.
        self.assertEqual(causal[5], [])
        # A mutated reader using unconfirmed extremes (formation
        # bars instead of confirmation bars) would already emit at
        # bar 6 — the causal implementation correctly waits for 7.
        early = FIB.fib_retracements(bars[:7], left=1, right=1)
        self.assertEqual(early[6], [])
        self.assertNotEqual(causal[7], [])

    def test_invalidation_causal(self):
        bars = _swing_bars()
        # close below impulse low invalidates bullish retracement.
        bad = [dict(b) for b in bars]
        bad[9] = dict(bad[9], close=80.0)
        retr = FIB.fib_retracements(bad, left=1, right=1)
        self.assertTrue(all(lvl["invalidated"] for lvl in retr[9]))
        good = FIB.fib_retracements(bars, left=1, right=1)
        self.assertTrue(all(not lvl["invalidated"] for lvl in good[7]))

    def test_extensions_causal_and_deterministic(self):
        bars = _swing_bars()
        ext = FIB.fib_extensions(bars, left=1, right=1)
        self.assertEqual(ext[5], [])
        self.assertEqual(len(ext[7]), 2)
        # bullish extension above high=120, span=30:
        # 1.272 -> 128.16, 1.618 -> 138.54
        by_ratio = {lvl["ratio"]: lvl["level"] for lvl in ext[7]}
        self.assertAlmostEqual(by_ratio[1.272], 128.16)
        self.assertAlmostEqual(by_ratio[1.618], 138.54)
        self.assertEqual(FIB.fib_extensions(list(bars), left=1, right=1), ext)

    def test_uses_ohlc_only_no_footprint(self):
        bars = _swing_bars()
        self.assertFalse(F.orderflow_available())
        retr = FIB.fib_retracements(bars, left=1, right=1)
        for levels in retr:
            for lvl in levels:
                self.assertNotIn("delta", lvl)
                self.assertNotIn("footprint", lvl)


if __name__ == "__main__":
    unittest.main()
