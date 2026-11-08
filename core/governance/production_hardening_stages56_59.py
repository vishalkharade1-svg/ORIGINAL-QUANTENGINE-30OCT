"""Offline evidence gates for production-hardening Stages 56–59.

Pure structural validators over operator-supplied records. No vulnerability
scanning, incident response, recovery action, or risk approval is executed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re

_SHA = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class StageAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def _required(value: str, field: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{field} is required")


def _digest(value: str, field: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        reasons.append(f"{field} must be a lowercase SHA-256 digest")


def _commit(value: str, field: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _COMMIT.fullmatch(value):
        reasons.append(f"{field} must be a 40-character Git commit ID")


def _count(value: int, field: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append(f"{field} must be a non-negative integer")


def _date(value: str, field: str, reasons: list[str]) -> datetime | None:
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
        return result
    except (AttributeError, TypeError, ValueError):
        reasons.append(f"{field} must be ISO-8601 with an explicit UTC offset")
        return None


@dataclass(frozen=True)
class VulnerabilityEvidence:
    release_id: str
    source_commit: str
    sbom_digest: str
    scan_report_ref: str
    severity_policy_ref: str
    remediation_register_ref: str
    independent_review_ref: str
    assessed_at_utc: str
    critical_findings: int
    high_findings: int
    overdue_findings: int
    untriaged_findings: int
    accepted_exceptions: int
    exception_expiry_verified: bool
    rescan_after_remediation: bool
    artifact_scope_complete: bool


def evaluate_vulnerability_management(e: VulnerabilityEvidence) -> StageAssessment:
    r: list[str] = []
    for f in ("release_id", "scan_report_ref", "severity_policy_ref",
              "remediation_register_ref", "independent_review_ref"):
        _required(getattr(e, f), f, r)
    _commit(e.source_commit, "source_commit", r)
    _digest(e.sbom_digest, "sbom_digest", r)
    _date(e.assessed_at_utc, "assessed_at_utc", r)
    for f in ("critical_findings", "high_findings", "overdue_findings",
              "untriaged_findings", "accepted_exceptions"):
        _count(getattr(e, f), f, r)
    for f in ("critical_findings", "high_findings", "overdue_findings", "untriaged_findings"):
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{f} must be zero")
    for f in ("exception_expiry_verified", "rescan_after_remediation", "artifact_scope_complete"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return StageAssessment(56, "VULNERABILITY_REVIEW_HOLD", tuple(r))
    return StageAssessment(56, "VULNERABILITY_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("scanner coverage, severity classification and remediation require independent verification",))


@dataclass(frozen=True)
class CyberExerciseEvidence:
    scenario_id: str
    source_commit: str
    exercise_plan_digest: str
    exercise_report_ref: str
    participant_roster_ref: str
    evidence_log_ref: str
    after_action_report_ref: str
    independent_observer_ref: str
    exercised_at_utc: str
    objectives: int
    objectives_met: int
    critical_gaps: int
    overdue_actions: int
    open_high_risk_actions: int
    escalation_tested: bool
    communications_tested: bool
    evidence_preserved: bool


def evaluate_cyber_exercise(e: CyberExerciseEvidence) -> StageAssessment:
    r: list[str] = []
    for f in ("scenario_id", "exercise_report_ref", "participant_roster_ref", "evidence_log_ref",
              "after_action_report_ref", "independent_observer_ref"):
        _required(getattr(e, f), f, r)
    _commit(e.source_commit, "source_commit", r)
    _digest(e.exercise_plan_digest, "exercise_plan_digest", r)
    _date(e.exercised_at_utc, "exercised_at_utc", r)
    for f in ("objectives", "objectives_met", "critical_gaps", "overdue_actions", "open_high_risk_actions"):
        _count(getattr(e, f), f, r)
    if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (e.objectives, e.objectives_met)):
        if e.objectives == 0:
            r.append("objectives must be greater than zero")
        if e.objectives_met > e.objectives:
            r.append("objectives_met cannot exceed objectives")
        if e.objectives_met < e.objectives:
            r.append("all exercise objectives must be met")
    for f in ("critical_gaps", "overdue_actions", "open_high_risk_actions"):
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{f} must be zero")
    for f in ("escalation_tested", "communications_tested", "evidence_preserved"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return StageAssessment(57, "CYBER_EXERCISE_HOLD", tuple(r))
    return StageAssessment(57, "CYBER_EXERCISE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("exercise realism, participant performance and evidence integrity require independent confirmation",))


@dataclass(frozen=True)
class ContinuityEvidence:
    service: str
    source_commit: str
    dependency_map_digest: str
    continuity_plan_ref: str
    exercise_record_ref: str
    recovery_evidence_ref: str
    independent_assessor_ref: str
    exercise_start_utc: str
    exercise_end_utc: str
    actual_recovery_minutes: float
    recovery_time_objective_minutes: float
    actual_data_loss_minutes: float
    recovery_point_objective_minutes: float
    critical_dependencies: int
    untested_critical_dependencies: int
    unresolved_recovery_failures: int
    backup_restore_verified: bool
    failover_path_tested: bool
    data_integrity_verified: bool


def evaluate_continuity(e: ContinuityEvidence) -> StageAssessment:
    r: list[str] = []
    for f in ("service", "continuity_plan_ref", "exercise_record_ref", "recovery_evidence_ref",
              "independent_assessor_ref"):
        _required(getattr(e, f), f, r)
    _commit(e.source_commit, "source_commit", r)
    _digest(e.dependency_map_digest, "dependency_map_digest", r)
    start, end = _date(e.exercise_start_utc, "exercise_start_utc", r), _date(e.exercise_end_utc, "exercise_end_utc", r)
    if start and end and end <= start:
        r.append("exercise end must follow start")
    numeric = ("actual_recovery_minutes", "recovery_time_objective_minutes",
               "actual_data_loss_minutes", "recovery_point_objective_minutes")
    for f in numeric:
        v = getattr(e, f)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            r.append(f"{f} must be finite and non-negative")
    for actual, target, message in (
        (e.actual_recovery_minutes, e.recovery_time_objective_minutes, "recovery time objective exceeded"),
        (e.actual_data_loss_minutes, e.recovery_point_objective_minutes, "recovery point objective exceeded"),
    ):
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in (actual, target)) and actual > target:
            r.append(message)
    for f in ("critical_dependencies", "untested_critical_dependencies", "unresolved_recovery_failures"):
        _count(getattr(e, f), f, r)
    if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (e.critical_dependencies, e.untested_critical_dependencies)):
        if e.untested_critical_dependencies > e.critical_dependencies:
            r.append("untested critical dependencies cannot exceed total")
        if e.untested_critical_dependencies:
            r.append("all critical dependencies must be tested")
    if isinstance(e.unresolved_recovery_failures, int) and not isinstance(e.unresolved_recovery_failures, bool) and e.unresolved_recovery_failures:
        r.append("unresolved recovery failures must be zero")
    for f in ("backup_restore_verified", "failover_path_tested", "data_integrity_verified"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return StageAssessment(58, "CONTINUITY_EVIDENCE_HOLD", tuple(r))
    return StageAssessment(58, "CONTINUITY_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("recovery measurements, dependency coverage and restore integrity require independent verification",))


@dataclass(frozen=True)
class RiskAcceptanceEvidence:
    risk_id: str
    risk_owner: str
    source_commit: str
    risk_assessment_digest: str
    treatment_plan_ref: str
    acceptance_record_ref: str
    independent_approval_ref: str
    exception_register_ref: str
    accepted_at_utc: str
    expires_at_utc: str
    residual_risk_score: float
    approved_risk_limit: float
    open_critical_actions: int
    overdue_actions: int
    owner_is_approver: bool
    compensating_controls_tested: bool
    periodic_review_scheduled: bool


def evaluate_risk_acceptance(e: RiskAcceptanceEvidence) -> StageAssessment:
    r: list[str] = []
    for f in ("risk_id", "risk_owner", "treatment_plan_ref", "acceptance_record_ref",
              "independent_approval_ref", "exception_register_ref"):
        _required(getattr(e, f), f, r)
    _commit(e.source_commit, "source_commit", r)
    _digest(e.risk_assessment_digest, "risk_assessment_digest", r)
    accepted, expires = _date(e.accepted_at_utc, "accepted_at_utc", r), _date(e.expires_at_utc, "expires_at_utc", r)
    if accepted and expires and expires <= accepted:
        r.append("risk acceptance expiry must follow acceptance time")
    for f in ("residual_risk_score", "approved_risk_limit"):
        v = getattr(e, f)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            r.append(f"{f} must be finite and non-negative")
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in (e.residual_risk_score, e.approved_risk_limit)):
        if e.residual_risk_score > e.approved_risk_limit:
            r.append("residual risk exceeds approved limit")
    for f in ("open_critical_actions", "overdue_actions"):
        _count(getattr(e, f), f, r)
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{f} must be zero")
    if e.owner_is_approver is not False:
        r.append("risk owner and approver must be segregated")
    for f in ("compensating_controls_tested", "periodic_review_scheduled"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return StageAssessment(59, "RISK_ACCEPTANCE_HOLD", tuple(r))
    return StageAssessment(59, "RISK_ACCEPTANCE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("risk authority, appetite and approval validity require independent governance confirmation",))
