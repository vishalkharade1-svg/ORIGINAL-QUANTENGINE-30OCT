"""Offline evidence gates for production-hardening Stages 60–63.

Validators inspect operator-supplied evidence references only. They never access
cryptographic material, scan systems, run security tests, or authorize release.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
class KeyLifecycleEvidence:
    key_inventory_digest: str
    source_commit: str
    inventory_record_ref: str
    rotation_policy_ref: str
    rotation_log_ref: str
    dual_control_attestation_ref: str
    hsm_assurance_ref: str
    independent_review_ref: str
    assessed_at_utc: str
    keys_in_scope: int
    unowned_keys: int
    expired_keys: int
    overdue_rotations: int
    unresolved_compromises: int
    rotation_coverage_complete: bool
    dual_control_verified: bool
    hardware_boundary_attested: bool


def evaluate_key_lifecycle(e: KeyLifecycleEvidence) -> StageAssessment:
    r: list[str] = []
    for f in ("inventory_record_ref", "rotation_policy_ref", "rotation_log_ref",
              "dual_control_attestation_ref", "hsm_assurance_ref", "independent_review_ref"):
        _required(getattr(e, f), f, r)
    _digest(e.key_inventory_digest, "key_inventory_digest", r)
    _commit(e.source_commit, "source_commit", r)
    _date(e.assessed_at_utc, "assessed_at_utc", r)
    for f in ("keys_in_scope", "unowned_keys", "expired_keys", "overdue_rotations",
              "unresolved_compromises"):
        _count(getattr(e, f), f, r)
    if isinstance(e.keys_in_scope, int) and not isinstance(e.keys_in_scope, bool) and e.keys_in_scope == 0:
        r.append("keys_in_scope must be greater than zero")
    for f in ("unowned_keys", "expired_keys", "overdue_rotations", "unresolved_compromises"):
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{f} must be zero")
    for f in ("rotation_coverage_complete", "dual_control_verified", "hardware_boundary_attested"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return StageAssessment(60, "KEY_LIFECYCLE_HOLD", tuple(r))
    return StageAssessment(60, "KEY_LIFECYCLE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("key custody, rotation records and hardware-boundary claims require independent verification",))


@dataclass(frozen=True)
class ThreatModelEvidence:
    threat_model_digest: str
    attack_surface_digest: str
    source_commit: str
    threat_model_ref: str
    asset_register_ref: str
    trust_boundary_review_ref: str
    mitigation_register_ref: str
    independent_architecture_review_ref: str
    assessed_at_utc: str
    assets_in_scope: int
    trust_boundaries_reviewed: int
    threats_identified: int
    threats_mitigated: int
    unowned_threats: int
    high_residual_threats: int
    scope_complete: bool
    mitigations_tested: bool


def evaluate_threat_model(e: ThreatModelEvidence) -> StageAssessment:
    r: list[str] = []
    for f in ("threat_model_ref", "asset_register_ref", "trust_boundary_review_ref",
              "mitigation_register_ref", "independent_architecture_review_ref"):
        _required(getattr(e, f), f, r)
    _digest(e.threat_model_digest, "threat_model_digest", r)
    _digest(e.attack_surface_digest, "attack_surface_digest", r)
    _commit(e.source_commit, "source_commit", r)
    _date(e.assessed_at_utc, "assessed_at_utc", r)
    for f in ("assets_in_scope", "trust_boundaries_reviewed", "threats_identified",
              "threats_mitigated", "unowned_threats", "high_residual_threats"):
        _count(getattr(e, f), f, r)
    if isinstance(e.assets_in_scope, int) and not isinstance(e.assets_in_scope, bool) and e.assets_in_scope == 0:
        r.append("assets_in_scope must be greater than zero")
    if isinstance(e.trust_boundaries_reviewed, int) and not isinstance(e.trust_boundaries_reviewed, bool) and e.trust_boundaries_reviewed == 0:
        r.append("trust_boundaries_reviewed must be greater than zero")
    if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
           for v in (e.threats_identified, e.threats_mitigated)):
        if e.threats_mitigated > e.threats_identified:
            r.append("threats_mitigated cannot exceed threats_identified")
        if e.threats_mitigated < e.threats_identified:
            r.append("all identified threats must have tested mitigations")
    for f in ("unowned_threats", "high_residual_threats"):
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{f} must be zero")
    for f in ("scope_complete", "mitigations_tested"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return StageAssessment(61, "THREAT_MODEL_HOLD", tuple(r))
    return StageAssessment(61, "THREAT_MODEL_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("asset completeness, threat analysis and mitigation test quality require independent confirmation",))


@dataclass(frozen=True)
class SecurityTestingEvidence:
    source_commit: str
    build_artifact_digest: str
    build_attestation_ref: str
    sast_report_ref: str
    dast_report_ref: str
    dependency_scan_ref: str
    penetration_test_ref: str
    remediation_retest_ref: str
    independent_assessor_ref: str
    assessed_at_utc: str
    critical_findings: int
    high_findings: int
    untriaged_findings: int
    overdue_findings: int
    test_scope_complete: bool
    remediation_retested: bool
    build_provenance_verified: bool


def evaluate_security_testing(e: SecurityTestingEvidence) -> StageAssessment:
    r: list[str] = []
    for f in ("build_attestation_ref", "sast_report_ref", "dast_report_ref",
              "dependency_scan_ref", "penetration_test_ref", "remediation_retest_ref",
              "independent_assessor_ref"):
        _required(getattr(e, f), f, r)
    _commit(e.source_commit, "source_commit", r)
    _digest(e.build_artifact_digest, "build_artifact_digest", r)
    _date(e.assessed_at_utc, "assessed_at_utc", r)
    for f in ("critical_findings", "high_findings", "untriaged_findings", "overdue_findings"):
        _count(getattr(e, f), f, r)
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{f} must be zero")
    for f in ("test_scope_complete", "remediation_retested", "build_provenance_verified"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return StageAssessment(62, "SECURITY_TESTING_HOLD", tuple(r))
    return StageAssessment(62, "SECURITY_TESTING_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("test execution, coverage, finding disposition and build provenance require independent verification",))


@dataclass(frozen=True)
class AssuranceDossierEvidence:
    source_commit: str
    evidence_stage_ids: tuple[int, ...]
    evidence_digests: tuple[str, ...]
    dossier_ref: str
    independent_assurance_ref: str
    blocker_register_ref: str
    prepared_at_utc: str
    unresolved_blockers: int
    evidence_scope_complete: bool
    provenance_chain_reviewed: bool


def evaluate_assurance_dossier(e: AssuranceDossierEvidence) -> StageAssessment:
    r: list[str] = []
    _commit(e.source_commit, "source_commit", r)
    for f in ("dossier_ref", "independent_assurance_ref", "blocker_register_ref"):
        _required(getattr(e, f), f, r)
    _date(e.prepared_at_utc, "prepared_at_utc", r)
    expected = tuple(range(56, 63))
    if e.evidence_stage_ids != expected:
        r.append("evidence_stage_ids must cover stages 56 through 62 in order")
    if not isinstance(e.evidence_digests, tuple) or len(e.evidence_digests) != 7:
        r.append("evidence_digests must contain seven stage evidence digests")
    else:
        for i, value in enumerate(e.evidence_digests):
            _digest(value, f"evidence_digests[{i}]", r)
    _count(e.unresolved_blockers, "unresolved_blockers", r)
    if isinstance(e.unresolved_blockers, int) and not isinstance(e.unresolved_blockers, bool) and e.unresolved_blockers:
        r.append("unresolved_blockers must be zero for dossier completeness")
    for f in ("evidence_scope_complete", "provenance_chain_reviewed"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return StageAssessment(63, "ASSURANCE_DOSSIER_HOLD", tuple(r))
    return StageAssessment(63, "ASSURANCE_DOSSIER_COMPLETE_UNVERIFIED",
                           ("dossier completeness is not release approval; all evidence and upstream blockers remain independently reviewable",))
