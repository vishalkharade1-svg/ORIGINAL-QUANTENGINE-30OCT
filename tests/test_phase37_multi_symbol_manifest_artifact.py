from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "research" / "results" / "phase37_multi_symbol_oos_manifest.json"
SCRIPT = ROOT / "scripts" / "build_phase37_multi_symbol_manifest.py"


class TestPhase37Artifact(unittest.TestCase):
    def test_current_snapshot_is_single_symbol_and_not_universal(self):
        import json
        payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(payload["symbol_count"], 1)
        self.assertEqual(payload["symbols"][0]["symbol"], "BTCUSDT")
        self.assertEqual(payload["interpretation"]["cross_symbol_validation"], "UNAVAILABLE")

    def test_rerun_is_byte_identical(self):
        before = ARTIFACT.read_bytes()
        subprocess.run([sys.executable, str(SCRIPT)], cwd=str(ROOT),
                       check=True, stdout=subprocess.DEVNULL)
        after = ARTIFACT.read_bytes()
        self.assertEqual(before, after)

    def test_artifact_has_no_wall_clock(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("time.time(", source)
        self.assertNotIn("datetime.now(", source)


if __name__ == "__main__":
    unittest.main()
