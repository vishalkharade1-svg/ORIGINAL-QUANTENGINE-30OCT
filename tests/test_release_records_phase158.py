"""Phase158 regression: release records must describe the bytes actually shipped.

Phase157 shipped a self-audit that described a *superseded* build (1,817 members,
sha256 72fe28e0...) while the packaged archive was a later 1,820-member rebuild,
and it shipped a provenance record named generically (``RELEASE_PROVENANCE.json``)
whose content was the Phase132 record.  Both were stale evidence about the
artifact they travelled with -- the exact defect class Phase158 exists to repair.

This contract makes the four failure modes detectable:

1. a required release record is missing;
2. a current record names the wrong artifact, or embeds the shipped archive's own
   hash (which is unprovable and goes stale the moment the tree changes);
3. a current record points at a report that does not exist;
4. a historical record was rewritten to look current instead of being preserved
   and labelled.

The detached hash record lives *outside* the packaged tree on purpose, so it is
never checked into the archive it describes.  In a build tree this test
cross-checks it against the real archive bytes; in an extracted package it
asserts the record was not smuggled inside instead.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_NAME = "QuantEngine_PHASE158_RELEASE_CANDIDATE.zip"
DETACHED_NAME = "RELEASE_HASH_PHASE158.txt"
BUNDLE_NAME = "QuantEngine_PHASE158_POST_BUILD"
INPUT_ARCHIVE = "QuantEngine_PHASE157_RELEASE_CANDIDATE.zip"
INPUT_SHA256 = "d43051a468e7d91d4a2be6b1cfe484fc0a13ac7f6d3fea6735c7b494ccfb00ad"

PROVENANCE = ROOT / "reports" / "PHASE158_PROVENANCE.json"
GATES = ROOT / "reports" / "PHASE158_RELEASE_GATES.json"

REQUIRED_RECORDS = [
    "reports/PHASE158_BASELINE_INVENTORY.md",
    "reports/PHASE158_ARCHIVE_INTEGRITY.json",
    "reports/PHASE158_SOURCE_DIFF.json",
    "reports/PHASE158_HASH_FAILURE_TRIAGE.json",
    "reports/PHASE158_GIT_EVIDENCE_STATUS.json",
    "reports/PHASE158_FULL_SUITE_RUN.txt",
    "reports/PHASE158_MANIFEST_AUDIT.json",
    "reports/PHASE158_PROVENANCE.json",
    "reports/PHASE158_SECURITY_SCAN.md",
    "reports/PHASE158_PRIVACY_REVIEW.md",
    "reports/PHASE158_DEPENDENCY_REVIEW.md",
    "reports/PHASE158_RELEASE_GATES.json",
    "reports/PHASE158_BLOCKERS.json",
    "reports/PHASE158_SNAPSHOT_AUDIT.md",
    "reports/PHASE158_AUDIT_REPAIRS.json",
    "docs/BUILD_HANDOFF_PHASE158.md",
    "docs/CLAUDE_PHASE158_INDEPENDENT_AUDIT_PROMPT.md",
    "NEXT_ACTIONS.md",
]

# Historical records that must survive byte-for-byte, with the build each one
# actually describes.  Rewriting them to look current is forbidden; the Phase158
# provenance record is where the trace lives instead.
HISTORICAL_PINS = {
    "reports/PHASE157_SELF_AUDIT.md": {
        "sha256": "b83553cb914ab26e58492fab8cf291beefc9859335eb886edaa421ac598774a4",
        "describes": "the superseded 1,817-member Phase157 build "
                     "(sha256 72fe28e0f0362d9ba717f4d4ffc2f869f0f402a5d844f70bf365542381bd7002)",
    },
}

# Provenance records renamed to phase-specific names, bytes unchanged.
RENAMED_RECORDS = {
    "reports/RELEASE_PROVENANCE_PHASE132.json": {
        "former_name": "reports/RELEASE_PROVENANCE.json",
        "sha256": "05df5fa91b4c0350aedf905f09eb3cdbc96d15abdfbed2876fbfa825f36e985e",
        "why": "the generic name made a Phase132 record ambiguous beside current "
               "release reports",
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


class TestReleaseRecords(unittest.TestCase):
    def test_required_release_records_exist_and_are_not_empty(self):
        missing = [rel for rel in REQUIRED_RECORDS
                   if not (ROOT / rel).exists() or (ROOT / rel).stat().st_size == 0]
        self.assertEqual(missing, [], "missing or empty release records")

    def test_provenance_names_the_input_and_output_archives(self):
        self.assertTrue(PROVENANCE.exists(), "missing %s" % PROVENANCE.name)
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(doc["phase"], 158)
        self.assertEqual(doc["input"]["archive"], INPUT_ARCHIVE)
        self.assertEqual(doc["input"]["sha256"], INPUT_SHA256)
        self.assertEqual(doc["output"]["archive"], ARCHIVE_NAME)
        self.assertEqual(doc["output"]["detached_record"], DETACHED_NAME)

    def test_current_records_do_not_embed_the_shipped_archive_hash(self):
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        declared = doc["output"]["sha256"]
        self.assertTrue(
            declared.startswith("NOT_EMBEDDED"),
            "the output hash must not be embedded inside the archive it "
            "describes; found %r" % declared)
        archive = ROOT.parent / ARCHIVE_NAME
        if not archive.exists():
            return  # extracted package: nothing further to compare against
        actual = _sha256(archive)
        offenders = []
        for rel in REQUIRED_RECORDS:
            path = ROOT / rel
            if not path.exists() or path.name == ARCHIVE_NAME:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:  # pragma: no cover
                continue
            if actual in text:
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
            self.skipTest("no archive/detached record beside this tree (extracted "
                          "package): the non-circularity invariant above is the "
                          "applicable check here")
        text = record.read_text(encoding="utf-8")
        digests = re.findall(r"\b([0-9a-f]{64})\b", text)
        self.assertTrue(digests, "detached record carries no SHA-256")
        self.assertEqual(digests[0], _sha256(archive),
                         "detached record does not describe the archive bytes")
        self.assertIn(ARCHIVE_NAME, text)

    def test_post_build_bundle_carries_the_artifacts_that_describe_the_archive(self):
        """The self-audit and the extracted-package log describe the shipped bytes.

        They cannot live inside the archive (they would describe bytes that did
        not exist when they were written -- exactly the Phase157 staleness defect),
        so they travel beside it in a named bundle."""
        archive = ROOT.parent / ARCHIVE_NAME
        if not archive.exists():
            return  # extracted package: no bundle is expected inside the tree
        bundle = ROOT.parent / BUNDLE_NAME
        self.assertTrue(bundle.is_dir(), "missing post-build bundle %s" % BUNDLE_NAME)
        for rel in ("README.md",
                    "reports/PHASE158_SELF_AUDIT.md",
                    "reports/PHASE158_EXTRACTED_PACKAGE_TESTS.txt",
                    "reports/PHASE158_POST_BUILD_VERIFICATION.json"):
            with self.subTest(entry=rel):
                path = bundle / rel
                self.assertTrue(path.exists(), "missing bundle entry %s" % rel)
                self.assertGreater(path.stat().st_size, 0)
        readme = (bundle / "README.md").read_text(encoding="utf-8")
        self.assertIn(ARCHIVE_NAME, readme)
        self.assertIn(DETACHED_NAME, readme)

    def test_gates_reference_only_reports_that_exist(self):
        doc = json.loads(GATES.read_text(encoding="utf-8"))
        referenced = set()
        for text in _walk_strings(doc):
            referenced.update(PATH_IN_TEXT.findall(text))
        missing = sorted(rel for rel in referenced if not (ROOT / rel).exists())
        self.assertEqual(missing, [],
                         "release gates reference records that do not exist")

    def test_any_blocked_gate_forbids_a_production_ready_claim(self):
        doc = json.loads(GATES.read_text(encoding="utf-8"))
        gates = {k: v for k, v in doc["gates"].items() if isinstance(v, str)}
        blocked = {k: v for k, v in gates.items() if not v.startswith("PASS")}
        if blocked:
            self.assertNotEqual(
                doc.get("overall"), "PRODUCTION_READY",
                "a release with non-passing gates must not claim "
                "PRODUCTION_READY: %s" % sorted(blocked))

    def test_historical_records_are_preserved_and_labelled(self):
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        historical = doc.get("historical_records", {})
        for rel, pin in HISTORICAL_PINS.items():
            path = ROOT / rel
            with self.subTest(record=rel):
                self.assertTrue(path.exists(), "%s was removed" % rel)
                self.assertEqual(
                    _sha256(path), pin["sha256"],
                    "%s was rewritten; historical records must survive "
                    "byte-for-byte and be labelled instead" % rel)
                self.assertIn(rel, historical,
                              "the provenance record must label %s as historical" % rel)
                self.assertIn(pin["describes"], json.dumps(historical[rel]),
                              "the label must state which build the record describes")
        for rel, record in RENAMED_RECORDS.items():
            path = ROOT / rel
            with self.subTest(record=rel):
                self.assertTrue(path.exists(), "%s is missing" % rel)
                self.assertFalse((ROOT / record["former_name"]).exists(),
                                 "the ambiguous former name is still present")
                self.assertEqual(_sha256(path), record["sha256"],
                                 "%s was modified while being renamed" % rel)
                self.assertIn(rel, historical,
                              "the renamed record must be labelled historical too")


if __name__ == "__main__":
    unittest.main()
