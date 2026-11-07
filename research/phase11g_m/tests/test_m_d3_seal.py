"""11G-M D3 seal: counters zero, sealed loaders refuse, no D3 markers."""

import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

MDIR = BASE_DIR / "research" / "phase11g_m"


class TestD3Seal(unittest.TestCase):
    def test_counters_zero(self):
        from research.phase11g import datasets as D11G
        from research.phase11g import fresh as FR
        self.assertEqual(D11G.D3_ACCESS["read"], 0)
        self.assertEqual(D11G.D3_ACCESS["hash"], 0)
        self.assertEqual(D11G.D3_ACCESS["load"], 0)
        self.assertEqual(FR.D3_ACCESS_11GD, {"read": 0, "hash": 0, "load": 0})

    def test_sealed_loaders_refuse(self):
        from research.phase11g import datasets as D11G
        from research.phase11g.registry import registry as RG
        with self.assertRaises(Exception):
            D11G.load_holdout("m-seal-check")
        reg = RG.Registry()
        with self.assertRaises(ValueError):
            reg.register("D3_X", {}, "SEALED")
        with self.assertRaises(RuntimeError):
            reg.d3_block("read")

    def test_no_d3_markers_in_m_files(self):
        for path in list(MDIR.rglob("*.py")) + list(MDIR.rglob("*.json")):
            for line in path.read_text().splitlines():
                if "D3" not in line or "assertNotIn" in line:
                    continue
                self.assertNotIn("universe_D3", line, str(path))
                self.assertNotIn("open(", line, str(path))
                self.assertNotIn("read_bytes", line, str(path))
                self.assertNotIn("load(", line, str(path))


if __name__ == "__main__":
    unittest.main()
