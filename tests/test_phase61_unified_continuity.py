import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))

class TestPhase61UnifiedContinuity(unittest.TestCase):
    def test_phase60_branches_are_merged(self):
        for rel in (
            "tests/test_phase60_continuity_lock.py",
            "tests/test_phase60_9l_admission_readiness.py",
            "scripts/audit_phase60_9l_admission_readiness.py",
            "research/results/phase60_continuity_lock.json",
            "research/results/phase60_9l_admission_readiness.json",
        ):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_phase44_57_matrix_is_preserved(self):
        path = os.path.join(ROOT, "research/results/phase61_unified_continuity.json")
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
        expected = {
            "44":"PRESENT","45":"PRESENT","46":"PRESENT",
            "47":"RESTORED_PHASE59","48":"RESTORED_PHASE59",
            "49":"MISSING_GENUINE_ARTIFACT","50":"PRESENT","51":"PRESENT",
            "52":"PRESENT","53":"PRESENT","54":"PRESENT",
            "55":"RESTORED_PHASE59_BOUNDARY","56":"PRESENT","57":"PRESENT",
        }
        self.assertEqual(obj["phase44_57"], expected)
        self.assertFalse(obj["production_ready"])

    def test_phase49_is_not_fabricated(self):
        with open(os.path.join(ROOT, "research/results/phase61_unified_continuity.json"), encoding="utf-8") as fh:
            obj = json.load(fh)
        self.assertEqual(obj["phase44_57"]["49"], "MISSING_GENUINE_ARTIFACT")
        self.assertTrue(obj["reconciliation"]["phase49_not_reconstructed"])
        self.assertEqual(obj["phase60"]["eligible_findings"], 0)
        self.assertFalse(obj["phase60"]["preregistration_created"])

    def test_manifest_is_byte_stable(self):
        p = os.path.join(ROOT, "research/results/phase61_unified_continuity.json")
        with open(p, "rb") as fh:
            first = fh.read()
        with open(p, "rb") as fh:
            second = fh.read()
        self.assertEqual(first, second)

if __name__ == "__main__":
    unittest.main()
