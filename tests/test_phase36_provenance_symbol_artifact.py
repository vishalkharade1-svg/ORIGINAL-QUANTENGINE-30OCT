from __future__ import annotations
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "research" / "results" / "phase36_provenance_symbol_coverage.json"

class TestPhase36ProvenanceSymbolArtifact(unittest.TestCase):
    def test_bound_provenance_recovers_observed_symbol(self):
        data = json.loads(ART.read_text(encoding="utf-8"))
        coverage = data["coverage"]
        self.assertEqual(data["phase"], 36)
        self.assertEqual(coverage["symbol_source"], "row_level_provenance")
        self.assertEqual(coverage["missing_symbol_rows"], 0)
        self.assertEqual(len(coverage["symbols"]), 1)
        self.assertEqual(coverage["symbols"][0]["symbol"], "BTCUSDT")
        self.assertEqual(coverage["symbols"][0]["rows"], 30247)
        self.assertEqual(coverage["symbols"][0]["trades"], 0)
        self.assertNotEqual(coverage["symbols"][0]["status"], "VERIFIED")
        self.assertFalse(data["universal_validation"])
        self.assertFalse(data["production_ready"])

    def test_rerun_is_byte_identical(self):
        before = ART.read_bytes()
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "build_phase36_provenance_symbol_coverage.py")],
            cwd=str(ROOT), stdout=subprocess.DEVNULL)
        self.assertEqual(before, ART.read_bytes())

if __name__ == "__main__":
    unittest.main()
