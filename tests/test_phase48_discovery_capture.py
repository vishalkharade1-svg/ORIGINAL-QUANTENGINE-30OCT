import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_phase48_discovery_capture.py"
ARTIFACT = ROOT / "research" / "results" / "phase48_discovery_capture.json"


class TestPhase48DiscoveryCapture(unittest.TestCase):
    def run_builder(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_capture_is_nonempty_and_research_only(self):
        self.run_builder()
        payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "phase48-discovery-capture-v1")
        self.assertEqual(payload["source"], "Backtester + ResearchJournal")
        self.assertGreater(payload["record_count"], 0)
        self.assertGreater(payload["event_count"], 0)
        self.assertFalse(payload["production_ready"])

    def test_capture_is_byte_deterministic(self):
        self.run_builder()
        first = ARTIFACT.read_bytes()
        self.run_builder()
        second = ARTIFACT.read_bytes()
        self.assertEqual(first, second)

    def test_content_identity_matches(self):
        self.run_builder()
        payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        identity = payload.pop("content_identity")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertEqual(identity, hashlib.sha256(canonical).hexdigest())


if __name__ == "__main__":
    unittest.main()
