"""11G-M reproducibility: eligibility regenerates byte-identical; L repro pinned."""

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

MDIR = BASE_DIR / "research" / "phase11g_m"
LRES = BASE_DIR / "research" / "phase11g_l" / "results"


class TestReproducibility(unittest.TestCase):
    def test_eligibility_byte_identical(self):
        out = MDIR / "eligibility" / "eligibility.json"
        before = out.read_bytes()
        r = subprocess.run(
            [sys.executable, "research/phase11g_m/eligibility/determine.py"],
            capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out.read_bytes(), before)

    def test_l_repro_artifact_pinned(self):
        rep = json.loads((LRES / "reproducibility_results.json").read_text())
        self.assertTrue(rep["identical"])
        self.assertEqual(len(rep["folds"]), 96)

    def test_result_hash_recorded(self):
        elig = json.loads((MDIR / "eligibility" / "eligibility.json").read_text())
        h = hashlib.sha256(
            json.dumps(elig, sort_keys=True).encode()).hexdigest()
        self.assertEqual(len(h), 64)
        self.assertEqual(elig["code_hash"],
                         hashlib.sha256(
                             (MDIR / "eligibility" / "determine.py").read_bytes()
                         ).hexdigest())


if __name__ == "__main__":
    unittest.main()
