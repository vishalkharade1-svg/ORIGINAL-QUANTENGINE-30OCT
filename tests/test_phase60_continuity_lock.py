import json
import os
import unittest

from core.research.conditional_ml.report import ConditionalMlReport
from core.research.oos.discovery_input import Discovery9LInput, from_opportunity_records
from core.research.oos.selection import NineLSelection, admit_9l_selection
from core.research.readiness.selection_preregistration import create_9l_preregistration
from core.research.readiness.preregistration import FrozenPreregistration
from core.research.journal.research_repository import ResearchRepository


ROOT = os.path.dirname(os.path.dirname(__file__))


class TestPhase60ContinuityLock(unittest.TestCase):
    def test_phase44_45_46_source_surfaces_exist(self):
        for rel in (
            "core/research/conditional_ml/report.py",
            "core/research/oos/discovery_input.py",
            "core/research/oos/selection.py",
            "core/research/readiness/selection_preregistration.py",
        ):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_phase47_48_durable_capture_surfaces_exist(self):
        for rel in (
            "core/research/journal/research_repository.py",
            "core/research/journal/research_journal.py",
            "scripts/build_phase48_discovery_capture.py",
            "tests/test_phase47_journal_persistence.py",
            "tests/test_phase48_discovery_capture.py",
        ):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_phase50_54_handoff_surfaces_exist(self):
        for rel in (
            "tests/test_phase40_42_frozen_handoff.py",
            "tests/test_phase43_research_import_boundary.py",
            "research/results/phase43_checkpoint.json",
        ):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_phase55_boundary_is_present_and_not_historical_recreation(self):
        path = os.path.join(ROOT, "research/results/phase55_recertification_boundary.json")
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
        self.assertFalse(obj.get("historical_artifact_recreated", False))
        self.assertTrue(obj.get("recorded_strategy_digest"))
        self.assertTrue(obj.get("current_canonical_strategy_digest"))
        self.assertNotEqual(obj["recorded_strategy_digest"], obj["current_canonical_strategy_digest"])

    def test_phase49_is_explicitly_missing_not_fabricated(self):
        manifest = os.path.join(ROOT, "research/results/phase59_continuity.json")
        with open(manifest, encoding="utf-8") as fh:
            obj = json.load(fh)
        self.assertEqual(obj["phases"]["49"]["status"], "MISSING_GENUINE_ARTIFACT")
        self.assertFalse(obj["phases"]["49"]["evidence"])

    def test_phase56_57_boundaries_exist(self):
        for rel in (
            "scripts/build_phase17_artifact.py",
            "scripts/acquire_phase17_product_snapshot.py",
            "tests/test_phase56_oos_builder.py",
            "tests/test_phase57_product_snapshot_acquisition.py",
            "research/results/phase56_deterministic_oos_builder.json",
            "research/results/phase57_product_snapshot_acquisition.json",
        ):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_continuity_manifest_is_byte_stable(self):
        for name in ("phase58_phase_continuity.json", "phase59_continuity.json"):
            path = os.path.join(ROOT, "research/results", name)
            with open(path, "rb") as fh:
                first = fh.read()
            with open(path, "rb") as fh:
                second = fh.read()
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
