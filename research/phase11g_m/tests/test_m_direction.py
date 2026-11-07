"""11G-M direction: frozen direction rules pinned (read-only); M claims nothing."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

KDIR = BASE_DIR / "research" / "phase11g_k"
MDIR = BASE_DIR / "research" / "phase11g_m"


class TestDirection(unittest.TestCase):
    def test_frozen_direction_rules_present(self):
        for p in sorted(KDIR.glob("hypotheses/*.json")):
            doc = json.loads(p.read_text())
            self.assertTrue(isinstance(doc["direction"], str) and doc["direction"],
                            p.stem)

    def test_m_no_directional_claims(self):
        elig = json.loads((MDIR / "eligibility" / "eligibility.json").read_text())
        self.assertEqual(elig["eligible_set"], [])
        for v in elig["hypotheses"].values():
            self.assertNotIn("LONG", json.dumps(v))
            self.assertNotIn("SHORT", json.dumps(v))


if __name__ == "__main__":
    unittest.main()
