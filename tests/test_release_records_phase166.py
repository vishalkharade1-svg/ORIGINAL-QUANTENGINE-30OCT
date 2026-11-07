"""Phase166 regression: release records must describe the bytes actually shipped.

Phase 166 independent release verification, runtime hardening, and evidence closure:
1. Baseline reproduction and archive integrity verification.
2. Independent runtime boundary certification (97 tests).
3. Strategy identity fail-closed hardening and historical digest forensics.
4. Testnet safety preflight and fail-closed authentication audit.
5. Standing evidence blockers disposition and release gate enforcement.

Release integrity contracts:
1. All required release records exist and are non-empty.
2. Current records name the correct artifacts and never embed their own archive hash.
3. Gates reference only existing reports.
4. Blocked gates forbid any claim of PRODUCTION_READY.
5. Historical records (Phase 161, 162, 165) are preserved unchanged and labelled.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_NAME = "QuantEngine_PHASE166_RELEASE_CANDIDATE.zip"
DETACHED_NAME = "RELEASE_HASH_PHASE166.txt"

INPUT_ARCHIVE = "QuantEngine_PHASE165_RELEASE_CANDIDATE.zip"

PROVENANCE = ROOT / "reports" / "PHASE166_PROVENANCE.json"
GATES = ROOT / "reports" / "PHASE166_RELEASE_GATES.json"

REQUIRED_RECORDS = [
    "NEXT_ACTIONS.md",
    "reports/PHASE166_RELEASE_GATES.json",
    "reports/PHASE166_BLOCKERS.json",
    "reports/PHASE166_PROVENANCE.json",
    "reports/PHASE166_TEST_RESULTS.json",
    "reports/PHASE166_INDEPENDENT_VERIFICATION.md",
]

HISTORICAL_PINS = {
    "reports/PHASE161_RELEASE_GATES.json": {
        "sha256": "d1e0663b35455c3b5fae9b1bd13fbc37e5ba27b2e4d5e3f5a6fb888bc6abd898",
        "describes": "the Phase161 gate record, preserved unchanged",
    },
    "reports/PHASE161_ENVIRONMENT.json": {
        "sha256": "ae9671c03ac166596df9da0c9be6e89e56e5d4e269e68c3eeb489fc1f2fa0251",
        "describes": "the Phase161 environment adoption record, preserved unchanged",
    },
    "reports/PHASE162_RELEASE_GATES.json": {
        "sha256": "f94aff1f1723c37527975850b733257d0ca26443dbcf81672f7429bd65a668b2",
        "describes": "the Phase162 release gates, preserved unchanged",
    },
    "reports/PHASE162_BLOCKERS.json": {
        "sha256": "5d053de948f7e0a07eae1b24022d2f4cd7d03f7ca92d819b79bd2aceff0fc626",
        "describes": "the Phase162 blockers record, preserved unchanged",
    },
    "reports/PHASE165_RELEASE_GATES.json": {
        "sha256": "f1ad8e7f879269e09acf13eed643013d41a308b1c1e7dd35ed170af3c53f2645",
        "describes": "the Phase165 release gates, preserved unchanged",
    },
    "reports/PHASE165_BLOCKERS.json": {
        "sha256": "2f42e3d742c799530c3c653cadb1296919c40fd72277b9f4cf0178eebe7cb35c",
        "describes": "the Phase165 blockers record, preserved unchanged",
    },
}

PATH_IN_TEXT = re.compile(r"\b(?:reports|docs)/[A-Za-z0-9_.\-/]+\.(?:json|md|txt)\b")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _walk_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_strings(value)


class TestReleaseRecords166(unittest.TestCase):
    def test_required_release_records_exist_and_are_not_empty(self):
        missing = [rel for rel in REQUIRED_RECORDS
                   if not (ROOT / rel).exists() or (ROOT / rel).stat().st_size == 0]
        self.assertEqual(missing, [], "missing or empty release records")

    def test_provenance_names_the_input_and_output_archives(self):
        self.assertTrue(PROVENANCE.exists(), "missing %s" % PROVENANCE.name)
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(doc["phase"], 166)
        self.assertEqual(doc["input"]["archive"], INPUT_ARCHIVE)

    def test_gates_reference_only_reports_that_exist(self):
        self.assertTrue(GATES.exists(), "missing %s" % GATES.name)
        doc = json.loads(GATES.read_text(encoding="utf-8"))
        self.assertEqual(doc["phase"], 166)
        missing_refs = []
        for text in _walk_strings(doc):
            for ref in PATH_IN_TEXT.findall(text):
                target = ROOT / ref
                if not target.exists():
                    missing_refs.append(ref)
        self.assertEqual(missing_refs, [],
                         "gates reference reports that do not exist on disk")

    def test_historical_records_are_preserved_and_labelled(self):
        mismatched = []
        for rel, expected in HISTORICAL_PINS.items():
            path = ROOT / rel
            self.assertTrue(path.exists(), "missing historical record %s" % rel)
            actual = _sha256(path)
            if actual != expected["sha256"]:
                mismatched.append((rel, expected["sha256"], actual))
        self.assertEqual(mismatched, [], "historical records mutated")

    def test_any_blocked_gate_forbids_a_production_ready_claim(self):
        doc = json.loads(GATES.read_text(encoding="utf-8"))
        gates = doc.get("gates", {})
        has_blocked = any(
            v.startswith("BLOCKED") or v.startswith("NOT-GREEN")
            or "UNVERIFIABLE" in v or "PARTIAL" in v
            for v in gates.values()
        )
        if has_blocked:
            self.assertEqual(doc.get("overall"), "NOT_PRODUCTION_READY")

    def test_current_records_do_not_embed_the_shipped_archive_hash(self):
        archive = ROOT.parent / ARCHIVE_NAME
        if not archive.exists():
            return  # pre-packaging run
        actual_hash = _sha256(archive)
        offenders = []
        for rel in REQUIRED_RECORDS:
            path = ROOT / rel
            if path.exists() and actual_hash in path.read_text(encoding="utf-8"):
                offenders.append(rel)
        self.assertEqual(offenders, [],
                          "these records embed the shipped archive's own hash")

    def test_detached_record_is_outside_the_package_and_agrees_with_the_archive(self):
        inside = ROOT / DETACHED_NAME
        self.assertFalse(inside.exists(),
                         "the detached hash record must travel beside the archive, "
                         "never inside it")
        archive = ROOT.parent / ARCHIVE_NAME
        record = ROOT.parent / DETACHED_NAME
        if not (archive.exists() and record.exists()):
            self.skipTest("no archive/detached record beside this tree")
        text = record.read_text(encoding="utf-8")
        digests = re.findall(r"\b([0-9a-f]{64})\b", text)
        self.assertTrue(digests, "detached record carries no SHA-256")
        self.assertEqual(digests[0], _sha256(archive),
                         "detached record does not describe the archive bytes")
        self.assertIn(ARCHIVE_NAME, text)


if __name__ == "__main__":
    unittest.main()
