"""Phase 33 readiness snapshot: deterministic, real-cache, non-executing."""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ART = ROOT / "research" / "results" / "phase33_oos_readiness_snapshot.json"
CACHE = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"


class TestPhase33Snapshot(unittest.TestCase):
    def test_artifact_exists_and_is_blocked(self):
        self.assertTrue(ART.exists())
        artifact = json.loads(ART.read_text(encoding="utf-8"))
        self.assertEqual(artifact["phase"], 33)
        self.assertEqual(artifact["snapshot"]["overall_readiness"], "BLOCKED")
        self.assertEqual(artifact["snapshot"]["handoff_state"], "WAITING_FOR_DATA")
        self.assertFalse(artifact["production_ready"])
        self.assertFalse(artifact["is_production_ready"])

    def test_snapshot_binds_current_dataset(self):
        env = json.loads(CACHE.read_text(encoding="utf-8"))
        artifact = json.loads(ART.read_text(encoding="utf-8"))
        blob = json.dumps(sorted(env["raw"], key=lambda r: r["time"]),
                          sort_keys=True, separators=(",", ":")).encode()
        identity = hashlib.sha256(blob).hexdigest()
        self.assertEqual(identity, env["dataset_identity"])
        self.assertEqual(identity, artifact["dataset"]["identity"])
        self.assertEqual(len(env["raw"]), artifact["dataset"]["rows"])

    def test_no_hypothesis_or_execution(self):
        artifact = json.loads(ART.read_text(encoding="utf-8"))
        snap = artifact["snapshot"]
        self.assertEqual(snap["hypothesis_count"], 0)
        self.assertEqual(snap["available_fills"], 3)
        self.assertGreaterEqual(snap["fill_gap"], 57)
        self.assertFalse(snap["is_production_ready"])

    def test_rerun_is_byte_identical(self):
        before = ART.read_bytes()
        subprocess.check_call([sys.executable,
                               str(ROOT / "scripts" /
                                   "build_phase33_oos_readiness_snapshot.py")],
                              cwd=str(ROOT))
        after = ART.read_bytes()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
