"""Offline evidence gates for production-hardening Stages 44–47.

All inputs are operator-supplied attestations. No live systems, registries,
identity providers, vendors, deployment systems, exchanges, or trading paths
are queried or changed by these validators.
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
class SupplyChainEvidence:
    component: str
    source_commit: str
    source_tree_digest: str
    dependency_lock_digest: str
    sbom_digest: str
    build_attestation_ref: str
    builder_identity_ref: str
    signature_verification_ref: str
    independent_review_ref: str
    built_at_utc: str
    source_matches_build: bool
    build_reproducible: bool
    signature_valid: bool
    dependencies_pinned: bool
    sbom_complete: bool
    critical_vulnerabilities: int
    high_vulnerabilities: int
    unapproved_components: int


def evaluate_supply_chain(e: SupplyChainEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("component", "build_attestation_ref", "builder_identity_ref",
                 "signature_verification_ref", "independent_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    for name in ("source_tree_digest", "dependency_lock_digest", "sbom_digest"):
        _digest(getattr(e, name), name, reasons)
    _timestamp(e.built_at_utc, "built_at_utc", reasons)
    for name in ("source_matches_build", "build_reproducible", "signature_valid",
                 "dependencies_pinned", "sbom_complete"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    for name in ("critical_vulnerabilities", "high_vulnerabilities", "unapproved_components"):
        _count(getattr(e, name), name, reasons)
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    if reasons:
        return StageAssessment(44, "SUPPLY_CHAIN_HOLD", tuple(reasons))
    return StageAssessment(44, "SUPPLY_CHAIN_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("artifact provenance, signatures and component inventory require independent verification",))


@dataclass(frozen=True)
class ConfigurationEvidence:
    system: str
    source_commit: str
    observed_config_digest: str
    approved_baseline_digest: str
    config_inventory_ref: str
    change_approval_ref: str
    policy_review_ref: str
    rollback_test_ref: str
    independent_review_ref: str
    reviewed_at_utc: str
    environment: str
    drifted_settings: int
    unapproved_changes: int
    embedded_secret_findings: int
    policy_exceptions: int
    rollback_tested: bool
    baseline_approved: bool
    environment_isolated: bool


def evaluate_configuration(e: ConfigurationEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("system", "config_inventory_ref", "change_approval_ref",
                 "policy_review_ref", "rollback_test_ref", "independent_review_ref",
                 "environment"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    for name in ("observed_config_digest", "approved_baseline_digest"):
        _digest(getattr(e, name), name, reasons)
    _timestamp(e.reviewed_at_utc, "reviewed_at_utc", reasons)
    if (isinstance(e.observed_config_digest, str) and isinstance(e.approved_baseline_digest, str)
            and _SHA256.fullmatch(e.observed_config_digest)
            and _SHA256.fullmatch(e.approved_baseline_digest)
            and e.observed_config_digest != e.approved_baseline_digest
            and e.drifted_settings == 0):
        reasons.append("configuration digest differs from approved baseline without enumerated drift")
    for name in ("drifted_settings", "unapproved_changes", "embedded_secret_findings", "policy_exceptions"):
        _count(getattr(e, name), name, reasons)
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    for name in ("rollback_tested", "baseline_approved", "environment_isolated"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if reasons:
        return StageAssessment(45, "CONFIGURATION_HOLD", tuple(reasons))
    return StageAssessment(45, "CONFIGURATION_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("configuration inventory and baseline approval require independent verification",))


@dataclass(frozen=True)
class IncidentResponseEvidence:
    service: str
    source_commit: str
    incident_playbook_ref: str
    on_call_roster_ref: str
    exercise_or_incident_report_ref: str
    evidence_preservation_ref: str
    communications_record_ref: str
    postmortem_ref: str
    independent_review_ref: str
    detected_at_utc: str
    acknowledged_at_utc: str
    contained_at_utc: str
    maximum_acknowledgement_seconds: int
    maximum_containment_seconds: int
    evidence_preserved: bool
    escalation_tested: bool
    stakeholder_communications_complete: bool
    corrective_actions_tracked: bool
    unresolved_critical_findings: int


def evaluate_incident_response(e: IncidentResponseEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("service", "incident_playbook_ref", "on_call_roster_ref",
                 "exercise_or_incident_report_ref", "evidence_preservation_ref",
                 "communications_record_ref", "postmortem_ref", "independent_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    detected = _timestamp(e.detected_at_utc, "detected_at_utc", reasons)
    acknowledged = _timestamp(e.acknowledged_at_utc, "acknowledged_at_utc", reasons)
    contained = _timestamp(e.contained_at_utc, "contained_at_utc", reasons)
    for name in ("maximum_acknowledgement_seconds", "maximum_containment_seconds",
                 "unresolved_critical_findings"):
        _count(getattr(e, name), name, reasons)
    if detected and acknowledged:
        elapsed = (acknowledged - detected).total_seconds()
        if elapsed < 0:
            reasons.append("acknowledgement predates detection")
        elif elapsed > e.maximum_acknowledgement_seconds:
            reasons.append("acknowledgement target exceeded")
    if detected and contained:
        elapsed = (contained - detected).total_seconds()
        if elapsed < 0:
            reasons.append("containment predates detection")
        elif elapsed > e.maximum_containment_seconds:
            reasons.append("containment target exceeded")
    for name in ("evidence_preserved", "escalation_tested",
                 "stakeholder_communications_complete", "corrective_actions_tracked"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if isinstance(e.unresolved_critical_findings, int) and not isinstance(e.unresolved_critical_findings, bool) and e.unresolved_critical_findings:
        reasons.append("critical incident findings remain unresolved")
    if reasons:
        return StageAssessment(46, "INCIDENT_RESPONSE_HOLD", tuple(reasons))
    return StageAssessment(46, "INCIDENT_RESPONSE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("exercise results, response timings and corrective-action closure require independent verification",))


@dataclass(frozen=True)
class ThirdPartyRiskEvidence:
    service: str
    source_commit: str
    vendor_inventory_digest: str
    critical_vendor_register_ref: str
    due_diligence_report_ref: str
    contractual_controls_ref: str
    service_level_report_ref: str
    exit_and_portability_plan_ref: str
    independent_risk_review_ref: str
    reviewed_at_utc: str
    critical_vendors_total: int
    critical_vendors_reviewed: int
    overdue_assessments: int
    unresolved_critical_findings: int
    unapproved_subprocessors: int
    tested_exit_plan: bool
    service_levels_met: bool
    concentration_risk_accepted: bool
    material_incidents_disclosed: bool


def evaluate_third_party_risk(e: ThirdPartyRiskEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("service", "critical_vendor_register_ref", "due_diligence_report_ref",
                 "contractual_controls_ref", "service_level_report_ref",
                 "exit_and_portability_plan_ref", "independent_risk_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    _digest(e.vendor_inventory_digest, "vendor_inventory_digest", reasons)
    _timestamp(e.reviewed_at_utc, "reviewed_at_utc", reasons)
    for name in ("critical_vendors_total", "critical_vendors_reviewed", "overdue_assessments",
                 "unresolved_critical_findings", "unapproved_subprocessors"):
        _count(getattr(e, name), name, reasons)
    if (isinstance(e.critical_vendors_reviewed, int) and not isinstance(e.critical_vendors_reviewed, bool)
            and isinstance(e.critical_vendors_total, int) and not isinstance(e.critical_vendors_total, bool)
            and e.critical_vendors_reviewed < e.critical_vendors_total):
        reasons.append("not all critical vendors have current reviews")
    for name in ("overdue_assessments", "unresolved_critical_findings", "unapproved_subprocessors"):
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    for name in ("tested_exit_plan", "service_levels_met",
                 "concentration_risk_accepted", "material_incidents_disclosed"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if reasons:
        return StageAssessment(47, "THIRD_PARTY_RISK_HOLD", tuple(reasons))
    return StageAssessment(47, "THIRD_PARTY_RISK_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("vendor due diligence, contractual controls and exit readiness require independent verification",))
