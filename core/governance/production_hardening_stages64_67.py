"""Offline evidence gates for audit-driven production-hardening Stages 64–67.

These validators inspect references and attestations only. They never access,
print, rotate, revoke, or otherwise handle credentials or live trading systems.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Assessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def _ref(value: str, field: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{field} reference is required")


def _digest(value: str, field: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        reasons.append(f"{field} must be a lowercase SHA-256 digest")


def _commit(value: str, field: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _COMMIT.fullmatch(value):
        reasons.append(f"{field} must be a 40-character Git commit ID")


def _count(value: int, field: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append(f"{field} must be a non-negative integer")


def _time(value: str, field: str, reasons: list[str]) -> None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        reasons.append(f"{field} must be ISO-8601 with an explicit UTC offset")


@dataclass(frozen=True)
class CredentialExposureClosure:
    source_commit: str
    exposure_register_ref: str
    provider_revocation_evidence_ref: str
    history_remediation_evidence_ref: str
    independent_verification_ref: str
    assessed_at_utc: str
    known_exposures: int
    unresolved_exposures: int
    provider_revocation_confirmed: bool
    history_remediation_confirmed: bool
    evidence_contains_no_secret_values: bool


def evaluate_credential_exposure(e: CredentialExposureClosure) -> Assessment:
    r: list[str] = []
    _commit(e.source_commit, "source_commit", r)
    for f in ("exposure_register_ref", "provider_revocation_evidence_ref",
              "history_remediation_evidence_ref", "independent_verification_ref"):
        _ref(getattr(e, f), f, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    _count(e.known_exposures, "known_exposures", r)
    _count(e.unresolved_exposures, "unresolved_exposures", r)
    if isinstance(e.known_exposures, int) and not isinstance(e.known_exposures, bool) and e.known_exposures == 0:
        r.append("known_exposures must be non-zero when closing a recorded exposure")
    if isinstance(e.unresolved_exposures, int) and not isinstance(e.unresolved_exposures, bool) and e.unresolved_exposures:
        r.append("unresolved_exposures must be zero")
    for f in ("provider_revocation_confirmed", "history_remediation_confirmed",
              "evidence_contains_no_secret_values"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return Assessment(64, "CREDENTIAL_EXPOSURE_HOLD", tuple(r))
    return Assessment(64, "CREDENTIAL_EXPOSURE_CLOSED_UNVERIFIED",
                      ("provider-side revocation and repository-history remediation require independent confirmation",))


@dataclass(frozen=True)
class RepositorySnapshotIntegrity:
    source_commit: str
    tree_digest: str
    status_report_ref: str
    lockfile_disposition_ref: str
    clean_checkout_attestation_ref: str
    independent_review_ref: str
    assessed_at_utc: str
    uncommitted_paths: int
    unresolved_index_locks: int
    checkout_reproducible: bool
    manifest_verified: bool


def evaluate_repository_snapshot(e: RepositorySnapshotIntegrity) -> Assessment:
    r: list[str] = []
    _commit(e.source_commit, "source_commit", r)
    _digest(e.tree_digest, "tree_digest", r)
    for f in ("status_report_ref", "lockfile_disposition_ref",
              "clean_checkout_attestation_ref", "independent_review_ref"):
        _ref(getattr(e, f), f, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    for f in ("uncommitted_paths", "unresolved_index_locks"):
        _count(getattr(e, f), f, r)
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{f} must be zero")
    for f in ("checkout_reproducible", "manifest_verified"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return Assessment(65, "REPOSITORY_SNAPSHOT_HOLD", tuple(r))
    return Assessment(65, "REPOSITORY_SNAPSHOT_COMPLETE_UNVERIFIED",
                      ("cleanliness, tree identity and independent checkout reproducibility require confirmation",))


@dataclass(frozen=True)
class StrategyRecertification:
    source_commit: str
    prior_strategy_pin: str
    replacement_strategy_digest: str
    canonicalization_spec_ref: str
    independent_reproduction_ref: str
    preregistration_ref: str
    dataset_manifest_digest: str
    out_of_sample_report_ref: str
    independent_reviewer_ref: str
    assessed_at_utc: str
    oos_observations: int
    leakage_findings: int
    hash_reproduced: bool
    dataset_lineage_verified: bool
    no_lookahead_attested: bool
    oos_protocol_followed: bool


def evaluate_strategy_recertification(e: StrategyRecertification) -> Assessment:
    r: list[str] = []
    _commit(e.source_commit, "source_commit", r)
    _digest(e.prior_strategy_pin, "prior_strategy_pin", r)
    _digest(e.replacement_strategy_digest, "replacement_strategy_digest", r)
    _digest(e.dataset_manifest_digest, "dataset_manifest_digest", r)
    for f in ("canonicalization_spec_ref", "independent_reproduction_ref",
              "preregistration_ref", "out_of_sample_report_ref", "independent_reviewer_ref"):
        _ref(getattr(e, f), f, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    _count(e.oos_observations, "oos_observations", r)
    _count(e.leakage_findings, "leakage_findings", r)
    if isinstance(e.oos_observations, int) and not isinstance(e.oos_observations, bool) and e.oos_observations == 0:
        r.append("oos_observations must be greater than zero")
    if isinstance(e.leakage_findings, int) and not isinstance(e.leakage_findings, bool) and e.leakage_findings:
        r.append("leakage_findings must be zero")
    for f in ("hash_reproduced", "dataset_lineage_verified", "no_lookahead_attested", "oos_protocol_followed"):
        if getattr(e, f) is not True:
            r.append(f"{f} must be explicitly attested true")
    if r:
        return Assessment(66, "STRATEGY_RECERTIFICATION_HOLD", tuple(r))
    return Assessment(66, "STRATEGY_RECERTIFICATION_COMPLETE_UNVERIFIED",
                      ("hash reproducibility and out-of-sample validity do not establish a profitable edge or authorize promotion",))


@dataclass(frozen=True)
class AuditCoverage:
    source_commit: str
    scope_register_ref: str
    findings_register_ref: str
    evidence_basis_register_ref: str
    independent_review_ref: str
    assessed_at_utc: str
    controls_in_scope: int
    controls_audited: int
    unknown_controls: int
    unresolved_p0_findings: int
    unresolved_p1_findings: int
    coverage_reconciled: bool


def evaluate_audit_coverage(e: AuditCoverage) -> Assessment:
    r: list[str] = []
    _commit(e.source_commit, "source_commit", r)
    for f in ("scope_register_ref", "findings_register_ref",
              "evidence_basis_register_ref", "independent_review_ref"):
        _ref(getattr(e, f), f, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    for f in ("controls_in_scope", "controls_audited", "unknown_controls",
              "unresolved_p0_findings", "unresolved_p1_findings"):
        _count(getattr(e, f), f, r)
    valid_counts = all(isinstance(getattr(e, f), int) and not isinstance(getattr(e, f), bool)
                       and getattr(e, f) >= 0 for f in
                       ("controls_in_scope", "controls_audited", "unknown_controls"))
    if valid_counts:
        if e.controls_in_scope == 0 or e.controls_audited != e.controls_in_scope:
            r.append("all non-empty in-scope controls must be audited")
        if e.unknown_controls != 0:
            r.append("unknown_controls must be zero")
    for f in ("unresolved_p0_findings", "unresolved_p1_findings"):
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v:
            r.append(f"{f} must be zero")
    if e.coverage_reconciled is not True:
        r.append("coverage_reconciled must be explicitly attested true")
    if r:
        return Assessment(67, "AUDIT_COVERAGE_HOLD", tuple(r))
    return Assessment(67, "AUDIT_COVERAGE_COMPLETE_UNVERIFIED",
                      ("scope completeness and finding closure require independent validation; this is not a release approval",))
