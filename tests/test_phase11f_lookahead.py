"""Phase 11F-2 lookahead tests (confirmation timing per structure).

For every structure: unavailable before its confirmation bar, usable
at/after it — never merely because the full dataset already shows
its eventual shape. Includes Fibonacci cases A–E and the
confirmation-timestamp audit table. Synthetic bars only.
"""

import unittest

from research.phase11f import candidates as C
from research.phase11f import causality as Q
from research.phase11f import features as F
from research.phase11f import fibonacci as FIB


def _peak_bars(peak=10.0, n=12, start=5000):
    """Single peak at index 2 (left=1/right=1 confirms at 3)."""
    highs = [1, 2, peak, 2, 1, 1, 1, 1, 1, 1, 1, 1]
    return [{"time": start + 60 * i, "open": 1, "high": h, "low": 0,
             "close": 1, "volume": 1} for i, h in enumerate(highs[:n])]


def _valley_peak_bars():
    """Valley e=2 (confirms 3), peak e=6 (confirms 7), left=1/right=1."""
    lows = [100, 100, 90, 100, 100, 100, 100, 100, 100, 100]
    highs = [100, 100, 100, 100, 100, 105, 120, 105, 100, 100]
    return [{"time": 1000 + 60 * i, "open": 100, "high": highs[i],
             "low": lows[i], "close": 100, "volume": 10.0} for i in range(10)]


def _triple_low_bars():
    """Three equal lows (90) at e=10/20/30, neighbours 100, highs 105."""
    bars = []
    for i in range(45):
        low = 90.0 if i in (10, 20, 30) else 100.0
        bars.append({"time": 7000 + 60 * i, "open": 100, "high": 105,
                     "low": low, "close": 100, "volume": 10.0})
    return bars


class TestFutureSwingRejection(unittest.TestCase):
    def test_future_swing_high_unavailable_before_confirmation(self):
        bars = _peak_bars()
        sw = F.swings(bars, left=1, right=1)
        self.assertIsNone(sw[2])
        self.assertIsNotNone(sw[3])
        self.assertEqual(sw[3]["extreme_index"], 2)
        # Truncation twin: without the confirming bar, no swing exists.
        self.assertIsNone(F.swings(bars[:3], left=1, right=1)[2])

    def test_future_swing_low_unavailable_before_confirmation(self):
        bars = [{"time": i, "open": 5, "high": 9, "low": h, "close": 5, "volume": 1}
                for i, h in enumerate([9, 8, 1, 8, 9, 9, 9])]
        sw = F.swings(bars, left=1, right=1)
        self.assertIsNone(sw[2])
        self.assertIsNotNone(sw[3])
        self.assertEqual(sw[3]["kind"], "low")


class TestFutureEqualLevelRejection(unittest.TestCase):
    def test_level_needs_three_confirmed_touches(self):
        bars = _triple_low_bars()
        # First low confirms at 13, second at 23, third at 33.
        self.assertEqual(F.equal_levels(bars[:14])[13], [])
        mid = F.equal_levels(bars[:24])[23]
        self.assertEqual(mid, [])
        full = F.equal_levels(bars)[33]
        self.assertTrue(any(g["touches"] >= 3 for g in full))
        # The level is never back-dated to the first touch bar.
        self.assertEqual(F.equal_levels(bars[:14])[10], [])


class TestFutureSweepRejection(unittest.TestCase):
    def test_sweep_only_on_reclaim_bar(self):
        bars = _triple_low_bars()
        # Sweep bar: wick to 85, reclaim close 95 (level ~90 confirmed by bar 33).
        sweep_bar = {"time": bars[-1]["time"] + 60, "open": 92, "high": 96,
                     "low": 85.0, "close": 95.0, "volume": 10.0}
        extended = bars + [sweep_bar]
        sw = F.sweeps(extended)
        self.assertIsNone(sw[len(bars) - 1])
        self.assertIsNotNone(sw[len(bars)])
        self.assertEqual(sw[len(bars)]["direction"], "long")
        # Before the sweep bar exists, nothing anticipates it.
        self.assertIsNone(F.sweeps(bars)[len(bars) - 1])


class TestFutureDisplacementRejection(unittest.TestCase):
    def test_displacement_only_on_impulse_bar(self):
        bars = [{"time": i * 60, "open": 100, "high": 101, "low": 99,
                 "close": 100, "volume": 10.0} for i in range(30)]
        self.assertFalse(any(F.displacement(bars)))
        big = dict(bars[-1], time=bars[-1]["time"] + 60,
                   high=120.0, low=80.0, close=115.0)
        extended = bars + [big]
        disp = F.displacement(extended)
        self.assertFalse(any(disp[:-1]))
        self.assertTrue(disp[-1])


class TestFutureFVGRejection(unittest.TestCase):
    def test_fvg_only_at_third_bar(self):
        bars = [
            {"time": 0, "open": 9, "high": 10, "low": 8, "close": 9, "volume": 1},
            {"time": 60, "open": 9, "high": 10, "low": 9, "close": 10, "volume": 1},
        ]
        self.assertEqual(F.fvg_zones(bars), [None, None])
        bars.append({"time": 120, "open": 10, "high": 13, "low": 11,
                     "close": 12, "volume": 1})
        fvg = F.fvg_zones(bars)
        self.assertIsNone(fvg[1])
        self.assertIsNotNone(fvg[2])


