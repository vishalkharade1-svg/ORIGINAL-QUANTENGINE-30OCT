"""Phase 35 artifact integrity tests."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "research" / "results" / "phase35_symbol_coverage.json"


class TestPhase35Artifact(unittest.TestCase):
    def test_current_snapshot_is_unavailable_cross_symbol(self):
        data = json.loads(ART.read_text(encoding="utf-8"))
        coverage = data["coverage"]
        self.assertEqual(data["phase"], 35)
        self.assertEqual(coverage["symbols"], [])
        self.assertEqual(coverage["missing_symbol_rows"], 30247)
        self.assertFalse(data["universal_validation"])
        self.assertFalse(data["production_ready"])

    def test_rerun_is_byte_identical(self):
        before = ART.read_bytes()
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "build_phase35_symbol_coverage.py")],
            cwd=str(ROOT), stdout=subprocess.DEVNULL)
        self.assertEqual(before, ART.read_bytes())


if __name__ == "__main__":
    unittest.main()
