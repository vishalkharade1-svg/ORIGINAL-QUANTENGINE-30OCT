from dataclasses import replace

from core.governance.production_hardening_stages56_59 import (
    CyberExerciseEvidence, ContinuityEvidence, RiskAcceptanceEvidence, VulnerabilityEvidence,
    evaluate_cyber_exercise, evaluate_continuity, evaluate_risk_acceptance,
    evaluate_vulnerability_management,
)

COMMIT = "a" * 40
DIGEST = "b" * 64


def vulnerability():
    return VulnerabilityEvidence("paper-release", COMMIT, DIGEST, "scan.json", "policy.json",
        "remediation.csv", "review.json", "2026-10-01T00:00:00Z", 0, 0, 0, 0, 0, True, True, True)


def cyber():
    return CyberExerciseEvidence("tabletop-01", COMMIT, DIGEST, "exercise.json", "roster.csv",
        "evidence.log", "after-action.md", "observer", "2026-10-02T00:00:00Z",
        8, 8, 0, 0, 0, True, True, True)


def continuity():
    return ContinuityEvidence("paper-runtime", COMMIT, DIGEST, "continuity.md", "exercise.json",
        "recovery.json", "assessor", "2026-10-03T00:00:00Z", "2026-10-03T02:00:00Z",
        45, 60, 2, 5, 12, 0, 0, True, True, True)


def risk():
    return RiskAcceptanceEvidence("RISK-1", "owner", COMMIT, DIGEST, "treatment.md",
        "acceptance.json", "approval.json", "exceptions.csv", "2026-10-04T00:00:00Z",
        "2027-01-04T00:00:00Z", 3.0, 4.0, 0, 0, False, True, True)


def test_four_stages_are_unverified_and_never_arm_live():
    results = [evaluate_vulnerability_management(vulnerability()), evaluate_cyber_exercise(cyber()),
               evaluate_continuity(continuity()), evaluate_risk_acceptance(risk())]
    assert [r.stage for r in results] == [56, 57, 58, 59]
    assert all("UNVERIFIED" in r.status for r in results)
    assert all(r.live_arming_permitted is False for r in results)


def test_vulnerability_gate_holds_for_critical_findings_and_missing_rescan():
    result = evaluate_vulnerability_management(replace(vulnerability(), critical_findings=1, rescan_after_remediation=False))
    assert result.status == "VULNERABILITY_REVIEW_HOLD"
    assert any("critical_findings" in reason for reason in result.reasons)


def test_cyber_exercise_requires_all_objectives_and_no_high_risk_actions():
    result = evaluate_cyber_exercise(replace(cyber(), objectives_met=7, open_high_risk_actions=1))
    assert result.status == "CYBER_EXERCISE_HOLD"
    assert any("all exercise objectives" in reason for reason in result.reasons)


def test_continuity_gate_checks_rto_rpo_and_dependency_coverage():
    result = evaluate_continuity(replace(continuity(), actual_recovery_minutes=75,
                                         untested_critical_dependencies=2))
    assert result.status == "CONTINUITY_EVIDENCE_HOLD"
    assert any("recovery time objective" in reason for reason in result.reasons)


def test_risk_acceptance_rejects_owner_approval_and_limit_breach():
    result = evaluate_risk_acceptance(replace(risk(), owner_is_approver=True, residual_risk_score=5))
    assert result.status == "RISK_ACCEPTANCE_HOLD"
    assert any("segregated" in reason for reason in result.reasons)
