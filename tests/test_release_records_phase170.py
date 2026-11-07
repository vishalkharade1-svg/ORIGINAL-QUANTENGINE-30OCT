"""Phase 170 regression: release records must describe the bytes actually shipped.

Phase 170 independent Phase 169 audit, timestamp provenance & historical strategy lineage:
1. Baseline reproduction and archive integrity verification for Phase 169 candidate.
2. Full forensic investigation and mathematical resolution of the 1760805669389773 timestamp discrepancy.
3. Hardened execution economics verifier with microsecond unit checks, UTC year bounds, and cross-leg chronology.
4. Deterministic offline L2 execution replay study across order sizes and market depth.
5. Maintenance of standing external blockers and release gate enforcement.

Release integrity contracts:
1. All required release records exist and are non-empty.
2. Current records name the correct artifacts and never embed their own archive hash.
3. Gates reference only existing reports.
4. Blocked gates forbid any claim of PRODUCTION_READY.
5. Historical records (Phase 161, 162, 165, 166, 167, 168, 169) are preserved unchanged and labelled.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

from core.research.strategy_identity import get_versioned_identities

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_NAME = "QuantEngine_PHASE170_RELEASE_CANDIDATE.zip"
DETACHED_NAME = "RELEASE_HASH_PHASE170.txt"

INPUT_ARCHIVE = "QuantEngine_PHASE169_RELEASE_CANDIDATE.zip"
INPUT_ARCHIVE_SHA256 = "be9b0c0d9f307669a9888690432d0c9dd025dc25919cc9917d4151346971b989"

PROVENANCE = ROOT / "reports" / "PHASE170_PROVENANCE.json"
GATES = ROOT / "reports" / "PHASE170_RELEASE_GATES.json"

REQUIRED_RECORDS = [
    "NEXT_ACTIONS.md",
    "reports/PHASE170_RELEASE_GATES.json",
    "reports/PHASE170_BLOCKERS.json",
    "reports/PHASE170_PROVENANCE.json",
    "reports/PHASE170_TEST_RESULTS.json",
    "reports/PHASE170_PRIVACY_REVIEW.md",
    "reports/PHASE170_RECONCILIATION_RESULTS.json",
    "reports/PHASE170_TIMESTAMP_PROVENANCE.md",
    "reports/PHASE170_FINDINGS.json",
    "reports/PHASE170_INDEPENDENT_AUDIT.md",
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
    "reports/PHASE166_RELEASE_GATES.json": {
        "sha256": "ab75204d1799fd71046a5acdc124f2d2bc41908743887a692c7cd920a5b35aca",
        "describes": "the Phase166 release gates, preserved unchanged",
    },
    "reports/PHASE166_BLOCKERS.json": {
        "sha256": "ce30bc50027f3e24ccc0c98eebbf8384d1e1e50819cc0e36a7da75a52691e4d1",
        "describes": "the Phase166 blockers record, preserved unchanged",
    },
    "reports/PHASE166_PROVENANCE.json": {
        "sha256": "641ad10fb2ab00c1cea16c666d39c21fecac6ad4556fc3c8e20745880152477a",
        "describes": "the Phase166 provenance record, preserved unchanged",
    },
    "reports/PHASE166_INDEPENDENT_VERIFICATION.md": {
        "sha256": "53be987581c046a43dbd47f7de359a9e67f9d150dd13888cf197318cef3a980f",
        "describes": "the Phase166 independent verification report, preserved unchanged",
    },
    "reports/PHASE167_RELEASE_GATES.json": {
        "sha256": "1876030542a73ed2a73fa5407834ffcf0148879c243cc371ca917a97a0eaeacb",
        "describes": "the Phase167 release gates, preserved unchanged",
    },
    "reports/PHASE167_BLOCKERS.json": {
        "sha256": "d8c84303a15bcb557cb0b7479ac1dafaf9cf0706d6ba78127bceace0204cb4b7",
        "describes": "the Phase167 blockers record, preserved unchanged",
    },
    "reports/PHASE167_PROVENANCE.json": {
        "sha256": "9201165f7440ef37118167fe98dc73a2de492583d1ee00e5f225c86ebec045b7",
        "describes": "the Phase167 provenance record, preserved unchanged",
    },
    "reports/PHASE167_INDEPENDENT_AUDIT.md": {
        "sha256": "d5e3e2aaf11c20c7cac7f685748197bceef5aaf2a9a82197570a48d34ed4b965",
        "describes": "the Phase167 independent audit report, preserved unchanged",
    },
    "reports/PHASE168_RELEASE_GATES.json": {
        "sha256": "b4f06d1785e552783322aefb130d5edaf908f6f4fa30c512e99bbaf2f97418f9",
        "describes": "the Phase168 release gates, preserved unchanged",
    },
    "reports/PHASE168_BLOCKERS.json": {
        "sha256": "7eefafddd04393e1c590926b2b41f42fd0aadb256fed19c9ebd730f6fb8680e5",
        "describes": "the Phase168 blockers record, preserved unchanged",
    },
    "reports/PHASE168_PROVENANCE.json": {
        "sha256": "7f0e438fc13d916c2ce5187c6e1ecca3967025505b0f8229d694e85c7f348a04",
        "describes": "the Phase168 provenance record, preserved unchanged",
    },
    "reports/PHASE168_EXECUTION_ECONOMICS_RECONCILIATION.md": {
        "sha256": "b340f656267b092ed253acd522d4873ebe3169e57ff0642059b3c72babedb0d1",
        "describes": "the Phase168 execution economics reconciliation report, preserved unchanged",
    },
    "reports/PHASE168_PRIVACY_REVIEW.md": {
        "sha256": "d042517690d53221371276485c6df38ccb7c7a00a57fd34a1c80e082b0de5975",
        "describes": "the Phase168 privacy review, preserved unchanged",
    },
    "reports/PHASE168_TEST_RESULTS.json": {
        "sha256": "16713344d4fe31546899f91a26d59145febbd75cd2a5b37a87edd72f749ab09f",
        "describes": "the Phase168 test results, preserved unchanged",
    },
    "reports/PHASE168_STRATEGY_HISTORICAL_RECONSTRUCTION.md": {
        "sha256": "4c343dc75bff7cd8fd4cdd1832791ea142243a9e70e062b9c3759e588e8a4638",
        "describes": "the Phase168 strategy historical reconstruction report, preserved unchanged",
    },
    "reports/PHASE169_RELEASE_GATES.json": {
        "sha256": "1a784fef71eb402595033062212095876f660decb26926fee053a6f08fc22fab",
        "describes": "the Phase169 release gates, preserved unchanged",
    },
    "reports/PHASE169_BLOCKERS.json": {
        "sha256": "939c97aa742a65ab9038127bfff10aa3aea0f3f0097d34bc550671eb02d66554",
        "describes": "the Phase169 blockers record, preserved unchanged",
    },
    "reports/PHASE169_PROVENANCE.json": {
        "sha256": "ff89e8ed17c842212796612e6e26be9110910e0f88939aebb5be2208b3b1d2e0",
        "describes": "the Phase169 provenance record, preserved unchanged",
    },
    "reports/PHASE169_TEST_RESULTS.json": {
        "sha256": "162964eeef3736ac2409d912c7c2d14a81de7aa8a892ce27e24a7346263a73c3",
        "describes": "the Phase169 test results, preserved unchanged",
    },
    "reports/PHASE169_PRIVACY_REVIEW.md": {
        "sha256": "712be004dc2dffd707d66d21b4c3521805e7c4d62601e7beeb7400a418a5baaf",
        "describes": "the Phase169 privacy review, preserved unchanged",
    },
    "reports/PHASE169_EXECUTION_ECONOMICS_RECONCILIATION.md": {
        "sha256": "1c53d138c0f29bde9c37325af4c777b3961d11d14a4e0a9759b7ec932d44eed4",
        "describes": "the Phase169 execution economics reconciliation report, preserved unchanged",
    },
    "reports/PHASE169_INDEPENDENT_AUDIT.md": {
        "sha256": "d0f4c9589ab761d35a04fb1146331a29b578b11588e963c5bd8422b270dacc00",
        "describes": "the Phase169 independent audit report, preserved unchanged",
    },
}

PATH_IN_TEXT = re.compile(r"\b(?:reports|docs)/[A-Za-z0-9_.\-/]+\.(?:json|md|txt)\b")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestReleaseRecords170(unittest.TestCase):
    def test_required_release_records_exist_and_are_not_empty(self):
        for rel in REQUIRED_RECORDS:
            p = ROOT / rel
            self.assertTrue(p.exists(), f"missing required record: {rel}")
            self.assertGreater(p.stat().st_size, 0, f"empty record: {rel}")

    def test_gates_reference_only_reports_that_exist(self):
        text = GATES.read_text(encoding="utf-8")
        candidates = PATH_IN_TEXT.findall(text)
        self.assertTrue(candidates, "no report paths found in release gates")
        missing = [c for c in candidates if not (ROOT / c).exists()]
        self.assertEqual(missing, [],
                          f"release gates reference non-existent files: {missing}")

    def test_provenance_names_the_input_and_output_archives(self):
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(doc.get("input_archive", {}).get("name"), INPUT_ARCHIVE)
        self.assertEqual(doc.get("input_archive", {}).get("sha256"), INPUT_ARCHIVE_SHA256)
        self.assertEqual(doc.get("output_archive", {}).get("name"), ARCHIVE_NAME)

    def test_historical_records_are_preserved_and_labelled(self):
        for rel, meta in HISTORICAL_PINS.items():
            path = ROOT / rel
            self.assertTrue(path.exists(), f"historical record removed: {rel}")
            actual = _sha256(path)
            self.assertEqual(actual, meta["sha256"],
                             f"historical record mutated: {rel} ({meta['describes']})")

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

    def test_versioned_strategy_identity_invariants(self):
        identities = get_versioned_identities(ROOT)
        # Phase 22 re-registration: the versioned composites advanced with
        # the delivered worktree (frozen-era OOS semantics restored; all
        # recorded OOS funnels reproduce). Provenance:
        # reports/PHASE22_STRATEGY_IDENTITY_BASELINE.json - the historical
        # Phase 14 pin (c52e648c...) remains the authority.
        self.assertEqual(
            identities["strategy_core"]["sha256"],
            "26c2bead8c4599b78c64281a3d2860e194f16603c950840df199c953fcfc9666"
        )
        self.assertEqual(
            identities["runtime_infrastructure"]["sha256"],
            "997a21f21045551ed25e29d2289157d257b16b5f3b99bbf04e95c7f257b96294"
        )
        self.assertEqual(
            identities["composite_legacy_9_files"]["canonical_lf_sha256"],
            "05986916c990dbda8329b7fa8230ced878f951c68ed87e071b6afd3b8475afda"
        )


if __name__ == "__main__":
    unittest.main()
