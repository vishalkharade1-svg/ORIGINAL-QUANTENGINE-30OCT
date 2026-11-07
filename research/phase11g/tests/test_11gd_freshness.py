"""11G-D contamination + WF-feasibility tests (no strategy runs)."""

import unittest

from research.phase11g import fresh as FR


class TestContaminationRegistry(unittest.TestCase):
    def test_fresh_vs_contaminated(self):
        self.assertEqual(FR.freshness("oos_fresh"), "FRESH")
        for known in ("D1_BTC", "D1_ETH", "D2_BTC", "D2_ETH",
                      "gate_a_snapshot", "phase7_file"):
            self.assertEqual(FR.freshness(known), "CONTAMINATED", known)

    def test_sealed_and_unknown(self):
        with self.assertRaises(FR.SealedHoldoutError):
            FR.freshness("D3_BTC")
        with self.assertRaises(FR.SealedHoldoutError):
            FR.freshness("universe_D3_ETH.json")
        self.assertEqual(FR.freshness("something_new"), "UNKNOWN")

    def test_hostile_relabel_blocked(self):
        # A contaminated dataset presented as fresh must NOT verify:
        # only the exact authorized name is FRESH.
        self.assertNotEqual(FR.freshness("D2_BTC"), "FRESH")
        self.assertNotEqual(FR.freshness("OOS_FRESH"), "FRESH")
        self.assertEqual(FR.freshness("oos_fresh"), "FRESH")

    def test_counters_zero(self):
        self.assertEqual(FR.D3_ACCESS_11GD, {"read": 0, "hash": 0, "load": 0})


class TestWFFeasibility(unittest.TestCase):
    def test_2499_cannot_host_4folds(self):
        feasible, need = FR.wf_feasible(2499)
        self.assertFalse(feasible)
        self.assertEqual(need, 6175)

    def test_7001_hosts_4folds(self):
        feasible, _ = FR.wf_feasible(7001)
        self.assertTrue(feasible)

    def test_no_fake_folds(self):
        from research.phase11f import validation as V
        with self.assertRaises(ValueError):
            V.build_folds(2499)


if __name__ == "__main__":
    unittest.main()
