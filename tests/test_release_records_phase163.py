"""Phase163 regression: release records must describe the bytes actually shipped.

Phase 163 builds the remaining QuantEngine core components:
1. Multi-instrument feed multiplexer and cross-symbol state isolation (core/runtime/multi_stream_multiplexer.py)
2. Protective bracket orders and trailing stop latency simulation (core/execution/protective_bracket.py)
3. Authenticated mobile push and telemetry broadcast gateway (core/monitoring/mobile_push_gateway.py)

Release integrity contracts:
1. All required release records exist and are non-empty.
2. Current records name the correct artifacts and never embed their own archive hash.
3. Gates reference only existing reports.
4. Blocked gates forbid any claim of PRODUCTION_READY.
5. Historical records (Phase 161 and Phase 162) are preserved unchanged and labelled.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_NAME = "QuantEngine_PHASE163_RELEASE_CANDIDATE.zip"
DETACHED_NAME = "RELEASE_HASH_PHASE163.txt"
BUNDLE_NAME = "QuantEngine_PHASE163_POST_BUILD"

INPUT_ARCHIVE = "QuantEngine_PHASE162_RELEASE_CANDIDATE.zip"

PROVENANCE = ROOT / "reports" / "PHASE163_PROVENANCE.json"
GATES = ROOT / "reports" / "PHASE163_RELEASE_GATES.json"

REQUIRED_RECORDS = [
    "NEXT_ACTIONS.md",
    "reports/PHASE163_RELEASE_GATES.json",
    "reports/PHASE163_BLOCKERS.json",
    "reports/PHASE163_PROVENANCE.json",
    "reports/PHASE163_SOURCE_DIFF.json",
    "reports/PHASE163_GIT_EVIDENCE_STATUS.json",
    "reports/PHASE163_FULL_SUITE_RUN.txt",
    "reports/PHASE163_SECURITY_SCAN.md",
    "reports/PHASE163_PRIVACY_REVIEW.md",
    "reports/PHASE163_ARCHITECTURE_AUDIT.md",
    "reports/PHASE163_MULTI_INSTRUMENT_AUDIT.md",
    "reports/PHASE163_PROTECTIVE_ORDERS_AUDIT.md",
    "reports/PHASE163_MOBILE_TELEMETRY_AUDIT.md",
    "reports/PHASE163_DOCUMENTATION_RECONCILIATION.md",
    "docs/BUILD_HANDOFF_PHASE163.md",
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


class TestReleaseRecords163(unittest.TestCase):
    def test_required_release_records_exist_and_are_not_empty(self):
        missing = [rel for rel in REQUIRED_RECORDS
                   if not (ROOT / rel).exists() or (ROOT / rel).stat().st_size == 0]
        self.assertEqual(missing, [], "missing or empty release records")

    def test_provenance_names_the_input_and_output_archives(self):
        self.assertTrue(PROVENANCE.exists(), "missing %s" % PROVENANCE.name)
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(doc["phase"], 163)
        self.assertEqual(doc["input"]["archive"], INPUT_ARCHIVE)
        self.assertEqual(doc["output"]["archive"], ARCHIVE_NAME)
        self.assertEqual(doc["output"]["detached_record"], DETACHED_NAME)

    def test_current_records_do_not_embed_the_shipped_archive_hash(self):
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        declared = doc["output"]["sha256"]
        self.assertTrue(
            declared.startswith("NOT_EMBEDDED"),
            "the output hash must not be embedded inside the archive it describes; found %r" % declared)
        archive = ROOT.parent / ARCHIVE_NAME
        if not archive.exists():
            return  # pre-pack build tree
        actual = _sha256(archive)
        offenders = []
        for rel in REQUIRED_RECORDS:
            path = ROOT / rel
            if not path.exists() or path.name == ARCHIVE_NAME:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if actual in text:
                offenders.append(rel)
        self.assertEqual(offenders, [], "these records embed the shipped archive's own hash")

    def test_gates_reference_only_reports_that_exist(self):
        doc = json.loads(GATES.read_text(encoding="utf-8"))
        referenced = set()
        for text in _walk_strings(doc):
            referenced.update(PATH_IN_TEXT.findall(text))
        missing = sorted(rel for rel in referenced if not (ROOT / rel).exists())
        self.assertEqual(missing, [], "release gates reference records that do not exist")

    def test_any_blocked_gate_forbids_a_production_ready_claim(self):
        doc = json.loads(GATES.read_text(encoding="utf-8"))
        gates = {k: v for k, v in doc["gates"].items() if isinstance(v, str)}
        blocked = {k: v for k, v in gates.items() if not v.startswith("PASS")}
        if blocked:
            self.assertNotEqual(
                doc.get("overall"), "PRODUCTION_READY",
                "a release with non-passing gates must not claim PRODUCTION_READY: %s" % sorted(blocked))

    def test_historical_records_are_preserved_and_labelled(self):
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        historical = doc.get("historical_records", {})
        for rel, pin in HISTORICAL_PINS.items():
            path = ROOT / rel
            with self.subTest(record=rel):
                self.assertTrue(path.exists(), "%s was removed" % rel)
                self.assertEqual(
                    _sha256(path), pin["sha256"],
                    "%s was rewritten; historical records must survive byte-for-byte" % rel)
                self.assertIn(rel, historical,
                              "the provenance record must label %s as historical" % rel)


if __name__ == "__main__":
    unittest.main()
