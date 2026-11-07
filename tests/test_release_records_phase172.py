"""Phase 172 regression: release records must describe the bytes actually shipped.

Phase 172 Queue-Aware Paper Execution, Post-Cost Backtesting & Maker Edge Validation:
1. Baseline reproduction and archive integrity verification for Phase 171 candidate.
2. Queue-aware deterministic paper execution state machine without live exchange access.
3. Asymmetric fee and execution economics modeling (Maker entry / Taker exit, rebates, GST).
4. FrictionHurdleGate pre-order decision integration in historical backtester.
5. Granular queue dynamics calibration separating 8 empirical vs simulated metrics.
6. Multi-year data limitation disclosure (1,440 continuous 1m bars; 113 L2 updates; rest is BLOCKED_EVIDENCE).
7. Maintenance of standing external blockers and release gate enforcement.

Release integrity contracts:
1. All required release records exist and are non-empty.
2. Current records name the correct artifacts and never embed their own archive hash.
3. Gates reference only existing reports.
4. Blocked gates forbid any claim of PRODUCTION_READY.
5. Historical records (Phase 161 through 171) are preserved unchanged and labelled.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

from core.research.strategy_identity import get_versioned_identities

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_NAME = "QuantEngine_PHASE172_RELEASE_CANDIDATE.zip"
DETACHED_NAME = "RELEASE_HASH_PHASE172.txt"

INPUT_ARCHIVE = "QuantEngine_PHASE171_RELEASE_CANDIDATE.zip"
INPUT_ARCHIVE_SHA256 = "18cbec7a7c891212e0add042e22fef0144293454d06a294a0bc4c00f907b0a39"

PROVENANCE = ROOT / "reports" / "PHASE172_PROVENANCE.json"
GATES = ROOT / "reports" / "PHASE172_RELEASE_GATES.json"

REQUIRED_RECORDS = [
    "NEXT_ACTIONS.md",
    "reports/PHASE172_RELEASE_GATES.json",
    "reports/PHASE172_BLOCKERS.json",
    "reports/PHASE172_PROVENANCE.json",
    "reports/PHASE172_TEST_RESULTS.json",
    "reports/PHASE172_PRIVACY_REVIEW.md",
    "reports/PHASE172_QUEUE_MODEL_VALIDATION.md",
    "reports/PHASE172_FRICTION_GATE_BACKTEST.md",
    "reports/PHASE172_FINDINGS.json",
    "reports/PHASE172_INDEPENDENT_AUDIT.md",
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
    "reports/PHASE170_RELEASE_GATES.json": {
        "sha256": "9a8e3b7020366e09ca53608bea1f6a56b2682dca2af93542dbd9ceb7f1bc4cfd",
        "describes": "the Phase170 release gates, preserved unchanged",
    },
    "reports/PHASE170_BLOCKERS.json": {
        "sha256": "53e9ef3d43d2eca60bc985a269043441b468b1bba6605608352a51450e8b58b1",
        "describes": "the Phase170 blockers record, preserved unchanged",
    },
    "reports/PHASE170_PROVENANCE.json": {
        "sha256": "3d09565b56960a93050d072141573e042ee3a55dbd8991c2248f18457b49e99e",
        "describes": "the Phase170 provenance record, preserved unchanged",
    },
    "reports/PHASE170_TEST_RESULTS.json": {
        "sha256": "380cc2daf29cf116634948ab2c429755801ee133a71e4c660d909826a717a33c",
        "describes": "the Phase170 test results, preserved unchanged",
    },
    "reports/PHASE170_PRIVACY_REVIEW.md": {
        "sha256": "ee54901f50dbdab5183f87d76157aec54920aef99e7282a1c015bf3c8b9a6c7e",
        "describes": "the Phase170 privacy review, preserved unchanged",
    },
    "reports/PHASE170_RECONCILIATION_RESULTS.json": {
        "sha256": "418bb9b5e30b580ea4138d1d2cc4b678a6c465f4ea644aa70941a82d9029d6d8",
        "describes": "the Phase170 reconciliation results, preserved unchanged",
    },
    "reports/PHASE170_TIMESTAMP_PROVENANCE.md": {
        "sha256": "2e673c3786a8710aa19adfaf2daa9ac1bd64aa137eb2bcaa197a37a543c7bf11",
        "describes": "the Phase170 timestamp provenance report, preserved unchanged",
    },
    "reports/PHASE170_FINDINGS.json": {
        "sha256": "90ec804e96c4b1c282fee311ade7dd07969e7b03f0b59a8e0f24c02ceed4b4e9",
        "describes": "the Phase170 findings record, preserved unchanged",
    },
    "reports/PHASE170_INDEPENDENT_AUDIT.md": {
        "sha256": "5e0a5f924b5b6012d517f6cb28e9612ab5cc5c3764de863e1a1b16a541d56c82",
        "describes": "the Phase170 independent audit report, preserved unchanged",
    },
    "reports/PHASE171_BLOCKERS.json": {
        "sha256": "9288da23d190c484bff77f3fa7b9fac75ca9e3bbf68966184f8c3520a6ab4a8d",
        "describes": "the Phase171 blockers record, preserved unchanged",
    },
    "reports/PHASE171_FINDINGS.json": {
        "sha256": "a57e5f415e60baabe2036e70ad90e7de91278b8436d867d203c78d362107fcf9",
        "describes": "the Phase171 findings record, preserved unchanged",
    },
    "reports/PHASE171_INDEPENDENT_AUDIT.md": {
        "sha256": "846b80121a56f1a1e0b2219aea7b38f5963b1ae4f8da033d9102367b71b7fdc8",
        "describes": "the Phase171 independent audit report, preserved unchanged",
    },
    "reports/PHASE171_MAKER_EXECUTION_RESEARCH.md": {
        "sha256": "7c6fe2434e242c03c63f519bcfe2974b65b5f3da1fd50cb48ab7767115a1c968",
        "describes": "the Phase171 maker execution research report, preserved unchanged",
    },
    "reports/PHASE171_PRIVACY_REVIEW.md": {
        "sha256": "fca12a03086aa0efc213af5b2e96c43de5dd981caa4764210906e74584dcd66a",
        "describes": "the Phase171 privacy review, preserved unchanged",
    },
    "reports/PHASE171_PROVENANCE.json": {
        "sha256": "dc5b27c2c41f4f6af00c4a22ad47773584ede258f5feaa630b6c1e6bde59bd26",
        "describes": "the Phase171 provenance record, preserved unchanged",
    },
    "reports/PHASE171_RECONCILIATION_RESULTS.json": {
        "sha256": "3a5d611e67b468761dde35eb73cffdabfc227a9db437de62d0193b799f4076c7",
        "describes": "the Phase171 reconciliation results, preserved unchanged",
    },
    "reports/PHASE171_RELEASE_GATES.json": {
        "sha256": "a7eb7ff19e5e989877fef0144dee85d56ace0238e3777eecfd6deef99bfcdd31",
        "describes": "the Phase171 release gates record, preserved unchanged",
    },
    "reports/PHASE171_TEST_RESULTS.json": {
        "sha256": "17b972f665a483bbe509afd2aedf4fe7aa8f9d46f0ea77f27a04d3d63efb14d8",
        "describes": "the Phase171 test results record, preserved unchanged",
    },
}

PATH_IN_TEXT = re.compile(r"\b(?:reports|docs)/[A-Za-z0-9_.\-/]+\.(?:json|md|txt)\b")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestReleaseRecords172(unittest.TestCase):
    def test_required_release_records_exist_and_are_not_empty(self):
        for rel in REQUIRED_RECORDS:
            p = ROOT / rel
            self.assertTrue(p.exists(), f"missing required record: {rel}")
            self.assertGreater(p.stat().st_size, 0, f"record is empty: {rel}")

    def test_provenance_names_the_input_and_output_archives(self):
        self.assertTrue(PROVENANCE.exists(), "missing provenance record")
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(doc["phase"], 172)
        self.assertEqual(doc["input"]["archive"], INPUT_ARCHIVE)
        self.assertEqual(doc["input"]["sha256"], INPUT_ARCHIVE_SHA256)
        self.assertEqual(doc["output"]["archive"], ARCHIVE_NAME)
        self.assertEqual(doc["output"]["detached_record"], DETACHED_NAME)

    def test_current_records_do_not_embed_the_shipped_archive_hash(self):
        detached = ROOT.parent / DETACHED_NAME
        if not detached.exists():
            self.skipTest(f"detached hash {DETACHED_NAME} not yet generated")
        h = detached.read_text(encoding="utf-8").strip().split()[0].lower()

        for rel in REQUIRED_RECORDS:
            content = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            self.assertNotIn(
                h, content.lower(),
                f"{rel} embeds the shipped archive hash {h}",
            )

    def test_gates_reference_only_reports_that_exist(self):
        self.assertTrue(GATES.exists(), "missing release gates record")
        doc = json.loads(GATES.read_text(encoding="utf-8"))
        self.assertEqual(doc["phase"], 172)
        for gate_name, gate in doc.get("gates", {}).items():
            ev = gate.get("evidence", "")
            if ev:
                self.assertTrue(
                    (ROOT / ev).exists(),
                    f"gate {gate_name} references non-existent evidence {ev}",
                )

    def test_any_blocked_gate_forbids_a_production_ready_claim(self):
        doc = json.loads(GATES.read_text(encoding="utf-8"))
        has_blocked = any(g.get("status") == "BLOCKED" for g in doc.get("gates", {}).values())
        if has_blocked:
            self.assertNotEqual(doc.get("system_status"), "PRODUCTION_READY")

    def test_historical_records_are_preserved_and_labelled(self):
        for rel, expected in HISTORICAL_PINS.items():
            p = ROOT / rel
            self.assertTrue(p.exists(), f"historical record missing: {rel}")
            actual = _sha256(p)
            self.assertEqual(
                actual, expected["sha256"],
                f"historical record {rel} was modified! Expected {expected['sha256']}, got {actual}",
            )

    def test_detached_record_is_outside_the_package_and_agrees_with_the_archive(self):
        detached = ROOT.parent / DETACHED_NAME
        archive = ROOT.parent / ARCHIVE_NAME
        if not detached.exists() or not archive.exists():
            self.skipTest("archive or detached record not present in parent dir")
        expected = detached.read_text(encoding="utf-8").strip().split()[0].lower()
        actual = _sha256(archive)
        self.assertEqual(actual, expected)

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
