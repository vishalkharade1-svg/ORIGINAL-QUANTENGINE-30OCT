"""Phase 11F-3 multiple-testing protocol tests (frozen pre-results).

Eight preregistered hypotheses; no run-8-pick-best selection. The
Bonferroni reference + BH-FDR exploratory rule are frozen here on
hand-computed p-values — never on hypothesis results (none exist).
Family-level vs individual evidence stays distinguished.
"""

import unittest

from research.phase11f import validation as V


class TestMultipleTestingFrozen(unittest.TestCase):
    def test_eight_hypotheses_no_selection(self):
        self.assertEqual(V.MULTIPLE_TESTING["n_hypotheses"], 8)
        self.assertIn("NO ranking selection", V.MULTIPLE_TESTING["selection_rule"])
        self.assertIn("holdout replication",
                      V.MULTIPLE_TESTING["selection_rule"])

    def test_bonferroni_reference(self):
        self.assertAlmostEqual(V.MULTIPLE_TESTING["bonferroni_reference"], 0.00625)
        self.assertAlmostEqual(V.bonferroni_threshold(0.05, 8), 0.00625)

    def test_bh_procedure_hand_computed(self):
        # p = [0.01, 0.04, 0.03, 0.20], q=0.10: sorted 0.01(r1:0.025),
        # 0.03(r2:0.05), 0.04(r3:0.075) pass; 0.20(r4:0.10) fails.
        rejected = V.bh_reject([0.01, 0.04, 0.03, 0.20], 0.10)
        self.assertEqual(rejected, {0, 1, 2})
        # q=0.05: bounds 0.0125/0.025/0.0375/0.05 -> 0.01 passes,
        # 0.03 fails, 0.04 fails -> step-up keeps {0} only... check:
        # sorted: 0.01<=0.0125 pass; 0.03>0.025 fail; 0.04>0.0375 fail;
        # 0.20>0.05 fail -> {0}.
        self.assertEqual(V.bh_reject([0.01, 0.04, 0.03, 0.20], 0.05), {0})
        # Empty and null sets stay empty (no phantom discoveries).
        self.assertEqual(V.bh_reject([0.50, 0.60, 0.70], 0.10), set())
        self.assertEqual(V.bh_reject([], 0.10), set())

    def test_bh_deterministic_ties(self):
        first = V.bh_reject([0.02, 0.02, 0.02], 0.10)
        second = V.bh_reject([0.02, 0.02, 0.02], 0.10)
        self.assertEqual(first, second)
        self.assertEqual(first, {0, 1, 2})

    def test_limitation_documented(self):
        self.assertIn("D3", V.MULTIPLE_TESTING["limitation"])

    def test_no_winner_picking_possible(self):
        # The protocol exposes no ranking/selection function over
        # hypotheses — only per-hypothesis gates (later) plus the
        # family reference numbers frozen here.
        self.assertFalse(hasattr(V, "select_winner"))
        self.assertFalse(hasattr(V, "rank_hypotheses"))


if __name__ == "__main__":
    unittest.main()
