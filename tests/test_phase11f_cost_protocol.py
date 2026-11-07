"""Phase 11F-3 cost-protocol tests (frozen scenarios + application order).

Accounting correctness only — no economic research, no hypothesis
runs. Every cost mutation (omission, doubling, reversal, reapplied
costs, inversion) must be detected; restoration passes.
"""

import unittest

from research.phase11f import contracts as K
from research.phase11f import validation as V


class TestCostScenariosFrozen(unittest.TestCase):
    def test_exact_values(self):
        frozen = V.cost_scenarios_frozen()
        self.assertEqual(set(frozen), {"A", "B", "C", "D"})
        self.assertEqual(frozen["A"],
                         {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.0,
                          "SLIPPAGE_BPS": 0.0})
        self.assertEqual(frozen["B"]["COMMISSION_RATE"], 0.0005)
        self.assertEqual(frozen["B"]["SLIPPAGE_BPS"], 2.0)
        self.assertEqual(frozen["C"]["COMMISSION_RATE"], 0.00059)
        self.assertEqual(frozen["C"]["SLIPPAGE_BPS"], 5.0)
        self.assertEqual(frozen["D"]["COMMISSION_RATE"], 0.00118)
        self.assertEqual(frozen["D"]["SLIPPAGE_BPS"], 10.0)
        # No fifth scenario may appear.
        self.assertEqual(len(frozen), 4)

    def test_roles(self):
        self.assertEqual(K.COST_SCENARIOS_11F["A"]["COMMISSION_RATE"], 0.0)


class TestCostApplicationOrder(unittest.TestCase):
    def test_order_frozen(self):
        self.assertEqual(V.COST_ORDER,
                         ["signal", "entry", "position", "gross", "commission",
                          "slippage", "funding", "net"])

    def test_sequence_hand_computed(self):
        # PV=500, scenario C: commission 0.295, slippage 0.5, funding 0.
        win = V.apply_cost_sequence(10.0, 500.0, "C")
        self.assertAlmostEqual(win["commission"], 0.295)
        self.assertAlmostEqual(win["slippage"], 0.5)
        self.assertAlmostEqual(win["funding"], 0.0)
        self.assertAlmostEqual(win["net"], 9.205)
        self.assertEqual(win["order"], V.COST_ORDER)
        # Costs apply identically to losers (no winner/loser asymmetry).
        loss = V.apply_cost_sequence(-10.0, 500.0, "C")
        self.assertAlmostEqual(loss["commission"], 0.295)
        self.assertAlmostEqual(loss["slippage"], 0.5)
        self.assertAlmostEqual(loss["net"], -10.795)

    def test_mut_cost_1_fee_omission_detected(self):
        good = V.apply_cost_sequence(10.0, 500.0, "C")
        # MUT-COST-1: fees silently dropped from net.
        mutant_net = good["gross"] - good["slippage"] - good["funding"]
        self.assertFalse(K.check_pnl_semantics(
            good["gross"], good["commission"], good["slippage"],
            good["funding"], mutant_net))
        self.assertTrue(K.check_pnl_semantics(
            good["gross"], good["commission"], good["slippage"],
            good["funding"], good["net"]))

    def test_mut_cost_2_slippage_double_count_detected(self):
        good = V.apply_cost_sequence(10.0, 500.0, "C")
        # MUT-COST-2: slippage subtracted twice.
        mutant_net = (good["gross"] - good["commission"]
                      - 2.0 * good["slippage"] - good["funding"])
        self.assertFalse(K.check_pnl_semantics(
            good["gross"], good["commission"], good["slippage"],
            good["funding"], mutant_net))
        self.assertTrue(K.check_pnl_semantics(
            good["gross"], good["commission"], good["slippage"],
            good["funding"], good["net"]))

    def test_reversed_slippage_detected(self):
        good = V.apply_cost_sequence(10.0, 500.0, "C")
        mutant_net = (good["gross"] - good["commission"]
                      + good["slippage"] - good["funding"])
        self.assertFalse(K.check_pnl_semantics(
            good["gross"], good["commission"], good["slippage"],
            good["funding"], mutant_net))

    def test_costs_applied_twice_detected(self):
        good = V.apply_cost_sequence(10.0, 500.0, "C")
        mutant_net = (good["gross"] - 2.0 * good["commission"]
                      - 2.0 * good["slippage"] - good["funding"])
        self.assertFalse(K.check_pnl_semantics(
            good["gross"], good["commission"], good["slippage"],
            good["funding"], mutant_net))

    def test_gross_net_inversion_detected(self):
        good = V.apply_cost_sequence(10.0, 500.0, "C")
        self.assertFalse(K.check_pnl_semantics(
            good["net"], good["commission"], good["slippage"],
            good["funding"], good["gross"]))


if __name__ == "__main__":
    unittest.main()
