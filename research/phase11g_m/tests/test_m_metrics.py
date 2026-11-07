"""11G-M metrics (read-only on L artifacts): accounting identity, NBO timing."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

LRES = BASE_DIR / "research" / "phase11g_l" / "results"


class TestMetricsIntegrity(unittest.TestCase):
    def test_accounting_identity_all_trades(self):
        fr = json.loads((LRES / "fold_results.json").read_text())
        n = 0
        for v in fr.values():
            for c in ("A", "B", "C", "D"):
                for t in v["costs"][c]["trades"]:
                    self.assertAlmostEqual(
                        (t["gross"] - t["commission"] - t["slippage"]) - t["net"],
                        0.0, places=9)
                    n += 1
        self.assertTrue(n > 0)

    def test_nbo_timing_all_trades(self):
        fr = json.loads((LRES / "fold_results.json").read_text())
        n = 0
        for v in fr.values():
            for c in ("A", "B", "C", "D"):
                for t in v["costs"][c]["trades"]:
                    self.assertEqual(t["entry_time"] - t["decision_time"], 60)
                    n += 1
        self.assertTrue(n > 0)

    def test_cost_ladder_monotone(self):
        costs = json.loads((LRES / "cost_results.json").read_text())
        for hid, per in costs.items():
            self.assertGreaterEqual(per["A"]["net"], per["B"]["net"], hid)
            self.assertGreaterEqual(per["B"]["net"], per["C"]["net"], hid)
            self.assertGreaterEqual(per["C"]["net"], per["D"]["net"], hid)


if __name__ == "__main__":
    unittest.main()
