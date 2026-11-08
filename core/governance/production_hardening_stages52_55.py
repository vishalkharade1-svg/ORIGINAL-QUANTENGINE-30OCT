"""Offline evidence gates for production-hardening Stages 52–55.

Pure structural validators over operator-supplied evidence. They do not query
production telemetry, evaluate live models, change controls, or authorize use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class StageAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def _text(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{name} is required")


def _digest(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        reasons.append(f"{name} must be a lowercase SHA-256 digest")


def _commit(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _GIT_SHA.fullmatch(value):
        reasons.append(f"{name} must be a 40-character Git commit ID")


def _number(value: float, name: str, reasons: list[str], *, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        reasons.append(f"{name} must be finite")
    elif minimum is not None and value < minimum:
        reasons.append(f"{name} must be at least {minimum}")


def _count(value: int, name: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append(f"{name} must be a non-negative integer")


def _time(value: str, name: str, reasons: list[str]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (AttributeError, TypeError, ValueError):
        reasons.append(f"{name} must be ISO-8601 with an explicit UTC offset")
        return None


@dataclass(frozen=True)
class MonitoringEvidence:
    service: str
    source_commit: str
    telemetry_snapshot_digest: str
    monitoring_report_ref: str
    alert_test_ref: str
    independent_review_ref: str
    window_start_utc: str
    window_end_utc: str
    availability: float
    availability_minimum: float
    error_rate: float
    error_rate_maximum: float
    p99_latency_ms: float
    p99_latency_maximum_ms: float
    unresolved_critical_alerts: int
    unacknowledged_alerts: int
    telemetry_gaps: int
    alert_delivery_tested: bool
    rollback_trigger_verified: bool


def evaluate_monitoring(e: MonitoringEvidence) -> StageAssessment:
    r: list[str] = []
    for n in ("service", "monitoring_report_ref", "alert_test_ref", "independent_review_ref"):
        _text(getattr(e, n), n, r)
    _commit(e.source_commit, "source_commit", r)
    _digest(e.telemetry_snapshot_digest, "telemetry_snapshot_digest", r)
    start, end = _time(e.window_start_utc, "window_start_utc", r), _time(e.window_end_utc, "window_end_utc", r)
    if start and end and end <= start:
        r.append("monitoring window end must follow its start")
    for n in ("availability", "availability_minimum", "error_rate", "error_rate_maximum",
              "p99_latency_ms", "p99_latency_maximum_ms"):
        _number(getattr(e, n), n, r, minimum=0)
    if isinstance(e.availability, (int, float)) and not isinstance(e.availability, bool) and e.availability > 1:
        r.append("availability must not exceed one")
    if isinstance(e.error_rate, (int, float)) and not isinstance(e.error_rate, bool) and e.error_rate > 1:
        r.append("error_rate must not exceed one")
    for observed, limit, msg, lower in (
        (e.availability, e.availability_minimum, "availability below minimum", True),
        (e.error_rate, e.error_rate_maximum, "error rate above maximum", False),
        (e.p99_latency_ms, e.p99_latency_maximum_ms, "p99 latency above maximum", False),
    ):
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (observed, limit)):
            if (lower and observed < limit) or (not lower and observed > limit):
                r.append(msg)
    for n in ("unresolved_critical_alerts", "unacknowledged_alerts", "telemetry_gaps"):
        _count(getattr(e, n), n, r)
        v = getattr(e, n)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{n} must be zero")
    for n in ("alert_delivery_tested", "rollback_trigger_verified"):
        if getattr(e, n) is not True:
            r.append(f"{n} must be explicitly attested true")
    if r:
        return StageAssessment(52, "POST_RELEASE_MONITORING_HOLD", tuple(r))
    return StageAssessment(52, "MONITORING_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("telemetry provenance and SLO claims require independent source verification",))


@dataclass(frozen=True)
class ComplianceEvidence:
    legal_entity: str
    jurisdiction: str
    source_commit: str
    control_matrix_digest: str
    applicability_assessment_ref: str
    obligation_register_ref: str
    evidence_index_ref: str
    compliance_review_ref: str
    reporting_period_start_utc: str
    reporting_period_end_utc: str
    applicable_obligations: int
    evidenced_obligations: int
    overdue_obligations: int
    material_findings: int
    open_exceptions: int
    evidence_retention_attested: bool
    independent_compliance_review: bool


def evaluate_compliance(e: ComplianceEvidence) -> StageAssessment:
    r: list[str] = []
    for n in ("legal_entity", "jurisdiction", "applicability_assessment_ref", "obligation_register_ref",
              "evidence_index_ref", "compliance_review_ref"):
        _text(getattr(e, n), n, r)
    _commit(e.source_commit, "source_commit", r)
    _digest(e.control_matrix_digest, "control_matrix_digest", r)
    start, end = _time(e.reporting_period_start_utc, "reporting_period_start_utc", r), _time(e.reporting_period_end_utc, "reporting_period_end_utc", r)
    if start and end and end <= start:
        r.append("reporting period end must follow start")
    for n in ("applicable_obligations", "evidenced_obligations", "overdue_obligations",
              "material_findings", "open_exceptions"):
        _count(getattr(e, n), n, r)
    if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
           for v in (e.applicable_obligations, e.evidenced_obligations)):
        if e.evidenced_obligations > e.applicable_obligations:
            r.append("evidenced obligations cannot exceed applicable obligations")
        if e.evidenced_obligations < e.applicable_obligations:
            r.append("all applicable obligations require indexed evidence")
    for n in ("overdue_obligations", "material_findings", "open_exceptions"):
        v = getattr(e, n)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{n} must be zero")
    for n in ("evidence_retention_attested", "independent_compliance_review"):
        if getattr(e, n) is not True:
            r.append(f"{n} must be explicitly attested true")
    if r:
        return StageAssessment(53, "COMPLIANCE_EVIDENCE_HOLD", tuple(r))
    return StageAssessment(53, "COMPLIANCE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("legal applicability and underlying evidence require qualified independent review",))


@dataclass(frozen=True)
class ControlTestEvidence:
    control_owner: str
    control_id: str
    source_commit: str
    control_design_digest: str
    test_plan_ref: str
    execution_record_ref: str
    exception_log_ref: str
    independent_tester_ref: str
    tested_at_utc: str
    population_size: int
    sample_size: int
    failures: int
    unresolved_high_risk_exceptions: int
    owner_is_tester: bool
    evidence_reperformed: bool
    remediation_retested: bool


def evaluate_control_test(e: ControlTestEvidence) -> StageAssessment:
    r: list[str] = []
    for n in ("control_owner", "control_id", "test_plan_ref", "execution_record_ref",
              "exception_log_ref", "independent_tester_ref"):
        _text(getattr(e, n), n, r)
    _commit(e.source_commit, "source_commit", r)
    _digest(e.control_design_digest, "control_design_digest", r)
    _time(e.tested_at_utc, "tested_at_utc", r)
    for n in ("population_size", "sample_size", "failures", "unresolved_high_risk_exceptions"):
        _count(getattr(e, n), n, r)
    if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
           for v in (e.population_size, e.sample_size)) and e.sample_size > e.population_size:
        r.append("sample_size cannot exceed population_size")
    for n in ("failures", "unresolved_high_risk_exceptions"):
        v = getattr(e, n)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{n} must be zero")
    if e.owner_is_tester is not False:
        r.append("control owner and tester must be segregated")
    for n in ("evidence_reperformed", "remediation_retested"):
        if getattr(e, n) is not True:
            r.append(f"{n} must be explicitly attested true")
    if r:
        return StageAssessment(54, "CONTROL_TEST_HOLD", tuple(r))
    return StageAssessment(54, "CONTROL_TEST_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("sample selection, reperformance and tester independence require independent confirmation",))


@dataclass(frozen=True)
class RecertificationEvidence:
    control_domain: str
    source_commit: str
    prior_assessment_digest: str
    current_evidence_digest: str
    recertification_record_ref: str
    owner_attestation_ref: str
    independent_approval_ref: str
    exception_register_ref: str
    certified_at_utc: str
    expires_at_utc: str
    controls_in_scope: int
    controls_retested: int
    changed_controls_not_assessed: int
    expired_exceptions: int
    material_changes_disclosed: bool
    evidence_snapshot_frozen: bool


def evaluate_recertification(e: RecertificationEvidence) -> StageAssessment:
    r: list[str] = []
    for n in ("control_domain", "recertification_record_ref", "owner_attestation_ref",
              "independent_approval_ref", "exception_register_ref"):
        _text(getattr(e, n), n, r)
    _commit(e.source_commit, "source_commit", r)
    for n in ("prior_assessment_digest", "current_evidence_digest"):
        _digest(getattr(e, n), n, r)
    certified, expires = _time(e.certified_at_utc, "certified_at_utc", r), _time(e.expires_at_utc, "expires_at_utc", r)
    if certified and expires and expires <= certified:
        r.append("recertification expiry must follow certification time")
    for n in ("controls_in_scope", "controls_retested", "changed_controls_not_assessed", "expired_exceptions"):
        _count(getattr(e, n), n, r)
    if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
           for v in (e.controls_in_scope, e.controls_retested)):
        if e.controls_retested > e.controls_in_scope:
            r.append("controls_retested cannot exceed controls_in_scope")
        if e.controls_retested < e.controls_in_scope:
            r.append("all in-scope controls must be retested")
    for n in ("changed_controls_not_assessed", "expired_exceptions"):
        v = getattr(e, n)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{n} must be zero")
    for n in ("material_changes_disclosed", "evidence_snapshot_frozen"):
        if getattr(e, n) is not True:
            r.append(f"{n} must be explicitly attested true")
    if r:
        return StageAssessment(55, "RECERTIFICATION_HOLD", tuple(r))
    return StageAssessment(55, "RECERTIFICATION_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("recertification validity remains bounded by its expiry and independent evidence review",))
