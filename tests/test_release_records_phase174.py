"""Phase 174 regression: release records must describe the bytes actually shipped.

Phase 174 Independent Economics Reconciliation, Gate Integrity & Evidence-Calibrated Execution:
1. Baseline reproduction and archive integrity verification for Phase 173 candidate.
2. Independent reconciliation of all 6 setups across Symmetric and Asymmetric models.
3. Detailed mathematical derivation of the 50-pt, 150-pt, 400-pt, and 1000-pt discrepancies.
4. Friction hurdle rule subsumption proof (Rule 1 strictly subsumes Rule 2) and fail-closed safety.
5. Poisson queue dynamics mathematical audit answering all 7 core questions.
6. Realized cashflow vs counterfactual opportunity cost separation.
7. Verification of data lineage and non-overlapping boundary constraints.
8. Reconciled test accounting and contractual preservation of historical pins.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

from core.research.strategy_identity import get_versioned_identities

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_NAME = "QuantEngine_PHASE174_RELEASE_CANDIDATE.zip"
DETACHED_NAME = "RELEASE_HASH_PHASE174.txt"

INPUT_ARCHIVE = "QuantEngine_PHASE173_RELEASE_CANDIDATE.zip"
INPUT_ARCHIVE_SHA256 = "db88433208b4059369734c6e6f2e9c7aa1fc7c6193bed93c5d6392e79bae0e8e"

PROVENANCE = ROOT / "reports" / "PHASE174_PROVENANCE.json"
GATES = ROOT / "reports" / "PHASE174_RELEASE_GATES.json"

REQUIRED_RECORDS = [
    "NEXT_ACTIONS.md",
    "reports/PHASE174_RELEASE_GATES.json",
    "reports/PHASE174_BLOCKERS.json",
    "reports/PHASE174_PROVENANCE.json",
    "reports/PHASE174_TEST_RESULTS.json",
    "reports/PHASE174_PRIVACY_REVIEW.md",
    "reports/PHASE174_QUEUE_MODEL_AUDIT.md",
    "reports/PHASE174_PNL_RECONCILIATION.md",
    "reports/PHASE174_GATE_ENFORCEMENT_AUDIT.md",
    "reports/PHASE174_DATA_EVIDENCE_AUDIT.md",
    "reports/PHASE174_FINDINGS.json",
    "reports/PHASE174_INDEPENDENT_ECONOMICS_AUDIT.md",
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
    "reports/PHASE172_RELEASE_GATES.json": {
        "sha256": "b88a1d0e8c4a72057b86b538bd61f03f79b8c17757631010a29da775430c80ff",
        "describes": "the Phase172 release gates record, preserved unchanged",
    },
    "reports/PHASE172_BLOCKERS.json": {
        "sha256": "f7d5ff115790955178b709ff1bc70e1f7dd0e25fd3518e6a0cfe60ee1c70e256",
        "describes": "the Phase172 blockers record, preserved unchanged",
    },
    "reports/PHASE172_PROVENANCE.json": {
        "sha256": "6c64893fb1ba9d6107edb4fa31ce44560e1617397f156bef00296559826a0110",
        "describes": "the Phase172 provenance record, preserved unchanged",
    },
    "reports/PHASE172_TEST_RESULTS.json": {
        "sha256": "fd5571f52e369d3f6af28582825a13de31552d040302615ecaac668990812956",
        "describes": "the Phase172 test results record, preserved unchanged",
    },
    "reports/PHASE172_PRIVACY_REVIEW.md": {
        "sha256": "c0a50b8b8a9b2b2ed25f72076934e03e9f9de97248cde67699bf8fb4884bd7c1",
        "describes": "the Phase172 privacy review, preserved unchanged",
    },
    "reports/PHASE172_QUEUE_MODEL_VALIDATION.md": {
        "sha256": "455ed4837635197e6b7e3d36ecde1979df680efce4655be92f7cb9f618e0f3ba",
        "describes": "the Phase172 queue model validation report, preserved unchanged",
    },
    "reports/PHASE172_FRICTION_GATE_BACKTEST.md": {
        "sha256": "ec49bc77fdd3830cdfacd198062068e96d22ede1afa3ea97b33444ae555c5156",
        "describes": "the Phase172 friction gate backtest report, preserved unchanged",
    },
    "reports/PHASE172_FINDINGS.json": {
        "sha256": "41af54f47a2e055a2898f3099836abb3f7486f39551e4d099d8ce7de6c05dc9f",
        "describes": "the Phase172 findings record, preserved unchanged",
    },
    "reports/PHASE172_INDEPENDENT_AUDIT.md": {
        "sha256": "c794d0510a3c144fa6beb077b47a955fa15ff8dc835dad2f2d62bd31b54321da",
        "describes": "the Phase172 independent audit report, preserved unchanged",
    },
    "reports/PHASE173_RELEASE_GATES.json": {
        "sha256": "e11907d5a6588d24c38b4fc5b2a4fc5f2bf4f42c100e3ee3bf8e4743a85f4d21",
        "describes": "the Phase173 release gates record, preserved unchanged",
    },
    "reports/PHASE173_BLOCKERS.json": {
        "sha256": "6d980d712e7d986482898b3bce34dcd58ea578165f7d38b75db2e82de8f6addd",
        "describes": "the Phase173 blockers record, preserved unchanged",
    },
    "reports/PHASE173_PROVENANCE.json": {
        "sha256": "1dba81d096e0b7c81a14f351eb5f8813ae81955f95d5798689a39e8d65b52f6a",
        "describes": "the Phase173 provenance record, preserved unchanged",
    },
    "reports/PHASE173_TEST_RESULTS.json": {
        "sha256": "5d8e09c99169b8aa464970207da4a1f8a0db320ae1f67794fe9fe58e5b92122f",
        "describes": "the Phase173 test results record, preserved unchanged",
    },
    "reports/PHASE173_PRIVACY_REVIEW.md": {
        "sha256": "efd401106d49ca0bff877c7c47c2133ceb562620c8b7983d24e01d100425fa26",
        "describes": "the Phase173 privacy review, preserved unchanged",
    },
    "reports/PHASE173_QUEUE_MODEL_VALIDATION.md": {
        "sha256": "866a306de45893219d5fca3ed19ec6ef8b80eda8edacad0f10efa9243dc2f541",
        "describes": "the Phase173 queue model validation report, preserved unchanged",
    },
    "reports/PHASE173_BACKTEST_REPRODUCTION.md": {
        "sha256": "14f46534f1cb6fe911606603a91c99a771004eba6ca6b3726e731f0e820a438d",
        "describes": "the Phase173 backtest reproduction report, preserved unchanged",
    },
    "reports/PHASE173_FINDINGS.json": {
        "sha256": "4c28b92d28b42ed45c713218a89b8d7048cf0cfd1cbb4327617c48e38ef682be",
        "describes": "the Phase173 findings record, preserved unchanged",
    },
    "reports/PHASE173_INDEPENDENT_AUDIT.md": {
        "sha256": "ec396baf1c4a43ff8aeab8d9ac469a4f8b97afc83458e89f8dbb7b4a272fd5a6",
        "describes": "the Phase173 independent audit report, preserved unchanged",
    },
}

PATH_IN_TEXT = re.compile(r"\b(?:reports|docs)/[A-Za-z0-9_.\-/]+\.(?:json|md|txt)\b")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestReleaseRecords174(unittest.TestCase):
    def test_required_release_records_exist_and_are_not_empty(self):
        for rel in REQUIRED_RECORDS:
            p = ROOT / rel
            self.assertTrue(p.exists(), f"missing required record: {rel}")
            self.assertGreater(p.stat().st_size, 0, f"record is empty: {rel}")

    def test_provenance_names_the_input_and_output_archives(self):
        self.assertTrue(PROVENANCE.exists(), "missing provenance record")
        doc = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(doc["phase"], 174)
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
        self.assertEqual(doc["phase"], 174)
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
        from tests.evidence_mode import require_history_depth
        require_history_depth(self, "phase174.historical_records")
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
        from tests.strategy_identity_evidence import assert_unregistered_identity
        identities = get_versioned_identities(ROOT)
        assert_unregistered_identity(self, identities, ROOT)


if __name__ == "__main__":
    unittest.main()
