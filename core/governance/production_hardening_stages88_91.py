"""Offline, reference-only evidence gates for QuantEngine Stages 88–91."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import re

@dataclass(frozen=True)
class Assessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False

def _valid_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0

def _check(refs: tuple[tuple[str, str], ...], counts: tuple[tuple[str, int], ...],
           flags: tuple[tuple[str, bool], ...], assessed_at: str) -> list[str]:
    reasons: list[str] = []
    for name, value in refs:
        if not isinstance(value, str) or not value.strip():
            reasons.append(f"{name} reference is required")
    try:
        parsed = datetime.fromisoformat(assessed_at.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        reasons.append("assessed_at must be ISO-8601 with an explicit UTC offset")
    for name, value in counts:
        if not _valid_count(value):
            reasons.append(f"{name} must be a non-negative integer")
    for name, value in flags:
        if value is not True:
            reasons.append(f"{name} must be explicitly attested true")
    return reasons

def _equal_counts(left: object, right: object) -> bool:
    return _valid_count(left) and _valid_count(right) and left == right

def _result(stage: int, prefix: str, reasons: list[str], note: str) -> Assessment:
    if reasons:
        return Assessment(stage, f"{prefix}_HOLD", tuple(reasons))
    return Assessment(stage, f"{prefix}_COMPLETE_UNVERIFIED", (note,))

@dataclass(frozen=True)
class DataQualityGovernance:
    assessment_ref: str
    source_inventory_ref: str
    schema_contract_ref: str
    quality_report_ref: str
    freshness_report_ref: str
    exception_register_ref: str
    assessed_at: str
    sources_in_scope: int
    sources_with_schema_validation: int
    sources_with_freshness_checks: int
    records_in_scope: int
    records_validated: int
    unresolved_critical_exceptions: int
    stale_critical_feeds: int
    duplicate_critical_records: int
    independent_review_attested: bool

def evaluate_data_quality(e: DataQualityGovernance) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "source_inventory_ref", "schema_contract_ref", "quality_report_ref",
        "freshness_report_ref", "exception_register_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "sources_in_scope", "sources_with_schema_validation", "sources_with_freshness_checks",
        "records_in_scope", "records_validated", "unresolved_critical_exceptions",
        "stale_critical_feeds", "duplicate_critical_records"))
    r = _check(refs, counts, (("independent_review_attested", e.independent_review_attested),), e.assessed_at)
    for name in ("sources_with_schema_validation", "sources_with_freshness_checks"):
        if not _equal_counts(getattr(e, name), e.sources_in_scope):
            r.append(f"{name} must cover every in-scope source")
    if not _equal_counts(e.records_validated, e.records_in_scope):
        r.append("every in-scope record must have validation evidence")
    for name in ("unresolved_critical_exceptions", "stale_critical_feeds", "duplicate_critical_records"):
        if _valid_count(getattr(e, name)) and getattr(e, name) != 0:
            r.append(f"{name} must be zero")
    return _result(88, "DATA_QUALITY", r,
        "source quality and freshness evidence remain independently unverified; no market-data feed or production dataset is queried")

@dataclass(frozen=True)
class CapacityGovernance:
    assessment_ref: str
    capacity_inventory_ref: str
    workload_forecast_ref: str
    headroom_policy_ref: str
    stress_test_report_ref: str
    queue_analysis_ref: str
    recovery_plan_ref: str
    assessed_at: str
    resources_in_scope: int
    resources_with_forecasts: int
    resources_with_headroom_evidence: int
    scenarios_in_scope: int
    scenarios_tested: int
    headroom_breaches: int
    unbounded_queues: int
    unowned_capacity_risks: int
    independent_review_attested: bool

def evaluate_capacity_governance(e: CapacityGovernance) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "capacity_inventory_ref", "workload_forecast_ref", "headroom_policy_ref",
        "stress_test_report_ref", "queue_analysis_ref", "recovery_plan_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "resources_in_scope", "resources_with_forecasts", "resources_with_headroom_evidence",
        "scenarios_in_scope", "scenarios_tested", "headroom_breaches", "unbounded_queues",
        "unowned_capacity_risks"))
    r = _check(refs, counts, (("independent_review_attested", e.independent_review_attested),), e.assessed_at)
    for name in ("resources_with_forecasts", "resources_with_headroom_evidence"):
        if not _equal_counts(getattr(e, name), e.resources_in_scope):
            r.append(f"{name} must cover every in-scope resource")
    if not _equal_counts(e.scenarios_tested, e.scenarios_in_scope):
        r.append("every capacity scenario must have test evidence")
    for name in ("headroom_breaches", "unbounded_queues", "unowned_capacity_risks"):
        if _valid_count(getattr(e, name)) and getattr(e, name) != 0:
            r.append(f"{name} must be zero")
    return _result(89, "CAPACITY_GOVERNANCE", r,
        "forecast, headroom and stress-test artifacts remain independently unverified; no live load test or resource change is performed")

@dataclass(frozen=True)
class DependencyResilience:
    assessment_ref: str
    dependency_inventory_ref: str
    criticality_register_ref: str
    assurance_pack_ref: str
    continuity_evidence_ref: str
    concentration_review_ref: str
    remediation_register_ref: str
    assessed_at: str
    dependencies_in_scope: int
    dependencies_classified: int
    critical_dependencies: int
    critical_dependencies_with_assurance: int
    critical_dependencies_with_continuity: int
    unresolved_critical_findings: int
    unmitigated_single_points_of_failure: int
    independent_review_attested: bool

def evaluate_dependency_resilience(e: DependencyResilience) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "dependency_inventory_ref", "criticality_register_ref", "assurance_pack_ref",
        "continuity_evidence_ref", "concentration_review_ref", "remediation_register_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "dependencies_in_scope", "dependencies_classified", "critical_dependencies",
        "critical_dependencies_with_assurance", "critical_dependencies_with_continuity",
        "unresolved_critical_findings", "unmitigated_single_points_of_failure"))
    r = _check(refs, counts, (("independent_review_attested", e.independent_review_attested),), e.assessed_at)
    if not _equal_counts(e.dependencies_classified, e.dependencies_in_scope):
        r.append("every in-scope dependency must be classified")
    for name in ("critical_dependencies_with_assurance", "critical_dependencies_with_continuity"):
        if not _equal_counts(getattr(e, name), e.critical_dependencies):
            r.append(f"{name} must cover every critical dependency")
    for name in ("unresolved_critical_findings", "unmitigated_single_points_of_failure"):
        if _valid_count(getattr(e, name)) and getattr(e, name) != 0:
            r.append(f"{name} must be zero")
    return _result(90, "DEPENDENCY_RESILIENCE", r,
        "third-party assurance and continuity evidence require independent verification; no vendor or external service is contacted")

@dataclass(frozen=True)
class AuditLogIntegrity:
    assessment_ref: str
    event_catalog_ref: str
    logging_coverage_ref: str
    append_only_control_ref: str
    integrity_checkpoint_ref: str
    retention_schedule_ref: str
    time_sync_evidence_ref: str
    incident_register_ref: str
    assessed_at: str
    event_classes_in_scope: int
    event_classes_logged: int
    checkpoints_in_scope: int
    checkpoints_verified: int
    uncovered_critical_event_classes: int
    unresolved_integrity_incidents: int
    retention_gaps: int
    clock_drift_exceptions: int
    independent_review_attested: bool

def evaluate_audit_log_integrity(e: AuditLogIntegrity) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "event_catalog_ref", "logging_coverage_ref", "append_only_control_ref",
        "integrity_checkpoint_ref", "retention_schedule_ref", "time_sync_evidence_ref", "incident_register_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "event_classes_in_scope", "event_classes_logged", "checkpoints_in_scope", "checkpoints_verified",
        "uncovered_critical_event_classes", "unresolved_integrity_incidents", "retention_gaps",
        "clock_drift_exceptions"))
    r = _check(refs, counts, (("independent_review_attested", e.independent_review_attested),), e.assessed_at)
    if not _equal_counts(e.event_classes_logged, e.event_classes_in_scope):
        r.append("every in-scope event class must have logging coverage evidence")
    if not _equal_counts(e.checkpoints_verified, e.checkpoints_in_scope):
        r.append("every in-scope integrity checkpoint must be verified")
    for name in ("uncovered_critical_event_classes", "unresolved_integrity_incidents",
                 "retention_gaps", "clock_drift_exceptions"):
        if _valid_count(getattr(e, name)) and getattr(e, name) != 0:
            r.append(f"{name} must be zero")
    return _result(91, "AUDIT_LOG_INTEGRITY", r,
        "append-only, retention and integrity references remain independently unverified; no production logs are read, changed or deleted")
