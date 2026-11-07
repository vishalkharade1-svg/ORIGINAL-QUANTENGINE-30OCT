"""Phase160 regression: release records must describe the bytes actually shipped.

Phase158 installed this contract for its own candidate; Phase159 extended the
same contract to its own record chain.  Phase160 extends it once more, without
touching the earlier contracts or records:

1. a required release record is missing;
2. a current record names the wrong artifact, or embeds the shipped archive's
   own hash (which is unprovable and goes stale the moment the tree changes);
3. a current record points at a report that does not exist;
4. a historical record was rewritten to look current instead of being preserved
   and labelled.

The Phase160 input is the sealed Phase159 hardening-only candidate (sha256
pinned below); the build tree is derived from it and the output candidate is
sealed beside the tree under the names declared here.  In an extracted package
(no archive beside), the detached-record and bundle checks are impossible by
construction; the applicable checks there are non-circularity and record
existence, and the detached-record test skips loudly in that configuration.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_NAME = "QuantEngine_PHASE160_RELEASE_CANDIDATE.zip"
DETACHED_NAME = "RELEASE_HASH_PHASE160.txt"
BUNDLE_NAME = "QuantEngine_PHASE160_POST_BUILD"

INPUT_ARCHIVE = "QuantEngine_PHASE159_RELEASE_CANDIDATE.zip"
INPUT_SHA256 = "015a3be87182bfa34ceeb30d7878c9c40a461dba7f17663a7746df8358ed3674"

PROVENANCE = ROOT / "reports" / "PHASE160_PROVENANCE.json"
GATES = ROOT / "reports" / "PHASE160_RELEASE_GATES.json"

REQUIRED_RECORDS = [
    "NEXT_ACTIONS.md",
    "reports/PHASE160_ARCHIVE_INTEGRITY.json",
    "reports/PHASE160_SOURCE_DIFF.json",
    "reports/PHASE160_GIT_EVIDENCE_STATUS.json",
    "reports/PHASE160_FULL_SUITE_RUN.txt",
    "reports/PHASE160_MANIFEST_AUDIT.json",
    "reports/PHASE160_PROVENANCE.json",
    "reports/PHASE160_SECURITY_SCAN.md",
    "reports/PHASE160_PRIVACY_REVIEW.md",
    "reports/PHASE160_PRIVACY_SCAN.json",
    "reports/PHASE160_DEPENDENCY_REVIEW.md",
    "reports/PHASE160_OSV_SCAN.json",
    "reports/PHASE160_HARDENING.json",
    "reports/PHASE160_RELEASE_GATES.json",
    "reports/PHASE160_BLOCKERS.json",
    "docs/BUILD_HANDOFF_PHASE160.md",
]

# The Phase159 decision records stay byte-identical in this tree; this file
# keeps them from being rewritten to look like Phase160 work.
HISTORICAL_PINS = {
    "reports/PHASE159_RELEASE_GATES.json": {
        "sha256": "7ffe9365f9fa664cfea3eb41fd3bd4efe16d30a9e7730ad9e3af1c611c335203",
        "describes": "the Phase159 gate record, preserved unchanged",
    },
    "reports/PHASE159_HARDENING.json": {
        "sha256": "56c667213c4c35cd0a3e22b53eaee726558135acb68bb8987d7ef490fe1700a6",
        "describes": "the Phase159 hardening repairs, preserved unchanged",
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


class TestReleaseRecords160(unittest.TestCase):
    def test_required_release_records_exist_and_are_not_empty(self):
        missing = [rel for rel in REQUIRED_RECORDS
                   if not (ROOT / rel).exists() or (ROOT / rel).stat().st_size == 0]
        self.assertEqual(missing, [], "missing or empty release records")

    def test_provenance_names_the_input_and_output_archives(self):
        self.assertTrue(PROVENANCE.exists(), "missing %s" % PROVENANCE.name)
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(doc["phase"], 160)
        self.assertEqual(doc["input"]["archive"], INPUT_ARCHIVE)
        self.assertEqual(doc["input"]["sha256"], INPUT_SHA256)
        self.assertEqual(doc["output"]["archive"], ARCHIVE_NAME)
        self.assertEqual(doc["output"]["detached_record"], DETACHED_NAME)

    def test_input_archive_identified_by_hash_if_present_beside_this_tree(self):
        """The declared Phase159 input must be what it claims to be."""
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(doc["input"]["bytes"], 56137390)
        self.assertEqual(doc["input"]["members"], 1868)
        archive = ROOT.parent / INPUT_ARCHIVE
        if not archive.exists():
            self.skipTest("input archive not beside this tree (the Phase159 "
                          "deliverable moved to _phase159_superseded/)")
        self.assertEqual(_sha256(archive), INPUT_SHA256,
                         "the archive beside this tree is not the declared input")

    def test_current_records_do_not_embed_the_shipped_archive_hash(self):
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        declared = doc["output"]["sha256"]
        self.assertTrue(
            declared.startswith("NOT_EMBEDDED"),
            "the output hash must not be embedded inside the archive it "
            "describes; found %r" % declared)
        archive = ROOT.parent / ARCHIVE_NAME
        if not archive.exists():
            return  # pre-pack build tree / extracted package: nothing to compare
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
            self.skipTest("no archive/detached record beside this tree "
                          "(pre-seal build tree or extracted package): the "
                          "non-circularity invariant above is the applicable check")
        text = record.read_text(encoding="utf-8")
        digests = re.findall(r"\b([0-9a-f]{64})\b", text)
        self.assertTrue(digests, "detached record carries no SHA-256")
        self.assertEqual(digests[0], _sha256(archive),
                         "detached record does not describe the archive bytes")
        self.assertIn(ARCHIVE_NAME, text)

    def test_post_build_bundle_carries_the_artifacts_that_describe_the_archive(self):
        """The self-audit and the extracted-package log describe the shipped bytes.

        They cannot live inside the archive (they would describe bytes that did
        not exist when they were written -- the Phase157 staleness defect), so
        they travel beside it in a named bundle."""
        archive = ROOT.parent / ARCHIVE_NAME
        if not archive.exists():
            return  # pre-seal build tree: no bundle is expected inside the tree
        bundle = ROOT.parent / BUNDLE_NAME
        self.assertTrue(bundle.is_dir(), "missing post-build bundle %s" % BUNDLE_NAME)
        for rel in ("README.md",
                    "reports/PHASE160_SELF_AUDIT.md",
                    "reports/PHASE160_EXTRACTED_PACKAGE_TESTS.txt",
                    "reports/PHASE160_POST_BUILD_VERIFICATION.json"):
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
                              "the provenance record must label %s as "
                              "historical" % rel)


if __name__ == "__main__":
    unittest.main()
