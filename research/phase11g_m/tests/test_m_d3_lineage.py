"""11G-M D3 lineage: M created no dataset; dev lineage pins only."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

MDIR = BASE_DIR / "research" / "phase11g_m"
KDIR = BASE_DIR / "research" / "phase11g_k"

ALLOWED_NAMES = {"determine.py", "eligibility.json"}


class TestD3Lineage(unittest.TestCase):
    def test_m_created_no_dataset(self):
        for path in sorted(MDIR.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            if path.suffix in (".py", ".pyc") or path.name in ALLOWED_NAMES:
                continue
            self.fail("unexpected non-code artifact under phase11g_m: %s" % path)

    def test_dev_dataset_pinned(self):
        man = json.loads((KDIR / "freeze" / "freeze_manifest.json").read_text())
        self.assertEqual(man["dataset"], "binance_um_aggtrades_BTCUSDT_2026-09-05")
        self.assertTrue(man["dataset_hash"].startswith("440c9191"))
        self.assertEqual(man["feature_version"], "real-trade-features-v1")

    def test_no_overlap_possible_without_d3(self):
        elig = json.loads((MDIR / "eligibility" / "eligibility.json").read_text())
        self.assertEqual(elig["eligible_set"], [])
        self.assertTrue(all(v == 0 for v in elig["d3_counters_before"].values()))
        self.assertTrue(all(v == 0 for v in elig["d3_counters_after"].values()))


if __name__ == "__main__":
    unittest.main()
