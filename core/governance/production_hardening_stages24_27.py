"""Offline evidence gates for production-hardening Stages 24–27.

Evidence is operator-supplied and structurally checked only. No secrets,
credentials, Git history, exchange endpoints, or live execution are accessed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_AUDIT_DOMAINS = frozenset({
    "indicators", "order_flow", "wyckoff_smc", "options",
    "backtest_bias", "paper_realism", "concurrency_async",
    "performance", "reconciliation", "protective_orders",
    "exception_handling", "execution_bypass", "stub_triage",
    "dependency_drift",
})


@dataclass(frozen=True)
class Assessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def _ref(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{name} is required")


def _digest(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        reasons.append(f"{name} must be lowercase SHA-256")


@dataclass(frozen=True)
class CredentialClosureEvidence:
    provider_revocation_confirmed: bool
    provider_case_ref: str
    revocation_effective_at_utc: str
    replacement_key_testnet_only: bool
    least_privilege_review_ref: str
    secret_scan_ref: str
    history_exposure_decision: str
    history_remediation_ref: str
    independent_security_review_ref: str


def evaluate_credential_closure(e: CredentialClosureEvidence) -> Assessment:
    reasons: list[str] = []
    if e.provider_revocation_confirmed is not True:
        reasons.append("provider-side revocation is not confirmed")
    for field in ("provider_case_ref", "revocation_effective_at_utc",
                  "least_privilege_review_ref", "secret_scan_ref",
                  "history_remediation_ref", "independent_security_review_ref"):
        _ref(getattr(e, field), field, reasons)
    if e.replacement_key_testnet_only is not True:
        reasons.append("replacement credential is not attested Testnet-only")
    if e.history_exposure_decision not in {"PURGED_AND_VERIFIED", "EXPOSURE_ACCEPTED_BY_OWNER"}:
        reasons.append("history exposure disposition is unresolved")
    if reasons:
        return Assessment(24, "SECURITY_HOLD", tuple(reasons))
    return Assessment(24, "CREDENTIAL_CLOSURE_EVIDENCE_COMPLETE_UNVERIFIED",
                      ("provider and history evidence references require independent authentication",))


@dataclass(frozen=True)
class RepositoryIntegrityEvidence:
    source_commit: str
    clean_tree_attested: bool
    uncommitted_path_count: int
    index_lock_present: bool
    canonical_ancestor_verified: bool
    canonical_ancestor_commit: str
    line_ending_policy_ref: str
    lf_fingerprint: str
    crlf_fingerprint: str
    fingerprint_reproducible: bool
    independent_repo_review_ref: str


def evaluate_repository_integrity(e: RepositoryIntegrityEvidence) -> Assessment:
    reasons: list[str] = []
    _digest(e.source_commit, "source_commit", reasons)
    _digest(e.canonical_ancestor_commit, "canonical_ancestor_commit", reasons)
    for field in ("lf_fingerprint", "crlf_fingerprint"):
        _digest(getattr(e, field), field, reasons)
    for field in ("line_ending_policy_ref", "independent_repo_review_ref"):
        _ref(getattr(e, field), field, reasons)
    if e.clean_tree_attested is not True or e.uncommitted_path_count != 0:
        reasons.append("repository is not independently attested clean")
    if isinstance(e.uncommitted_path_count, bool) or not isinstance(e.uncommitted_path_count, int) or e.uncommitted_path_count < 0:
        reasons.append("uncommitted_path_count must be a non-negative integer")
    if e.index_lock_present is not False:
        reasons.append("stale Git index lock is present or unverified")
    if e.canonical_ancestor_verified is not True:
        reasons.append("canonical source ancestry is not verified")
    if e.fingerprint_reproducible is not True or e.lf_fingerprint != e.crlf_fingerprint:
        reasons.append("strategy fingerprint is not reproducible across declared line endings")
    if reasons:
        return Assessment(25, "REPOSITORY_INTEGRITY_HOLD", tuple(reasons))
    return Assessment(25, "REPOSITORY_INTEGRITY_EVIDENCE_COMPLETE_UNVERIFIED",
                      ("Git ancestry and fingerprints are operator-attested, not independently fetched or recomputed",))


@dataclass(frozen=True)
class Classification:
    path: str
    disposition: str
    evidence_ref: str


@dataclass(frozen=True)
class GovernanceInventoryEvidence:
    canonical_dependency_manifest: str
    dependency_manifest_digest: str
    compared_manifest_digests: tuple[str, ...]
    dependency_comparison_ref: str
    dependency_drift_resolved: bool
    classifications: tuple[Classification, ...]
    required_classification_paths: tuple[str, ...]
    independent_review_ref: str


def evaluate_governance_inventory(e: GovernanceInventoryEvidence) -> Assessment:
    reasons: list[str] = []
    _ref(e.canonical_dependency_manifest, "canonical_dependency_manifest", reasons)
    _digest(e.dependency_manifest_digest, "dependency_manifest_digest", reasons)
    _ref(e.dependency_comparison_ref, "dependency_comparison_ref", reasons)
    _ref(e.independent_review_ref, "independent_review_ref", reasons)
    if not e.compared_manifest_digests:
        reasons.append("compared_manifest_digests must not be empty")
    for digest in e.compared_manifest_digests:
        _digest(digest, "compared_manifest_digests entry", reasons)
    if e.dependency_drift_resolved is not True:
        reasons.append("dependency manifest drift is unresolved")
    seen: set[str] = set()
    allowed = {"ACTIVE", "TEST_ONLY", "DEAD_PLACEHOLDER"}
    for item in e.classifications:
        if not item.path or item.path in seen:
            reasons.append("classification paths must be non-empty and unique")
        seen.add(item.path)
        if item.disposition not in allowed:
            reasons.append(f"{item.path}: invalid or unresolved disposition")
        _ref(item.evidence_ref, f"{item.path}.evidence_ref", reasons)
    missing = sorted(set(e.required_classification_paths) - seen)
    if missing:
        reasons.append("unclassified paths: " + ", ".join(missing))
    if reasons:
        return Assessment(26, "GOVERNANCE_INVENTORY_HOLD", tuple(reasons))
    return Assessment(26, "GOVERNANCE_INVENTORY_COMPLETE_UNVERIFIED",
                      ("manifest comparisons and file classifications require independent review",))


@dataclass(frozen=True)
class AuditFinding:
    domain: str
    disposition: str
    evidence_ref: str


@dataclass(frozen=True)
class AuditCoverageEvidence:
    findings: tuple[AuditFinding, ...]
    independent_audit_review_ref: str
    scope_commit: str


def evaluate_audit_coverage(e: AuditCoverageEvidence) -> Assessment:
    reasons: list[str] = []
    _ref(e.independent_audit_review_ref, "independent_audit_review_ref", reasons)
    _digest(e.scope_commit, "scope_commit", reasons)
    seen: set[str] = set()
    allowed = {"VERIFIED_PASS", "VERIFIED_DEFECT", "NOT_APPLICABLE_WITH_RATIONALE"}
    for finding in e.findings:
        if finding.domain not in _AUDIT_DOMAINS:
            reasons.append(f"unknown audit domain: {finding.domain}")
        if finding.domain in seen:
            reasons.append(f"duplicate audit domain: {finding.domain}")
        seen.add(finding.domain)
        if finding.disposition not in allowed:
            reasons.append(f"{finding.domain}: UNKNOWN or unsupported disposition")
        _ref(finding.evidence_ref, f"{finding.domain}.evidence_ref", reasons)
    missing = sorted(_AUDIT_DOMAINS - seen)
    if missing:
        reasons.append("audit domains still uncovered: " + ", ".join(missing))
    if reasons:
        return Assessment(27, "AUDIT_COVERAGE_HOLD", tuple(reasons))
    return Assessment(27, "AUDIT_COVERAGE_COMPLETE_UNVERIFIED",
                      ("all declared domains have evidence references; references and conclusions are not authenticated",))
