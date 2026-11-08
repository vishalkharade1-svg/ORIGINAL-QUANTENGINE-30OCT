from dataclasses import replace

from core.governance.production_hardening_stages52_55 import (
    ComplianceEvidence, ControlTestEvidence, MonitoringEvidence, RecertificationEvidence,
    evaluate_compliance, evaluate_control_test, evaluate_monitoring, evaluate_recertification,
)

COMMIT = "a" * 40
DIGEST = "b" * 64


def monitoring():
    return MonitoringEvidence("paper-service", COMMIT, DIGEST, "monitoring.json", "alerts.json",
        "review.json", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z",
        .999, .99, .001, .01, 120, 250, 0, 0, 0, True, True)


def compliance():
    return ComplianceEvidence("Example Ltd", "XX", COMMIT, DIGEST, "scope.json", "obligations.csv",
        "index.json", "review.json", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z",
        12, 12, 0, 0, 0, True, True)


def control_test():
    return ControlTestEvidence("owner", "CTRL-1", COMMIT, DIGEST, "plan.json", "execution.json",
        "exceptions.csv", "independent-tester", "2026-03-01T00:00:00Z", 100, 25, 0, 0,
        False, True, True)


def recertification():
    return RecertificationEvidence("access-controls", COMMIT, DIGEST, "c" * 64, "record.json",
        "owner.json", "approval.json", "exceptions.csv", "2026-01-01T00:00:00Z",
        "2027-01-01T00:00:00Z", 20, 20, 0, 0, True, True)


def test_all_four_stages_only_report_unverified_evidence_completion():
    assessments = [
        evaluate_monitoring(monitoring()), evaluate_compliance(compliance()),
        evaluate_control_test(control_test()), evaluate_recertification(recertification()),
    ]
    assert [a.stage for a in assessments] == [52, 53, 54, 55]
    assert all("UNVERIFIED" in a.status for a in assessments)
    assert all(a.live_arming_permitted is False for a in assessments)


def test_monitoring_fails_closed_on_slo_breach_and_telemetry_gap():
    e = replace(monitoring(), availability=.95, telemetry_gaps=1)
    result = evaluate_monitoring(e)
    assert result.status == "POST_RELEASE_MONITORING_HOLD"
    assert any("availability" in reason for reason in result.reasons)
    assert result.live_arming_permitted is False


def test_compliance_requires_full_evidence_and_zero_open_findings():
    e = replace(compliance(), evidenced_obligations=11, open_exceptions=1)
    result = evaluate_compliance(e)
    assert result.status == "COMPLIANCE_EVIDENCE_HOLD"
    assert any("all applicable obligations" in reason for reason in result.reasons)


def test_control_testing_rejects_self_review_and_failed_samples():
    e = replace(control_test(), owner_is_tester=True, failures=1)
    result = evaluate_control_test(e)
    assert result.status == "CONTROL_TEST_HOLD"
    assert any("segregated" in reason for reason in result.reasons)


def test_recertification_rejects_unassessed_changes_and_invalid_expiry():
    e = replace(recertification(), changed_controls_not_assessed=1,
                expires_at_utc="2025-12-31T00:00:00Z")
    result = evaluate_recertification(e)
    assert result.status == "RECERTIFICATION_HOLD"
    assert any("expiry" in reason for reason in result.reasons)
