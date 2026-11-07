"""11G-M Monte Carlo: seed/count pins; M ran no simulations."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

import research.phase11g_l.run_l as R  # noqa: E402

MDIR = BASE_DIR / "research" / "phase11g_m"
LRES = BASE_DIR / "research" / "phase11g_l" / "results"


class TestMonteCarlo(unittest.TestCase):
    def test_seeds_pinned(self):
        self.assertEqual(R.MC_SIMS, 5000)
        self.assertEqual(R.MC_SEED_SHUFFLE, 1107001)
        self.assertEqual(R.MC_SEED_BOOT, 1107002)
        mc = json.loads((LRES / "monte_carlo_results.json").read_text())
        self.assertEqual(len(mc), 8)

    def test_m_ran_no_monte_carlo(self):
        hits = [p for p in MDIR.rglob("*") if p.is_file()
                and "tests" not in p.parts
                and ("monte_carlo" in p.name.lower() or "montecarlo" in p.name.lower())]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
