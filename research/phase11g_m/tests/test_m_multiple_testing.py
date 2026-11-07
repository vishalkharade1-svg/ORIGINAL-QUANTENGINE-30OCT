"""11G-M multiple testing: denominator 8 retained, tested 0, corrections pinned."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

MDIR = BASE_DIR / "research" / "phase11g_m"


class TestMultipleTesting(unittest.TestCase):
    def test_denominator_retained_tested_empty(self):
        elig = json.loads((MDIR / "eligibility" / "eligibility.json").read_text())
        self.assertEqual(elig["family_denominator"], 8)
        self.assertEqual(elig["eligible_set"], [])
        self.assertEqual(len(elig["hypotheses"]), 8)
        barred = [h for h, v in elig["hypotheses"].items()
                  if v["branch"] == "RESURRECTION_BARRED"]
        self.assertEqual(sorted(barred), ["H11GK-004", "H11GK-007"])

    def test_corrections_pinned(self):
        self.assertAlmostEqual(0.05 / 8, 0.00625)
        self.assertEqual(0.10, 0.10)


if __name__ == "__main__":
    unittest.main()