class TestFutureOrderBlockRejection(unittest.TestCase):
    def test_ob_uses_strictly_past_bars(self):
        bars = [{"time": i * 60, "open": 100 + (1 if i % 2 else -1),
                 "high": 102, "low": 98, "close": 100, "volume": 1}
                for i in range(10)]
        ob = F.order_block_before(bars, 9, "long")
        self.assertIsNotNone(ob)
        self.assertLess(ob["index"], 9)
        # Appending future bars cannot change the OB resolved at 9.
        future = bars + [{"time": 600 + 60 * k, "open": 200, "high": 210,
                          "low": 190, "close": 205, "volume": 99} for k in range(5)]
        self.assertEqual(F.order_block_before(future, 9, "long"), ob)


class TestFibonacciCausality(unittest.TestCase):
    def test_case_a_future_swing_no_levels(self):
        bars = _valley_peak_bars()
        retr = FIB.fib_retracements(bars, left=1, right=1)
        for i in range(7):  # peak confirms at 7
            self.assertEqual(retr[i], [], "Case A leaks at %d" % i)

    def test_case_b_levels_after_confirmation(self):
        bars = _valley_peak_bars()
        retr = FIB.fib_retracements(bars, left=1, right=1)
        self.assertEqual(len(retr[7]), 4)
        self.assertAlmostEqual(
            {l["ratio"]: l["level"] for l in retr[7]}[0.5], 105.0)

    def test_case_c_future_changes_preserve_history(self):
        bars = _valley_peak_bars()
        ref = FIB.fib_retracements(bars, left=1, right=1)[7]
        wild = bars + [{"time": 1000 + 60 * (10 + k), "open": 500,
                        "high": 900, "low": 100, "close": 700, "volume": 5}
                       for k in range(6)]
        self.assertEqual(FIB.fib_retracements(wild, left=1, right=1)[7], ref)

    def test_case_d_forced_future_anchor_rejected(self):
        bars = _valley_peak_bars()
        # Forcing the unconfirmed peak (formation bar 6) as an anchor
        # at decision 5 must be rejected: no confirmed pair exists.
        self.assertEqual(FIB.fib_retracements(bars[:6], left=1, right=1)[5], [])
        hostile = Q.HostileBars(bars, 5)
        self.assertEqual(FIB.fib_retracements(hostile, left=1, right=1)[5], [])

    def test_case_e_custom_ratios_rejected(self):
        bars = _valley_peak_bars()
        with self.assertRaises(ValueError):
            FIB.fib_retracements(bars, ratios=(0.5, 0.7))
        with self.assertRaises(ValueError):
            FIB.fib_extensions(bars, ratios=(2.0,))
        self.assertEqual(FIB.FIB_RETRACE_RATIOS, (0.382, 0.5, 0.618, 0.786))
        self.assertEqual(FIB.FIB_EXTENSION_RATIOS, (1.272, 1.618))


class TestConfirmationTimestampAudit(unittest.TestCase):
    def test_table_matches_implementation(self):
        by_name = {r["structure"]: r for r in Q.STRUCTURE_TIMING}
        # Swing: extreme at 2 confirmed at 3 (left=1/right=1).
        sw = F.swings(_peak_bars(), left=1, right=1)
        self.assertEqual((sw[3]["extreme_index"], sw[3]["confirmed_index"]), (2, 3))
        # FVG: gap visible exactly at third bar.
        bars = [
            {"time": 0, "open": 9, "high": 10, "low": 8, "close": 9, "volume": 1},
            {"time": 60, "open": 9, "high": 10, "low": 9, "close": 10, "volume": 1},
            {"time": 120, "open": 10, "high": 13, "low": 11, "close": 12, "volume": 1},
        ]
        self.assertIsNotNone(F.fvg_zones(bars)[2])
        # Order block never references its own or a future bar
        # (_valley_peak_bars are dojis, which count as body-up: use short).
        ob = F.order_block_before(_valley_peak_bars(), 8, "short")
        self.assertLess(ob["index"], 8)
        # Fibonacci timestamp equals max anchor confirmation.
        retr = FIB.fib_retracements(_valley_peak_bars(), left=1, right=1)[7]
        self.assertTrue(all(l["confirmed_index"] == 7 for l in retr))
        for row in Q.STRUCTURE_TIMING:
            self.assertEqual(row["backdating_allowed"], "NO")

    def test_breaker_trigger_never_on_setup_bar(self):
        # Crafted cross-and-retest: swing low 80 at e=10 (confirms 13),
        # closes dip under 80, cross back above at bar 16 (arm), touch
        # 80 again at bar 18 (trigger). The trigger bar alone — without
        # the prior arming — must yield nothing.
        bars = []
        for i in range(30):
            bars.append({"time": i * 60, "open": 88, "high": 89,
                         "low": 87, "close": 88, "volume": 10.0})
        bars[10] = dict(bars[10], low=80.0, close=86.0)
        bars[14] = dict(bars[14], close=79.0, low=78.0)
        bars[15] = dict(bars[15], close=78.0, low=77.0)
        bars[16] = dict(bars[16], close=85.0, low=79.0, high=86.0)
        bars[18] = dict(bars[18], low=79.5, high=80.5, close=82.0)
        inst = C.BreakerRetest()
        triggers = []
        for idx in range(len(bars)):
            for sig in inst.signals(idx, bars, None) or []:
                trig = int(sig["setup_id"].rsplit("-", 1)[1])
                self.assertEqual(trig, idx)
                triggers.append(idx)
        self.assertIn(18, triggers)
        for trig in triggers:
            self.assertEqual(C.BreakerRetest().signals(trig, bars, None) or [], [])


if __name__ == "__main__":
    unittest.main()
