"""Phase158 regression: private data is confined, declared, and integrity-covered.

Phase157 shipped raw private captures carrying the operator's account id and
venue order ids inside the release ZIP, while reports described the raw captures
as "restricted".  The wording was ambiguous: it could be read as *excluded*,
when in fact they ship deliberately as the evidence of record.

Phase158 states the position precisely and enforces it mechanically:

* the account identifier is allowed in exactly the enumerated raw restricted
  captures and nowhere else;
* raw venue order ids found in the raw captures are split against the input
  archive's inventory: **new leakage** (an aggregate artifact that is not
  byte-identical to its input member) fails, while findings in byte-identical
  sealed historical records are enumerated and reported, never rewritten;
* no credential material and no credential-bearing path is present;
* the restricted captures are covered by the build manifest, so they ship with
  integrity evidence rather than by accident.

A privacy review is not proof of source integrity, and a secret scan is not a
privacy review; each of those gates is reported separately in
reports/PHASE158_SECURITY_SCAN.md and reports/PHASE158_PRIVACY_REVIEW.md.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = ROOT / "scripts" / "security" / "scan_privacy.py"

_spec = importlib.util.spec_from_file_location("phase158_privacy_scan", SCANNER_PATH)
assert _spec is not None and _spec.loader is not None
privacy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = privacy
_spec.loader.exec_module(privacy)

import re

_PRIVACY_NAME = re.compile(r"PHASE(\d+)_PRIVACY_REVIEW\.md$")


def _latest_privacy_review() -> Path:
    found = []
    for path in (ROOT / "reports").glob("PHASE*_PRIVACY_REVIEW.md"):
        match = _PRIVACY_NAME.search(path.name)
        if match:
            found.append((int(match.group(1)), path))
    if not found:
        return ROOT / "reports" / "PHASE158_PRIVACY_REVIEW.md"
    return max(found, key=lambda item: item[0])[1]


PRIVACY_REVIEW = _latest_privacy_review()
MANIFEST = ROOT / "BUILD_MANIFEST.sha256"



class TestPrivacyContract(unittest.TestCase):
    def test_account_identifier_is_confined_to_the_restricted_captures(self):
        violations, carriers = privacy.scan_account_identifier(ROOT)
        self.assertEqual([(v.rule, v.path) for v in violations], [],
                         "the account identifier appears outside the enumerated "
                         "raw restricted captures")
        self.assertEqual(sorted(carriers),
                         sorted(privacy.RESTRICTED_EVIDENCE_PATHS),
                         "the enumerated allowlist no longer matches the files "
                         "that actually carry the identifier")

    def test_no_new_raw_order_id_leaks_into_aggregate_artifacts(self):
        ids = privacy.capture_order_ids(ROOT)
        self.assertTrue(ids, "no raw order ids found: the scan would be vacuous")
        violations = privacy.scan_order_id_leakage(ROOT, ids)
        new, historical = privacy.classify_leakage(ROOT, violations)
        self.assertEqual([(v.rule, v.path) for v in new], [],
                         "a raw venue order id leaked into an aggregate artifact "
                         "that is not a byte-identical historical record")
        self.assertTrue(historical,
                        "the historical baseline is empty: the two-tier "
                        "classification is vacuous and should be removed")
        self.assertGreaterEqual(len({v.path for v in historical}), 1)

    def test_the_historical_order_id_baseline_is_enumerated_in_the_review(self):
        """Sealed records that quote order ids must be visible, not hidden.

        The review enumerates every historical carrier, so a reader sees exactly
        which sealed artifacts would have to be sanitised for a distribution.
        """
        ids = privacy.capture_order_ids(ROOT)
        violations = privacy.scan_order_id_leakage(ROOT, ids)
        _, historical = privacy.classify_leakage(ROOT, violations)
        carriers = sorted({v.path for v in historical})
        text = PRIVACY_REVIEW.read_text(encoding="utf-8")
        for rel in carriers:
            with self.subTest(path=rel):
                self.assertIn(rel, text,
                              "the review must enumerate every historical carrier")

    def test_no_credential_material_in_the_packaged_tree(self):
        violations, rules, operator_local = privacy.scan_secret_material(ROOT)
        # Every detected credential-bearing file outside the documented
        # operator-local set (the root `.env`, excluded from release
        # packaging) is a violation.  The operator-local set itself must be
        # explicitly surfaced, never silently dropped (Phase193B).
        self.assertEqual(
            [(v.rule, v.path) for v in violations], [],
            "credential material detected (rules: %s)" % rules)
        for path in operator_local:
            self.assertEqual(path, ".env")

    def test_no_secret_bearing_paths_in_the_packaged_tree(self):
        violations, operator_local = privacy.scan_secret_paths(ROOT)
        self.assertEqual(
            [(v.rule, v.path) for v in violations], [],
            "a credential-bearing file is present in the release tree")
        for path in operator_local:
            self.assertEqual(path, ".env")

    def test_restricted_captures_are_covered_by_the_build_manifest(self):
        listed = {line.split("  ", 1)[1].strip()
                  for line in MANIFEST.read_text(encoding="utf-8").splitlines()
                  if "  " in line}
        for rel in privacy.RESTRICTED_EVIDENCE_PATHS:
            with self.subTest(path=rel):
                self.assertIn(rel, listed,
                              "restricted evidence must ship with manifest coverage")

    def test_privacy_review_declares_the_allowlist_and_the_package_class(self):
        self.assertTrue(PRIVACY_REVIEW.exists(), "missing privacy review")
        text = PRIVACY_REVIEW.read_text(encoding="utf-8")
        for rel, reason in privacy.RESTRICTED_EVIDENCE_PATHS.items():
            with self.subTest(path=rel):
                self.assertIn(rel, text, "the review must enumerate every path")
                self.assertIn(reason, text, "the review must state why each path is allowed")
        self.assertIn("restricted evidence package", text.lower(),
                      "the review must state what class of package this archive is")

    def test_the_scan_and_review_deny_publication_clearance(self):
        """PRIVACY_SCAN_PASS is a restricted-package verdict, not clearance.

        The independent audit read a green privacy verdict as publication
        clearance.  The scan now states the package class explicitly, and the
        review must carry the same statement.
        """
        report = privacy.run(ROOT)
        self.assertEqual(report["verdict"], "PRIVACY_SCAN_PASS")
        self.assertEqual(report["publication_clearance"], "NOT_CLEARED")
        self.assertTrue(report["publication_clearance_reason"].strip(),
                        "the scan must state why the package is not cleared")
        text = PRIVACY_REVIEW.read_text(encoding="utf-8").lower()
        self.assertIn("publication clearance: none", text,
                      "the review must state that the package is not cleared "
                      "for publication")
        self.assertIn("not cleared for publication", text,
                      "the review must say in plain words that the package is "
                      "not cleared for publication")


class TestPrivacyScannerCanFail(unittest.TestCase):
    """Negative controls: the confinement rule must actually be detectable."""

    def test_identifier_outside_the_allowlist_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reports").mkdir()
            (root / "reports" / "leak.json").write_text(
                '{"user_id": %s}\n' % privacy.ACCOUNT_IDENTIFIER_VALUE, encoding="utf-8")
            violations, carriers = privacy.scan_account_identifier(root)
        self.assertEqual([v.path for v in violations], ["reports/leak.json"])
        self.assertEqual(carriers, ["reports/leak.json"])

    def test_identifier_inside_an_allowlisted_capture_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = next(iter(privacy.RESTRICTED_EVIDENCE_PATHS))
            target = root / rel
            target.parent.mkdir(parents=True)
            target.write_text('{"user_id": %s}\n' % privacy.ACCOUNT_IDENTIFIER_VALUE,
                              encoding="utf-8")
            violations, carriers = privacy.scan_account_identifier(root)
        self.assertEqual(violations, [])
        self.assertEqual(carriers, [rel])

    def test_bom_prefixed_capture_line_is_still_harvested(self):
        """Phase159 regression: a BOM must not hide line 1 of a raw capture.

        The privacy scanner's line reader now decodes with utf-8-sig (same
        hardening as the secret scanner), so a raw venue id on a BOM'd first
        line is still harvested and can still trigger the aggregate rule.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research" / "captures").mkdir(parents=True)
            (root / "research" / "results").mkdir(parents=True)
            (root / "research" / "captures" / "raw.json").write_text(
                '{"order_id": 9000001234}\n', encoding="utf-8-sig")
            self.assertTrue(
                (root / "research" / "captures" / "raw.json")
                .read_bytes().startswith(b"\xef\xbb\xbf"),
                "the fixture must actually carry a UTF-8 BOM")
            ids = privacy.capture_order_ids(root)
        self.assertEqual(ids, {"9000001234": "research/captures/raw.json"})

    def test_raw_order_id_in_an_aggregate_artifact_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research" / "captures").mkdir(parents=True)
            (root / "research" / "results").mkdir(parents=True)
            # fixture id is deliberately synthetic (Phase159 hardening):
            # test fixtures must not carry a real historical venue order id.
            (root / "research" / "captures" / "raw.json").write_text(
                '{"order_id": 9000001234}\n', encoding="utf-8")
            (root / "research" / "results" / "aggregate.json").write_text(
                '{"note": "order 9000001234 matched"}\n', encoding="utf-8")
            ids = privacy.capture_order_ids(root)
            violations = privacy.scan_order_id_leakage(root, ids)
        self.assertEqual(ids, {"9000001234": "research/captures/raw.json"})
        self.assertEqual([v.path for v in violations], ["research/results/aggregate.json"])

    def test_new_aggregate_file_is_not_grandfathered(self):
        """With no inventory entry, a finding is NEW leakage, not history."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research" / "captures").mkdir(parents=True)
            (root / "reports").mkdir()
            (root / "reports" / "PHASE158_INPUT_INVENTORY.sha256").write_text(
                "", encoding="utf-8")
            (root / "research" / "captures" / "raw.json").write_text(
                '{"order_id": 9000001234}\n', encoding="utf-8")
            (root / "reports" / "journal.md").write_text(
                "order 9000001234 filled\n", encoding="utf-8")
            ids = privacy.capture_order_ids(root)
            violations = privacy.scan_order_id_leakage(root, ids)
            new, historical = privacy.classify_leakage(root, violations)
        self.assertEqual([v.path for v in new], ["reports/journal.md"])
        self.assertEqual(historical, [])

    def test_byte_identical_input_member_is_classified_historical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research" / "captures").mkdir(parents=True)
            (root / "reports").mkdir()
            (root / "research" / "captures" / "raw.json").write_text(
                '{"order_id": 9000001234}\n', encoding="utf-8")
            journal = root / "reports" / "journal.md"
            journal.write_text("order 9000001234 filled\n", encoding="utf-8")
            digest = hashlib.sha256(journal.read_bytes()).hexdigest()
            (root / "reports" / "PHASE158_INPUT_INVENTORY.sha256").write_text(
                "%s  reports/journal.md\n" % digest, encoding="utf-8")
            ids = privacy.capture_order_ids(root)
            violations = privacy.scan_order_id_leakage(root, ids)
            new, historical = privacy.classify_leakage(root, violations)
        self.assertEqual(new, [])
        self.assertEqual([v.path for v in historical], ["reports/journal.md"])

    def test_modified_historical_file_is_no_longer_grandfathered(self):
        """Editing a sealed record forfeits its historical classification."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research" / "captures").mkdir(parents=True)
            (root / "reports").mkdir()
            (root / "research" / "captures" / "raw.json").write_text(
                '{"order_id": 9000001234}\n', encoding="utf-8")
            journal = root / "reports" / "journal.md"
            journal.write_text("order 9000001234 filled\n", encoding="utf-8")
            digest = hashlib.sha256(journal.read_bytes()).hexdigest()
            (root / "reports" / "PHASE158_INPUT_INVENTORY.sha256").write_text(
                "%s  reports/journal.md\n" % digest, encoding="utf-8")
            journal.write_text("order 9000001234 filled (edited)\n", encoding="utf-8")
            ids = privacy.capture_order_ids(root)
            violations = privacy.scan_order_id_leakage(root, ids)
            new, historical = privacy.classify_leakage(root, violations)
        self.assertEqual([v.path for v in new], ["reports/journal.md"])
        self.assertEqual(historical, [])

    def test_utf16_capture_and_aggregate_order_ids_are_still_detected(self):
        """Phase160 regression: the declared UTF-16 boundary must be closed.

        The Phase159 vendor-audit handoff declared that UTF-16 members were
        invisible to every content rule.  Both privacy sides are pinned here:
        a BOM'd UTF-16 raw capture must still yield its venue order id, and a
        BOM'd UTF-16 aggregate quoting it must still be reported.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research" / "captures").mkdir(parents=True)
            (root / "research" / "results").mkdir(parents=True)
            capture = root / "research" / "captures" / "raw.json"
            capture.write_bytes('{"order_id": 9000001234}\n'.encode("utf-16"))
            (root / "research" / "results" / "aggregate.json").write_bytes(
                '{"note": "order 9000001234 matched"}\n'.encode("utf-16"))
            self.assertEqual(capture.read_bytes()[:2], b"\xff\xfe",
                             "the fixture must actually carry a UTF-16LE BOM")
            ids = privacy.capture_order_ids(root)
            violations = privacy.scan_order_id_leakage(root, ids)
        self.assertEqual(ids, {"9000001234": "research/captures/raw.json"})
        self.assertEqual([v.path for v in violations],
                         ["research/results/aggregate.json"])

    def test_bomless_utf16_capture_id_is_harvested(self):
        """Phase160: BOM-less UTF-16 LE must not slip through this scanner."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research" / "captures").mkdir(parents=True)
            capture = root / "research" / "captures" / "raw.json"
            capture.write_bytes('{"order_id": 9000001234}\n'.encode("utf-16-le"))
            self.assertFalse(capture.read_bytes().startswith(b"\xff\xfe"),
                             "the fixture must be BOM-less")
            ids = privacy.capture_order_ids(root)
        self.assertEqual(ids, {"9000001234": "research/captures/raw.json"})

    def test_utf16_account_identifier_leak_is_reported(self):
        """Phase160: rule A reads content-decoded text, not suffix-selected
        files, so a UTF-16 aggregate is checked like any other."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reports").mkdir()
            (root / "reports" / "leak.json").write_bytes(
                ('{"user_id": %s}\n' % privacy.ACCOUNT_IDENTIFIER_VALUE)
                .encode("utf-16"))
            violations, carriers = privacy.scan_account_identifier(root)
        self.assertEqual([v.path for v in violations], ["reports/leak.json"])
        self.assertEqual(carriers, ["reports/leak.json"])

    def test_undeclared_opaque_member_fails_the_coverage_rule(self):
        """Rule E (Phase160): binary members must be declared, not skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes.txt").write_text("plain text\n", encoding="utf-8")
            (root / "blob.bin").write_bytes(bytes(range(256)) * 4)
            inspected, declared, undeclared = privacy.scan_content_coverage(root)
        self.assertEqual(inspected, 1)
        self.assertEqual(declared, [])
        self.assertEqual([v.rule for v in undeclared],
                         ["opaque_member_not_declared"])
        self.assertEqual([v.path for v in undeclared], ["blob.bin"])

    def test_declared_opaque_classes_are_reported_not_failed(self):
        """A binary member inside a declared class is enumerated, not a
        violation: the classes ship integrity-covered by the manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bundle.zip").write_bytes(bytes(range(256)) * 4)
            inspected, declared, undeclared = privacy.scan_content_coverage(root)
        self.assertEqual(inspected, 0)
        self.assertEqual(declared, ["bundle.zip"])
        self.assertEqual(undeclared, [])


if __name__ == "__main__":
    unittest.main()
