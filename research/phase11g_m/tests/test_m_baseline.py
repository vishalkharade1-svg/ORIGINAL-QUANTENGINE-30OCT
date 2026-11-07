"""11G-M random baseline: methodology pins; M ran no baselines."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

import research.phase11g_l.run_l as R  # noqa: E402

MDIR = BASE_DIR / "research" / "phase11g_m"
LRES = BASE_DIR / "research" / "phase11g_l" / "results"


class TestBaseline(unittest.TestCase):
    def test_methodology_pinned(self):
        self.assertEqual(R.RB_DRAWS, 500)
        self.assertEqual(list(R.RB_SEEDS), list(range(1108000, 1108500)))
        self.assertEqual(R.V2_SEED, 1107)
        rb = json.loads((LRES / "random_baseline_results.json").read_text())
        self.assertEqual(len(rb), 8)

    def test_m_ran_no_baselines(self):
        hits = [p for p in MDIR.rglob("*") if p.is_file()
                and "tests" not in p.parts
                and "baseline" in p.name.lower()]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
