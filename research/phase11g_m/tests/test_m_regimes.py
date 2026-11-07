"""11G-M regimes (MUT-M9): frozen train-only methodology pinned; M fit nothing."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

KDIR = BASE_DIR / "research" / "phase11g_k"
MDIR = BASE_DIR / "research" / "phase11g_m"


class TestRegimes(unittest.TestCase):
    def test_mut_m9_frozen_methodology_pinned(self):
        for p in sorted(KDIR.glob("hypotheses/*.json")):
            doc = json.loads(p.read_text())
            reg = doc["regimes"]
            self.assertEqual(reg["fit"], "training data only", p.stem)
            self.assertEqual(reg["trend"], "close vs SMA50", p.stem)
            self.assertEqual(reg["volatility"], "ATR14/close terciles", p.stem)

    def test_m_fit_no_regimes(self):
        hits = [p for p in MDIR.rglob("*") if p.is_file()
                and "tests" not in p.parts
                and "regime" in p.name.lower()]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
