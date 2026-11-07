"""Phase-23 deterministic public-capture fixture contracts."""

from __future__ import annotations

import copy
import unittest

from scripts.capture_delta_public_frames import (
    control_frame_summary,
    deterministic_fixture,
)
from tests.test_delta_global_evidence_gate_phase1 import _synthetic_global_bundle


class TestDeltaCaptureFixturePhase23(unittest.TestCase):
    def test_control_frame_summary_is_deterministic(self):
        bundle = _synthetic_global_bundle()
        summary = control_frame_summary(bundle)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["types"], {"subscriptions": 1})

    def test_fixture_drops_local_capture_clock(self):
        first = deterministic_fixture(_synthetic_global_bundle())
        changed = copy.deepcopy(_synthetic_global_bundle())
        changed["started_unix"] = 9999999999.0
        for record in changed["frames"]:
            record["receipt_unix_ns"] = 1234567890123456789
        second = deterministic_fixture(changed)
        self.assertEqual(first, second)

    def test_fixture_identity_changes_with_public_payload(self):
        bundle = _synthetic_global_bundle()
        first = deterministic_fixture(bundle)
        bundle["frames"][1]["frame"]["c"] = 777
        second = deterministic_fixture(bundle)
        self.assertNotEqual(first["fixture_identity"], second["fixture_identity"])

    def test_fixture_retains_control_frames_and_summary(self):
        fixture = deterministic_fixture(_synthetic_global_bundle())
        controls = [r for r in fixture["frames"] if r["classification"] == "control_or_unrequested"]
        self.assertEqual(len(controls), 1)
        self.assertEqual(fixture["control_frame_summary"], {"total": 1, "types": {"subscriptions": 1}})

    def test_fixture_is_explicitly_not_authenticity_evidence(self):
        fixture = deterministic_fixture(_synthetic_global_bundle())
        self.assertTrue(any("not venue authenticity" in x for x in fixture["limitations"]))


if __name__ == "__main__":
    unittest.main()
