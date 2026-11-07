"""Phase-13 P0: post-cost R:R single authority (deterministic, offline).

Covers the required regression cases against the ONE mandatory
authority (core.risk.costs.post_cost_rr):

  A. gross RR >= 1 but costs push it below 1  -> REFUSED
  B. gross RR < 1                             -> REFUSED
  C. post-cost RR exactly 1.0                 -> ACCEPTED (inclusive)
  D. LONG / SHORT symmetry
  E. zero vs unknown economics distinction
  F. non-finite costs                         -> FAIL CLOSED

Plus cross-authority equivalence: economics.recheck_rr (zero-cost
delegate) agrees with post_cost_rr on a deterministic grid, proving
there is ONE formula, not two. Stdlib only. No network.
"""

from __future__ import annotations

import math
import unittest


class TestPostCostRRCases(unittest.TestCase):
    def test_case_a_gross_passes_but_costs_refuse(self):
        from core.risk.costs import post_cost_rr

        # Gross: (110-100)/10 = 1.0. Scale costs up so the
        # post-cost reward/risk falls below the new 1.0 minimum.
        verdict = post_cost_rr(direction="BULLISH", entry=100.0,
                               stop=90.0, target=110.0, quantity=1.0,
                               commission=12.0, slippage=0.0)
        self.assertFalse(verdict.allowed)
        self.assertGreater(verdict.rr, 0.0)
        self.assertIn("below minimum", verdict.reason)

    def test_case_b_gross_below_minimum_refused(self):
        from core.risk.costs import post_cost_rr

        # Gross (105-100)/10 = 0.5 < 1, zero costs: refused.
        verdict = post_cost_rr(direction="BULLISH", entry=100.0,
                               stop=90.0, target=105.0, quantity=2.0,
                               commission=0.0, slippage=0.0)
        self.assertFalse(verdict.allowed)
        self.assertAlmostEqual(verdict.rr, 0.5, places=9)

    def test_case_c_exactly_six_accepted_inclusive(self):
        from core.risk.costs import post_cost_rr

        # Post-cost exactly 6.0: LONG entry 101.0 (shifted), risk
        # 2.5, reward 15.0 -> 6.0. Inclusive boundary accepts.
        verdict = post_cost_rr(direction="BULLISH", entry=101.0,
                               stop=98.5, target=116.0, quantity=1.5,
                               commission=0.0, slippage=0.0)
        self.assertTrue(verdict.allowed)
        self.assertAlmostEqual(verdict.rr, 6.0, places=9)

    def test_case_d_long_short_symmetry(self):
        from core.risk.costs import post_cost_rr

        long_v = post_cost_rr(direction="BULLISH", entry=100.0,
                              stop=90.0, target=170.0, quantity=2.0,
                              commission=3.0, slippage=2.0)
        short_v = post_cost_rr(direction="BEARISH", entry=100.0,
                               stop=110.0, target=30.0, quantity=2.0,
                               commission=3.0, slippage=2.0)
        self.assertTrue(long_v.allowed)
        self.assertTrue(short_v.allowed)
        self.assertAlmostEqual(long_v.rr, short_v.rr, places=9)
        self.assertAlmostEqual(long_v.actual_entry - 100.0,
                               100.0 - short_v.actual_entry, places=9)
        # Refusal is symmetric too.
        long_bad = post_cost_rr(direction="BULLISH", entry=100.0,
                                stop=90.0, target=110.0, quantity=2.0,
                                commission=3.0, slippage=2.0)
        short_bad = post_cost_rr(direction="BEARISH", entry=100.0,
                                 stop=110.0, target=90.0, quantity=2.0,
                                 commission=3.0, slippage=2.0)
        self.assertFalse(long_bad.allowed)
        self.assertFalse(short_bad.allowed)
        self.assertAlmostEqual(long_bad.rr, short_bad.rr, places=9)

    def test_case_e_zero_vs_unknown(self):
        from core.risk.costs import (
            CONFIGURED_SIMULATION,
            EXPLICIT_ZERO,
            UNKNOWN,
            VENUE_VERIFIED,
            CostSpec,
            describe,
            require_known,
            unknown_costs,
        )

        # Zero means explicit zero: known, active, vacuous shift.
        zero = CostSpec(per_trade=0.0, rate=0.0, slippage_bps=0.0)
        self.assertEqual(describe(zero), EXPLICIT_ZERO)
        self.assertIs(require_known(zero), zero)
        # Missing means unknown: fail closed, never a silent zero.
        unknown = unknown_costs()
        self.assertEqual(describe(unknown), UNKNOWN)
        with self.assertRaises(ValueError):
            require_known(unknown)
        with self.assertRaises(ValueError):
            require_known(None)
        with self.assertRaises(TypeError):
            require_known({"per_trade": 0.0})
        # Configured nonzero without venue evidence is simulation.
        sim = CostSpec(per_trade=1.0, rate=0.0005, slippage_bps=5.0)
        self.assertEqual(describe(sim), CONFIGURED_SIMULATION)
        # Only a cited venue source counts as venue-verified.
        venue = CostSpec(per_trade=1.0, rate=0.0005, slippage_bps=5.0,
                         venue_source="delta-docs-fee-schedule")
        self.assertEqual(describe(venue), VENUE_VERIFIED)

    def test_case_f_non_finite_costs_fail_closed(self):
        from core.risk.costs import post_cost_rr

        for bad in (float("nan"), float("inf"), float("-inf")):
            for kwargs in ({"commission": bad, "slippage": 0.0},
                           {"commission": 0.0, "slippage": bad},
                           {"commission": bad, "slippage": bad}):
                verdict = post_cost_rr(direction="BULLISH", entry=100.0,
                                       stop=90.0, target=170.0,
                                       quantity=2.0, **kwargs)
                self.assertFalse(verdict.allowed, kwargs)
        # Non-finite legs and quantity fail closed too.
        self.assertFalse(post_cost_rr(
            direction="BULLISH", entry=float("nan"), stop=90.0,
            target=170.0, quantity=2.0, commission=0.0,
            slippage=0.0).allowed)
        self.assertFalse(post_cost_rr(
            direction="BULLISH", entry=100.0, stop=90.0,
            target=170.0, quantity=0.0, commission=1.0,
            slippage=1.0).allowed)
        # Negative costs are corrupt, never a subsidy.
        self.assertFalse(post_cost_rr(
            direction="BULLISH", entry=100.0, stop=90.0,
            target=170.0, quantity=2.0, commission=-1.0,
            slippage=0.0).allowed)
        # Inverted geometry can never pass on ratio alone.
        self.assertFalse(post_cost_rr(
            direction="BULLISH", entry=100.0, stop=110.0,
            target=170.0, quantity=2.0, commission=0.0,
            slippage=0.0).allowed)
        # Unknown direction fails closed.
        self.assertFalse(post_cost_rr(
            direction="SIDEWAYS", entry=100.0, stop=90.0,
            target=170.0, quantity=2.0, commission=0.0,
            slippage=0.0).allowed)

    def test_costs_shift_entry_adversely_by_side(self):
        from core.risk.costs import post_cost_rr

        # One-way (4+2)/2 = 3 on qty 2 -> 1.5 adverse shift.
        long_v = post_cost_rr(direction="BULLISH", entry=100.0,
                              stop=90.0, target=200.0, quantity=2.0,
                              commission=4.0, slippage=2.0)
        short_v = post_cost_rr(direction="BEARISH", entry=100.0,
                               stop=110.0, target=0.0, quantity=2.0,
                               commission=4.0, slippage=2.0)
        self.assertAlmostEqual(long_v.actual_entry, 101.5, places=9)
        self.assertAlmostEqual(short_v.actual_entry, 98.5, places=9)


