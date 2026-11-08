"""Offline evidence gates for production-hardening Stages 40–43.

All records are operator-supplied evidence. These functions do not inspect
production infrastructure, invoke identity providers, restore systems, or
authorize access, release, deployment, or trading.
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


def _required(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{name} is required")


def _digest(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        reasons.append(f"{name} must be a lowercase SHA-256 digest")


def _commit(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _GIT_SHA.fullmatch(value):
        reasons.append(f"{name} must be a 40-character Git commit ID")


def _count(value: int, name: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append(f"{name} must be a non-negative integer")


def _number(value: float, name: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        reasons.append(f"{name} must be a finite number")


def _timestamp(value: str, name: str, reasons: list[str]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (AttributeError, TypeError, ValueError):
        reasons.append(f"{name} must be an ISO-8601 timestamp with UTC offset")
        return None


@dataclass(frozen=True)
class DataGovernanceEvidence:
    dataset_ref: str
    source_commit: str
    dataset_digest: str
    schema_digest: str
    lineage_manifest_ref: str
    data_owner_ref: str
    classification: str
    permitted_use_ref: str
    retention_policy_ref: str
    deletion_attestation_ref: str
    quality_report_ref: str
    privacy_review_ref: str
    consent_or_lawful_basis_ref: str
    collected_at_utc: str
    reviewed_at_utc: str
    required_fields_present: bool
    schema_compatible: bool
    provenance_complete: bool
    personal_data_minimized: bool
    retention_within_policy: bool
    deletion_requests_satisfied: bool
    unresolved_quality_critical: int
    unauthorized_data_sources: int


def evaluate_data_governance(e: DataGovernanceEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("dataset_ref", "lineage_manifest_ref", "data_owner_ref",
                 "permitted_use_ref", "retention_policy_ref", "deletion_attestation_ref",
                 "quality_report_ref", "privacy_review_ref", "consent_or_lawful_basis_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    for name in ("dataset_digest", "schema_digest"):
        _digest(getattr(e, name), name, reasons)
    if e.classification not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        reasons.append("classification must be an approved data classification")
    collected = _timestamp(e.collected_at_utc, "collected_at_utc", reasons)
    reviewed = _timestamp(e.reviewed_at_utc, "reviewed_at_utc", reasons)
    if collected and reviewed and reviewed < collected:
        reasons.append("review timestamp predates data collection")
    for name in ("required_fields_present", "schema_compatible", "provenance_complete",
                 "personal_data_minimized", "retention_within_policy",
                 "deletion_requests_satisfied"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    for name in ("unresolved_quality_critical", "unauthorized_data_sources"):
        _count(getattr(e, name), name, reasons)
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    if reasons:
        return StageAssessment(40, "DATA_GOVERNANCE_HOLD", tuple(reasons))
    return StageAssessment(40, "DATA_GOVERNANCE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("dataset lineage, privacy basis, retention and deletion attestations require independent verification",))


@dataclass(frozen=True)
class DisasterRecoveryEvidence:
    service: str
    source_commit: str
    recovery_plan_ref: str
    backup_catalog_ref: str
    backup_digest: str
    restore_test_report_ref: str
    failover_test_report_ref: str
    dependency_map_ref: str
    independent_recovery_review_ref: str
    recovery_point_objective_seconds: int
    measured_data_loss_seconds: int
    recovery_time_objective_seconds: int
    measured_recovery_seconds: int
    backup_age_seconds: int
    maximum_backup_age_seconds: int
    restore_success: bool
    failover_success: bool
    backup_integrity_verified: bool
    dependencies_recovered: bool
    rollback_path_tested: bool
    unresolved_critical_recovery_findings: int
    last_drill_at_utc: str


def evaluate_disaster_recovery(e: DisasterRecoveryEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("service", "recovery_plan_ref", "backup_catalog_ref",
                 "restore_test_report_ref", "failover_test_report_ref",
                 "dependency_map_ref", "independent_recovery_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    _digest(e.backup_digest, "backup_digest", reasons)
    for name in ("recovery_point_objective_seconds", "measured_data_loss_seconds",
                 "recovery_time_objective_seconds", "measured_recovery_seconds",
                 "backup_age_seconds", "maximum_backup_age_seconds",
                 "unresolved_critical_recovery_findings"):
        _count(getattr(e, name), name, reasons)
    for measured, target, label in (
        (e.measured_data_loss_seconds, e.recovery_point_objective_seconds, "data loss exceeds RPO"),
        (e.measured_recovery_seconds, e.recovery_time_objective_seconds, "recovery duration exceeds RTO"),
        (e.backup_age_seconds, e.maximum_backup_age_seconds, "backup age exceeds policy"),
    ):
        if (isinstance(measured, int) and not isinstance(measured, bool) and measured >= 0
                and isinstance(target, int) and not isinstance(target, bool) and target >= 0
                and measured > target):
            reasons.append(label)
    for name in ("restore_success", "failover_success", "backup_integrity_verified",
                 "dependencies_recovered", "rollback_path_tested"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if isinstance(e.unresolved_critical_recovery_findings, int) and not isinstance(e.unresolved_critical_recovery_findings, bool) and e.unresolved_critical_recovery_findings:
        reasons.append("critical recovery findings remain unresolved")
    _timestamp(e.last_drill_at_utc, "last_drill_at_utc", reasons)
    if reasons:
        return StageAssessment(41, "DISASTER_RECOVERY_HOLD", tuple(reasons))
    return StageAssessment(41, "DISASTER_RECOVERY_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("backup integrity and measured restore/failover results require independent rehearsal",))


@dataclass(frozen=True)
class AccessControlEvidence:
    system: str
    source_commit: str
    access_inventory_digest: str
    identity_provider_review_ref: str
    privileged_access_review_ref: str
    service_account_inventory_ref: str
    joiner_mover_leaver_report_ref: str
    separation_of_duties_matrix_ref: str
    independent_security_review_ref: str
    reviewed_at_utc: str
    mfa_coverage_percent: float
    mfa_minimum_percent: float
    privileged_accounts_reviewed: int
    privileged_accounts_total: int
    stale_accounts: int
    orphaned_service_accounts: int
    shared_human_accounts: int
    excessive_privilege_findings: int
    unapproved_access_changes: int
    break_glass_accounts_tested: bool
    break_glass_use_audited: bool
    dual_control_for_critical_actions: bool


def evaluate_access_control(e: AccessControlEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("system", "identity_provider_review_ref", "privileged_access_review_ref",
                 "service_account_inventory_ref", "joiner_mover_leaver_report_ref",
                 "separation_of_duties_matrix_ref", "independent_security_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    _digest(e.access_inventory_digest, "access_inventory_digest", reasons)
    _timestamp(e.reviewed_at_utc, "reviewed_at_utc", reasons)
    for name in ("mfa_coverage_percent", "mfa_minimum_percent"):
        _number(getattr(e, name), name, reasons)
    if (isinstance(e.mfa_coverage_percent, (int, float)) and not isinstance(e.mfa_coverage_percent, bool)
            and isinstance(e.mfa_minimum_percent, (int, float)) and not isinstance(e.mfa_minimum_percent, bool)
            and e.mfa_coverage_percent < e.mfa_minimum_percent):
        reasons.append("MFA coverage is below policy minimum")
    for name in ("privileged_accounts_reviewed", "privileged_accounts_total", "stale_accounts",
                 "orphaned_service_accounts", "shared_human_accounts",
                 "excessive_privilege_findings", "unapproved_access_changes"):
        _count(getattr(e, name), name, reasons)
    if (isinstance(e.privileged_accounts_reviewed, int) and isinstance(e.privileged_accounts_total, int)
            and e.privileged_accounts_reviewed < e.privileged_accounts_total):
        reasons.append("not all privileged accounts have been reviewed")
    for name in ("stale_accounts", "orphaned_service_accounts", "shared_human_accounts",
                 "excessive_privilege_findings", "unapproved_access_changes"):
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    for name in ("break_glass_accounts_tested", "break_glass_use_audited",
                 "dual_control_for_critical_actions"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if reasons:
        return StageAssessment(42, "ACCESS_CONTROL_HOLD", tuple(reasons))
    return StageAssessment(42, "ACCESS_CONTROL_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("identity-provider configuration and access inventory require independent confirmation",))


@dataclass(frozen=True)
class AuditEvidence:
    system: str
    source_commit: str
    audit_bundle_digest: str
    event_schema_ref: str
    immutable_storage_ref: str
    retention_schedule_ref: str
    time_sync_evidence_ref: str
    independent_audit_review_ref: str
    period_start_utc: str
    period_end_utc: str
    generated_at_utc: str
    required_event_coverage_percent: float
    minimum_event_coverage_percent: float
    tamper_check_passed: bool
    retention_lock_enabled: bool
    access_to_audit_logs_restricted: bool
    privileged_events_attributed: bool
    event_sequence_gaps: int
    missing_critical_events: int
    unexplained_clock_skew_ms: int
    unresolved_audit_findings: int


def evaluate_audit_evidence(e: AuditEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("system", "event_schema_ref", "immutable_storage_ref",
                 "retention_schedule_ref", "time_sync_evidence_ref",
                 "independent_audit_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    _digest(e.audit_bundle_digest, "audit_bundle_digest", reasons)
    start = _timestamp(e.period_start_utc, "period_start_utc", reasons)
    end = _timestamp(e.period_end_utc, "period_end_utc", reasons)
    generated = _timestamp(e.generated_at_utc, "generated_at_utc", reasons)
    if start and end and end <= start:
        reasons.append("audit period must have positive duration")
    if end and generated and generated < end:
        reasons.append("audit bundle generation predates audit period end")
    for name in ("required_event_coverage_percent", "minimum_event_coverage_percent"):
        _number(getattr(e, name), name, reasons)
    if (isinstance(e.required_event_coverage_percent, (int, float))
            and isinstance(e.minimum_event_coverage_percent, (int, float))
            and e.required_event_coverage_percent < e.minimum_event_coverage_percent):
        reasons.append("required audit event coverage is below policy minimum")
    for name in ("tamper_check_passed", "retention_lock_enabled",
                 "access_to_audit_logs_restricted", "privileged_events_attributed"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    for name in ("event_sequence_gaps", "missing_critical_events",
                 "unexplained_clock_skew_ms", "unresolved_audit_findings"):
        _count(getattr(e, name), name, reasons)
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    if reasons:
        return StageAssessment(43, "AUDIT_EVIDENCE_HOLD", tuple(reasons))
    return StageAssessment(43, "AUDIT_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("log immutability, coverage, retention and clock synchronization require independent verification",))
