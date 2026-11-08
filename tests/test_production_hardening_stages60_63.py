from dataclasses import replace

from core.governance.production_hardening_stages60_63 import (
    AssuranceDossierEvidence, KeyLifecycleEvidence, SecurityTestingEvidence,
    ThreatModelEvidence, evaluate_assurance_dossier, evaluate_key_lifecycle,
    evaluate_security_testing, evaluate_threat_model,
)

COMMIT = "a" * 40
DIGEST = "b" * 64


def key_lifecycle():
    return KeyLifecycleEvidence(DIGEST, COMMIT, "inventory.json", "rotation-policy.md",
        "rotation-log.csv", "dual-control.json", "hsm-attestation.json", "review.json",
        "2026-11-01T00:00:00Z", 12, 0, 0, 0, 0, True, True, True)


def threat_model():
    return ThreatModelEvidence(DIGEST, DIGEST, COMMIT, "threat-model.md", "assets.csv",
        "boundaries.md", "mitigations.csv", "architecture-review.md",
        "2026-11-02T00:00:00Z", 15, 4, 20, 20, 0, 0, True, True)


def security_testing():
    return SecurityTestingEvidence(COMMIT, DIGEST, "build-attestation.json", "sast.json",
        "dast.json", "dependencies.json", "pentest.pdf", "retest.json", "assessor.md",
        "2026-11-03T00:00:00Z", 0, 0, 0, 0, True, True, True)


def assurance_dossier():
    return AssuranceDossierEvidence(COMMIT, tuple(range(56, 63)), (DIGEST,) * 7,
        "dossier.zip", "independent-assurance.md", "blockers.csv",
        "2026-11-04T00:00:00Z", 0, True, True)


def test_four_stages_are_unverified_and_never_arm_live():
    results = [evaluate_key_lifecycle(key_lifecycle()), evaluate_threat_model(threat_model()),
               evaluate_security_testing(security_testing()),
               evaluate_assurance_dossier(assurance_dossier())]
    assert [r.stage for r in results] == [60, 61, 62, 63]
    assert all("UNVERIFIED" in r.status for r in results)
    assert all(r.live_arming_permitted is False for r in results)


def test_key_lifecycle_holds_for_expired_keys_and_missing_dual_control():
    result = evaluate_key_lifecycle(replace(key_lifecycle(), expired_keys=1, dual_control_verified=False))
    assert result.status == "KEY_LIFECYCLE_HOLD"
    assert any("expired_keys" in reason for reason in result.reasons)


def test_threat_model_requires_tested_mitigations_and_zero_high_residual():
    result = evaluate_threat_model(replace(threat_model(), threats_mitigated=19, high_residual_threats=1))
    assert result.status == "THREAT_MODEL_HOLD"
    assert any("all identified threats" in reason for reason in result.reasons)


def test_security_testing_rejects_high_findings_and_incomplete_scope():
    result = evaluate_security_testing(replace(security_testing(), high_findings=1, test_scope_complete=False))
    assert result.status == "SECURITY_TESTING_HOLD"
    assert any("high_findings" in reason for reason in result.reasons)


def test_assurance_dossier_requires_all_stage_digests_and_zero_blockers():
    result = evaluate_assurance_dossier(replace(assurance_dossier(), evidence_stage_ids=(56, 57), unresolved_blockers=2))
    assert result.status == "ASSURANCE_DOSSIER_HOLD"
    assert any("stages 56 through 62" in reason for reason in result.reasons)
