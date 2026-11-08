"""Offline evidence gates for production-hardening Stages 20–23.

These validators consume operator-supplied records only. They do not sign,
authenticate external systems, execute backups, invoke incident controls,
deploy software, or authorize live trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _utc(value: str, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include an offset")
    return parsed.astimezone(timezone.utc)


def _refs(values: Iterable[str], name: str) -> list[str]:
    result = list(values)
    if not result or any(not isinstance(x, str) or not x.strip() for x in result):
        raise ValueError(f"{name} must contain non-empty references")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} contains duplicate references")
    return result


@dataclass(frozen=True)
class SupplyChainEvidence:
    source_commit: str
    build_run_ref: str
    builder_identity_ref: str
    dependency_lock_ref: str
    dependency_scan_ref: str
    artifact_digest: str
    provenance_ref: str
    independent_review_ref: str
    build_reproducible: bool
    critical_vulnerabilities: int
    evaluated_at_utc: str
    evidence_valid_until_utc: str


@dataclass(frozen=True)
class StageAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def evaluate_supply_chain(e: SupplyChainEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("source_commit", "artifact_digest"):
        value = getattr(e, name)
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            reasons.append(f"{name} must be lowercase SHA-256")
    for name in ("build_run_ref", "builder_identity_ref", "dependency_lock_ref",
                 "dependency_scan_ref", "provenance_ref", "independent_review_ref"):
        if not isinstance(getattr(e, name), str) or not getattr(e, name).strip():
            reasons.append(f"{name} is required")
    if e.build_reproducible is not True:
        reasons.append("reproducible build evidence is absent")
    if isinstance(e.critical_vulnerabilities, bool) or not isinstance(e.critical_vulnerabilities, int) or e.critical_vulnerabilities < 0:
        reasons.append("critical_vulnerabilities must be a non-negative integer")
    elif e.critical_vulnerabilities:
        reasons.append("critical vulnerabilities remain unresolved")
    try:
        evaluated = _utc(e.evaluated_at_utc, "evaluated_at_utc")
        expiry = _utc(e.evidence_valid_until_utc, "evidence_valid_until_utc")
        if expiry <= evaluated:
            reasons.append("supply-chain evidence is expired")
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))
    if reasons:
        return StageAssessment(20, "HOLD", tuple(reasons))
    return StageAssessment(20, "SUPPLY_CHAIN_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("references and attestations are structurally complete; provenance and signatures are not authenticated",))


@dataclass(frozen=True)
class RestoreDrillEvidence:
    backup_ref: str
    backup_digest: str
    backup_created_at_utc: str
    restore_started_at_utc: str
    restore_completed_at_utc: str
    restored_state_digest: str
    expected_state_digest: str
    independent_restore_review_ref: str
    recovery_point_objective_seconds: int
    recovery_time_objective_seconds: int
    measured_data_loss_seconds: int
    measured_restore_seconds: int
    integrity_check_passed: bool


def evaluate_restore_drill(e: RestoreDrillEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("backup_digest", "restored_state_digest", "expected_state_digest"):
        value = getattr(e, name)
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            reasons.append(f"{name} must be lowercase SHA-256")
    for name in ("backup_ref", "independent_restore_review_ref"):
        if not isinstance(getattr(e, name), str) or not getattr(e, name).strip():
            reasons.append(f"{name} is required")
    try:
        created = _utc(e.backup_created_at_utc, "backup_created_at_utc")
        started = _utc(e.restore_started_at_utc, "restore_started_at_utc")
        completed = _utc(e.restore_completed_at_utc, "restore_completed_at_utc")
        if started < created or completed < started:
            reasons.append("restore timestamps are not chronological")
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))
    for name in ("recovery_point_objective_seconds", "recovery_time_objective_seconds",
                 "measured_data_loss_seconds", "measured_restore_seconds"):
        value = getattr(e, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            reasons.append(f"{name} must be a non-negative integer")
    if e.integrity_check_passed is not True:
        reasons.append("backup integrity check did not pass")
    if e.restored_state_digest != e.expected_state_digest:
        reasons.append("restored state digest differs from expected state")
    if (isinstance(e.measured_data_loss_seconds, int) and
        isinstance(e.recovery_point_objective_seconds, int) and
        e.measured_data_loss_seconds > e.recovery_point_objective_seconds):
        reasons.append("recovery point objective exceeded")
    if (isinstance(e.measured_restore_seconds, int) and
        isinstance(e.recovery_time_objective_seconds, int) and
        e.measured_restore_seconds > e.recovery_time_objective_seconds):
        reasons.append("recovery time objective exceeded")
    if reasons:
        return StageAssessment(21, "RESTORE_DRILL_FAILED", tuple(reasons))
    return StageAssessment(21, "RESTORE_DRILL_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("restore evidence is structurally consistent; backup bytes and external review are not independently verified",))


@dataclass(frozen=True)
class IncidentDrillEvidence:
    incident_id: str
    severity: str
    declared_at_utc: str
    contained_at_utc: str
    closed_at_utc: str
    incident_timeline_ref: str
    escalation_record_ref: str
    kill_switch_drill_ref: str
    credential_containment_ref: str
    postmortem_ref: str
    independent_observer_ref: str
    unauthorized_actions: int
    containment_sla_seconds: int
    measured_containment_seconds: int
    corrective_actions_open: int


def evaluate_incident_drill(e: IncidentDrillEvidence) -> StageAssessment:
    reasons: list[str] = []
    if not isinstance(e.incident_id, str) or not e.incident_id.strip():
        reasons.append("incident_id is required")
    if e.severity not in {"SEV1", "SEV2", "SEV3"}:
        reasons.append("severity must be SEV1, SEV2, or SEV3")
    for name in ("incident_timeline_ref", "escalation_record_ref", "kill_switch_drill_ref",
                 "credential_containment_ref", "postmortem_ref", "independent_observer_ref"):
        if not isinstance(getattr(e, name), str) or not getattr(e, name).strip():
            reasons.append(f"{name} is required")
    try:
        declared = _utc(e.declared_at_utc, "declared_at_utc")
        contained = _utc(e.contained_at_utc, "contained_at_utc")
        closed = _utc(e.closed_at_utc, "closed_at_utc")
        if contained < declared or closed < contained:
            reasons.append("incident timestamps are not chronological")
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))
    for name in ("unauthorized_actions", "containment_sla_seconds",
                 "measured_containment_seconds", "corrective_actions_open"):
        value = getattr(e, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            reasons.append(f"{name} must be a non-negative integer")
    if isinstance(e.unauthorized_actions, int) and e.unauthorized_actions > 0:
        reasons.append("unauthorized actions occurred during drill")
    if (isinstance(e.measured_containment_seconds, int) and
        isinstance(e.containment_sla_seconds, int) and
        e.measured_containment_seconds > e.containment_sla_seconds):
        reasons.append("containment SLA exceeded")
    if isinstance(e.corrective_actions_open, int) and e.corrective_actions_open:
        reasons.append("corrective actions remain open")
    if reasons:
        return StageAssessment(22, "INCIDENT_DRILL_FAILED", tuple(reasons))
    return StageAssessment(22, "INCIDENT_DRILL_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("drill attestations are complete; no real incident response or kill switch was executed",))


@dataclass(frozen=True)
class FinalReadinessEvidence:
    stage20_status: str
    stage21_status: str
    stage22_status: str
    stage19_status: str
    full_regression_passed: bool
    stage4_lineage_verified: bool
    oos_independent_review_ref: str
    venue_economics_review_ref: str
    credential_revocation_review_ref: str
    operational_owner_approval_ref: str
    release_candidate_digest: str
    reviewed_candidate_digest: str
    open_critical_findings: int


def evaluate_final_readiness(e: FinalReadinessEvidence) -> StageAssessment:
    reasons: list[str] = []
    required_statuses = (
        ("stage20", e.stage20_status, "SUPPLY_CHAIN_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage21", e.stage21_status, "RESTORE_DRILL_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage22", e.stage22_status, "INCIDENT_DRILL_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage19", e.stage19_status, "READY_FOR_CONTROLLED_TESTNET_REVIEW"),
    )
    for label, actual, expected in required_statuses:
        if actual != expected:
            reasons.append(f"{label} prerequisite is not satisfied")
    if e.full_regression_passed is not True:
        reasons.append("full repository regression is not certified")
    if e.stage4_lineage_verified is not True:
        reasons.append("Stage 4 source lineage is not verified")
    for name in ("oos_independent_review_ref", "venue_economics_review_ref",
                 "credential_revocation_review_ref", "operational_owner_approval_ref"):
        if not isinstance(getattr(e, name), str) or not getattr(e, name).strip():
            reasons.append(f"{name} is required")
    for name in ("release_candidate_digest", "reviewed_candidate_digest"):
        value = getattr(e, name)
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            reasons.append(f"{name} must be lowercase SHA-256")
    if e.release_candidate_digest != e.reviewed_candidate_digest:
        reasons.append("reviewed digest does not match release candidate")
    if isinstance(e.open_critical_findings, bool) or not isinstance(e.open_critical_findings, int) or e.open_critical_findings < 0:
        reasons.append("open_critical_findings must be a non-negative integer")
    elif e.open_critical_findings:
        reasons.append("critical findings remain open")
    if reasons:
        return StageAssessment(23, "HOLD", tuple(reasons))
    return StageAssessment(23, "READY_FOR_INDEPENDENT_RELEASE_REVIEW",
                           ("evidence supports independent release review only; deployment and live trading remain disabled",))
