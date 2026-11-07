"""Paper result labels must not overstate zero-cost assumptions."""

import unittest

from core.paper_trading.readiness import assess_paper_readiness
from core.risk.costs import CostSpec


class TestPaperReadiness(unittest.TestCase):
    def test_unverified_or_zero_cost_profile_is_not_evidence_ready(self):
        self.assertFalse(assess_paper_readiness(
            costs=CostSpec(), profile_name="zero", venue_realistic=False
        ).ready)
        self.assertFalse(assess_paper_readiness(
            costs=CostSpec(), profile_name="claimed", venue_realistic=True
        ).ready)

    def test_verified_nonzero_cost_profile_is_ready_label_only(self):
        verdict = assess_paper_readiness(
            costs=CostSpec(1.0, 0.0005, 5.0), profile_name="delta-sandbox-verified",
            venue_realistic=True,
        )
        self.assertTrue(verdict.ready)
        self.assertEqual(verdict.status, "READY")


if __name__ == "__main__":
    unittest.main()
