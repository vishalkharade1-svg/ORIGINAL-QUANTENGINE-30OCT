"""11G-M symbols: dev ran BTCUSDT only; M asserts no cross-symbol inference."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

LRES = BASE_DIR / "research" / "phase11g_l" / "results"
MDIR = BASE_DIR / "research" / "phase11g_m"


class TestSymbols(unittest.TestCase):
    def test_dev_single_symbol(self):
        fr = json.loads((LRES / "fold_results.json").read_text())
        syms = {v["symbol"] for v in fr.values()}
        self.assertEqual(syms, {"BTCUSDT"})

    def test_m_no_symbol_results(self):
        elig = json.loads((MDIR / "eligibility" / "eligibility.json").read_text())
        self.assertEqual(elig["eligible_set"], [])
        hits = [p for p in MDIR.rglob("*") if p.is_file()
                and "tests" not in p.parts
                and ("eth" in p.name.lower() or "sol" in p.name.lower()
                     or "symbol" in p.name.lower())]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
