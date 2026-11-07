"""Phase-21 deterministic capture-bundle integrity tests.

These tests use synthetic bundles only.  They prove the verifier rejects
structurally corrupt evidence without claiming any exchange authenticity.
"""

import copy
import unittest

from scripts.verify_delta_global_evidence import (
    canonical_capture_identity,
    verify_capture_integrity,
    verify_single_session,
)
from tests.test_delta_global_evidence_gate_phase1 import _synthetic_global_bundle


class TestDeltaCaptureIntegrityPhase21(unittest.TestCase):
    def test_identity_is_stable_when_local_receipt_clock_changes(self):
        bundle = _synthetic_global_bundle()
        first = canonical_capture_identity(bundle)
        changed = copy.deepcopy(bundle)
        for record in changed["frames"]:
            record["receipt_unix_ns"] = int(record.get("receipt_unix_ns", 0)) + 987654321
        self.assertEqual(first, canonical_capture_identity(changed))

    def test_identity_changes_when_frame_payload_changes(self):
        bundle = _synthetic_global_bundle()
        first = canonical_capture_identity(bundle)
        bundle["frames"][1]["frame"]["c"] = 999
        self.assertNotEqual(first, canonical_capture_identity(bundle))

    def test_non_contiguous_ordinals_fail(self):
        bundle = _synthetic_global_bundle()
        bundle["frames"][1]["receipt_ordinal"] = 9
        checks = verify_capture_integrity(bundle)
        self.assertFalse(next(c for c in checks if c.name == "receipt_ordinals").passed)
        self.assertFalse(verify_single_session(bundle).passed)

    def test_symbol_mismatch_fails(self):
        bundle = _synthetic_global_bundle()
        bundle["frames"][1]["frame"]["sy"] = "ETHUSDT"
        checks = verify_capture_integrity(bundle)
        self.assertFalse(next(c for c in checks if c.name == "frame_payload_integrity").passed)

    def test_nonfinite_candle_fails(self):
        bundle = _synthetic_global_bundle()
        bundle["frames"][1]["frame"]["h"] = float("nan")
        checks = verify_capture_integrity(bundle)
        self.assertFalse(next(c for c in checks if c.name == "frame_payload_integrity").passed)

    def test_negative_volume_fails(self):
        bundle = _synthetic_global_bundle()
        bundle["frames"][1]["frame"]["v"] = -1
        checks = verify_capture_integrity(bundle)
        self.assertFalse(next(c for c in checks if c.name == "frame_payload_integrity").passed)

    def test_declared_identity_mismatch_fails(self):
        bundle = _synthetic_global_bundle()
        bundle["content_identity"] = "0" * 64
        checks = verify_capture_integrity(bundle)
        self.assertFalse(next(c for c in checks if c.name == "content_identity").passed)

    def test_declared_identity_match_passes(self):
        bundle = _synthetic_global_bundle()
        bundle["content_identity"] = canonical_capture_identity(bundle)
        checks = verify_capture_integrity(bundle)
        self.assertTrue(all(c.passed for c in checks), checks)


if __name__ == "__main__":
    unittest.main()
