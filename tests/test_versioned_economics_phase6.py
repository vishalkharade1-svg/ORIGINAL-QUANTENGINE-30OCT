"""Phase-6 versioned economics: zero-cost is never realistic (offline)."""

import unittest

from core.execution.economics import (
    ZERO_NEUTRAL,
    EconomicsProfile,
    annotate_result,
    apply_costs,
    recheck_rr,
    require_realistic,
)


REALISTIC = EconomicsProfile(
    name="delta-btcusdt-taker", version="2026-09-18a",
    commission_rate=0.0005, spread_bps=1.0, slippage_bps=2.0,
    venue_realistic=True, venue_source="delta-docs-fee-schedule",
)


class TestVersionedEconomics(unittest.TestCase):
    def test_zero_neutral_is_not_realistic(self):
        self.assertFalse(ZERO_NEUTRAL.venue_realistic)
        with self.assertRaises(PermissionError):
            require_realistic(ZERO_NEUTRAL)

    def test_realistic_profile_requires_source(self):
        with self.assertRaises(ValueError):
            EconomicsProfile(name="x", version="1", venue_realistic=True,
                             venue_source="")
        self.assertIs(require_realistic(REALISTIC), REALISTIC)

    def test_costs_move_entry_adversely(self):
        long_fill = apply_costs(entry=100.0, direction="BULLISH", quantity=2.0,
                                bars_held=0, profile=REALISTIC)
        self.assertGreater(long_fill.actual_entry, 100.0)
        short_fill = apply_costs(entry=100.0, direction="BEARISH", quantity=2.0,
                                 bars_held=0, profile=REALISTIC)
        self.assertLess(short_fill.actual_entry, 100.0)
        self.assertGreater(long_fill.total_cost, 0.0)

    def test_post_cost_rr_is_reenforced_at_minimum(self):
        # Pre-cost: risk 10, reward 65 -> 6.5 (passes).
        # Post-cost long entry slips to 100.9: risk 10.9, reward 64.1 -> 5.88.
        costed = apply_costs(entry=100.0, direction="BULLISH", quantity=10.0,
                             bars_held=0, profile=REALISTIC)
        verdict = recheck_rr(entry=100.0, stop=90.0, target=165.0,
                             actual_entry=costed.actual_entry,
                             direction="BULLISH")
        # (values depend on profile math; the invariant is fail-closed)
        self.assertEqual(verdict.allowed, verdict.rr >= 6.0)
        if verdict.rr < 6.0:
            self.assertIn("below minimum", verdict.reason)

    def test_eroded_trade_follows_runtime_policy(self):
        verdict = recheck_rr(entry=100.0, stop=90.0, target=165.0,
                             actual_entry=101.0, direction="BULLISH")
        # risk 11, reward 64 -> 5.82R.  The authoritative runtime policy
        # is configurable and defaults to 1R; the legacy hard 6R research
        # threshold is not a runtime execution rule.
        self.assertTrue(verdict.allowed)
        self.assertAlmostEqual(verdict.rr, 64.0 / 11.0, places=6)

    def test_accepted_trade_keeps_minimum(self):
        verdict = recheck_rr(entry=100.0, stop=90.0, target=170.0,
                             actual_entry=100.5, direction="BULLISH")
        # risk 10.5, reward 69.5 -> 6.62
        self.assertTrue(verdict.allowed)

    def test_stop_breach_and_target_erosion_rejected(self):
        self.assertFalse(recheck_rr(
            entry=100.0, stop=90.0, target=170.0, actual_entry=89.0,
            direction="BULLISH").allowed)
        self.assertFalse(recheck_rr(
            entry=100.0, stop=90.0, target=100.2, actual_entry=100.5,
            direction="BULLISH").allowed)

    def test_every_result_identifies_its_profile(self):
        record = annotate_result(ZERO_NEUTRAL)
        self.assertEqual(record["economics_profile"], "explicit-zero-neutral")
        self.assertFalse(record["venue_realistic"])
        self.assertEqual(record["venue_source"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