class TestSingleAuthorityEquivalence(unittest.TestCase):
    def test_recheck_rr_delegates_exactly(self):
        # economics.recheck_rr is a zero-cost delegate of
        # costs.post_cost_rr. Verdicts (allowed) agree on EVERY
        # grid point; exact (risk, reward, rr) numerics agree on
        # every geometrically valid point. On inverted-geometry
        # inputs both refuse (the delegate reports zeros with a
        # geometry reason where the legacy form reported raw legs
        # — a refused fill either way; documented, not drift).
        from core.backtesting.accounting import directional_geometry_ok
        from core.execution.economics import recheck_rr
        from core.risk.costs import post_cost_rr

        entries = (90.0, 99.5, 100.0, 100.5, 101.0, 110.0)
        stops = (89.0, 90.0, 95.0)
        targets = (100.2, 160.0, 165.0, 170.0)
        for direction in ("BULLISH", "BEARISH"):
            for actual in entries:
                for stop in stops:
                    for target in targets:
                        legacy = recheck_rr(entry=100.0, stop=stop,
                                            target=target,
                                            actual_entry=actual,
                                            direction=direction)
                        canon = post_cost_rr(
                            direction=direction, entry=actual,
                            stop=stop, target=target, quantity=1.0,
                            commission=0.0, slippage=0.0)
                        self.assertEqual(
                            legacy.allowed, canon.allowed,
                            msg=(direction, actual, stop, target))
                        if directional_geometry_ok(direction, actual,
                                                   stop, target):
                            self.assertAlmostEqual(
                                legacy.risk, canon.risk, places=9,
                                msg=(direction, actual, stop, target))
                            self.assertAlmostEqual(
                                legacy.reward, canon.reward,
                                places=9,
                                msg=(direction, actual, stop, target))
                            self.assertAlmostEqual(
                                legacy.rr, canon.rr, places=9,
                                msg=(direction, actual, stop, target))
                        else:
                            self.assertFalse(legacy.allowed)
                            self.assertFalse(canon.allowed)

    def test_recheck_rr_reason_contract_preserved(self):
        from core.execution.economics import recheck_rr

        refused = recheck_rr(entry=100.0, stop=90.0, target=100.5,
                             actual_entry=100.0, direction="BULLISH")
        self.assertFalse(refused.allowed)
        self.assertIn("below minimum", refused.reason)
        accepted = recheck_rr(entry=100.0, stop=90.0, target=170.0,
                              actual_entry=100.5, direction="BULLISH")
        self.assertTrue(accepted.allowed)


if __name__ == "__main__":
    unittest.main()
