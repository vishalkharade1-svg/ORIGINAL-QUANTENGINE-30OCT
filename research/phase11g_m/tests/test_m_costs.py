"""11G-M costs (MUT-M5/M6/M7): ladder pins, mutant detection, no-fee-omission."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f.harness import COST_SCENARIOS_11F  # noqa: E402

LRES = BASE_DIR / "research" / "phase11g_l" / "results"


class TestCosts(unittest.TestCase):
    def test_mut_m5_cost_ladder_pinned(self):
        self.assertEqual(COST_SCENARIOS_11F["A"],
                         {"COMMISSION_PER_TRADE": 0.0, "COMMISSION_RATE": 0.0,
                          "SLIPPAGE_BPS": 0.0})
        self.assertEqual(COST_SCENARIOS_11F["B"]["COMMISSION_RATE"], 0.0005)
        self.assertEqual(COST_SCENARIOS_11F["B"]["SLIPPAGE_BPS"], 2.0)
        self.assertEqual(COST_SCENARIOS_11F["C"]["COMMISSION_RATE"], 0.00059)
        self.assertEqual(COST_SCENARIOS_11F["C"]["SLIPPAGE_BPS"], 5.0)
        self.assertEqual(COST_SCENARIOS_11F["D"]["COMMISSION_RATE"], 0.00118)
        self.assertEqual(COST_SCENARIOS_11F["D"]["SLIPPAGE_BPS"], 10.0)
        bad = dict(COST_SCENARIOS_11F["C"], COMMISSION_RATE=0.0, SLIPPAGE_BPS=0.0)
        self.assertNotEqual(bad, COST_SCENARIOS_11F["C"])

    def test_mut_m6_m7_no_fee_or_slippage_omission(self):
        fr = json.loads((LRES / "fold_results.json").read_text())
        n = 0
        for v in fr.values():
            for t in v["costs"]["C"]["trades"]:
                pv = abs(t["quantity"]) * abs(t["entry"])
                self.assertGreater(pv, 0.0)
                # Omission would zero these despite positive notional.
                self.assertGreater(t["commission"] + t["slippage"], 0.0)
                n += 1
        self.assertTrue(n > 0)


if __name__ == "__main__":
    unittest.main()
