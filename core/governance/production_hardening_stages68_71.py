"""Offline evidence gates for provenance and audit reconciliation, Stages 68–71.

Validators consume operator-supplied evidence references and attestations only.
They do not inspect Git, secrets, exchanges, trading systems, or production telemetry.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import re

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_STAGE4_ANCESTOR = "b42e8181406091bf06af18e312508a93924dcc37"

@dataclass(frozen=True)
class Assessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False

def _ref(v: str, name: str, out: list[str]) -> None:
    if not isinstance(v, str) or not v.strip():
        out.append(f"{name} reference is required")

def _commit(v: str, name: str, out: list[str]) -> None:
    if not isinstance(v, str) or not _COMMIT.fullmatch(v):
        out.append(f"{name} must be a 40-character lowercase Git commit ID")

def _digest(v: str, name: str, out: list[str]) -> None:
    if not isinstance(v, str) or not _SHA256.fullmatch(v):
        out.append(f"{name} must be a lowercase SHA-256 digest")

def _time(v: str, name: str, out: list[str]) -> None:
    try:
        d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        if d.tzinfo is None or d.utcoffset() is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        out.append(f"{name} must be ISO-8601 with an explicit UTC offset")

def _nonnegative(v: int, name: str, out: list[str]) -> None:
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        out.append(f"{name} must be a non-negative integer")

@dataclass(frozen=True)
class AncestryReconciliation:
    source_commit: str
    required_ancestor_commit: str
    ancestry_report_ref: str
    independent_verification_ref: str
    assessed_at_utc: str
    required_ancestor_reachable: bool
    report_matches_source_commit: bool

def evaluate_ancestry_reconciliation(e: AncestryReconciliation) -> Assessment:
    r: list[str] = []
    _commit(e.source_commit, "source_commit", r)
    _commit(e.required_ancestor_commit, "required_ancestor_commit", r)
    if e.required_ancestor_commit != _REQUIRED_STAGE4_ANCESTOR:
        r.append("required_ancestor_commit must equal the immutable Stage 4 pinned commit")
    for n in ("ancestry_report_ref", "independent_verification_ref"):
        _ref(getattr(e, n), n, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    if e.required_ancestor_reachable is not True:
        r.append("required Stage 4 pinned ancestor must be reachable; assertion cannot be bypassed")
    if e.report_matches_source_commit is not True:
        r.append("ancestry report must be bound to source_commit")
    if r:
        return Assessment(68, "PINNED_ANCESTRY_HOLD", tuple(r))
    return Assessment(68, "PINNED_ANCESTRY_RECONCILED_UNVERIFIED",
                      ("ancestry evidence requires independent repository verification",))

@dataclass(frozen=True)
class FindingRemediation:
    source_commit: str
    findings_register_ref: str
    remediation_evidence_ref: str
    independent_closure_review_ref: str
    assessed_at_utc: str
    open_p0: int
    open_p1: int
    expired_actions: int
    findings_in_scope: int
    owners_assigned: bool
    evidence_redacted: bool
    closures_independently_verified: bool

def evaluate_finding_remediation(e: FindingRemediation) -> Assessment:
    r: list[str] = []
    _commit(e.source_commit, "source_commit", r)
    for n in ("findings_register_ref", "remediation_evidence_ref",
              "independent_closure_review_ref"):
        _ref(getattr(e, n), n, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    for n in ("open_p0", "open_p1", "expired_actions", "findings_in_scope"):
        _nonnegative(getattr(e, n), n, r)
    if e.findings_in_scope == 0:
        r.append("findings_in_scope must be non-zero for remediation reconciliation")
    for n in ("open_p0", "open_p1", "expired_actions"):
        v = getattr(e, n)
        if isinstance(v, int) and not isinstance(v, bool) and v != 0:
            r.append(f"{n} must be zero")
    for n in ("owners_assigned", "evidence_redacted", "closures_independently_verified"):
        if getattr(e, n) is not True:
            r.append(f"{n} must be explicitly attested true")
    if r:
        return Assessment(69, "FINDING_REMEDIATION_HOLD", tuple(r))
    return Assessment(69, "FINDING_REMEDIATION_COMPLETE_UNVERIFIED",
                      ("finding closure, ownership and evidence quality require independent confirmation",))

@dataclass(frozen=True)
class VenueEconomicsEvidence:
    source_commit: str
    dataset_manifest_digest: str
    preregistration_ref: str
    fee_schedule_ref: str
    slippage_model_ref: str
    latency_assumptions_ref: str
    venue_coverage_ref: str
    out_of_sample_report_ref: str
    independent_review_ref: str
    assessed_at_utc: str
    venues_in_scope: int
    venues_tested: int
    oos_observations: int
    missing_cost_components: int
    assumptions_reconciled: bool
    no_lookahead_attested: bool

def evaluate_venue_economics(e: VenueEconomicsEvidence) -> Assessment:
    r: list[str] = []
    _commit(e.source_commit, "source_commit", r)
    _digest(e.dataset_manifest_digest, "dataset_manifest_digest", r)
    for n in ("preregistration_ref", "fee_schedule_ref", "slippage_model_ref",
              "latency_assumptions_ref", "venue_coverage_ref",
              "out_of_sample_report_ref", "independent_review_ref"):
        _ref(getattr(e, n), n, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    for n in ("venues_in_scope", "venues_tested", "oos_observations", "missing_cost_components"):
        _nonnegative(getattr(e, n), n, r)
    if e.venues_in_scope == 0 or e.venues_tested != e.venues_in_scope:
        r.append("all non-empty in-scope venues must be tested")
    if e.oos_observations == 0:
        r.append("oos_observations must be greater than zero")
    if e.missing_cost_components != 0:
        r.append("missing_cost_components must be zero")
    for n in ("assumptions_reconciled", "no_lookahead_attested"):
        if getattr(e, n) is not True:
            r.append(f"{n} must be explicitly attested true")
    if r:
        return Assessment(70, "VENUE_ECONOMICS_HOLD", tuple(r))
    return Assessment(70, "VENUE_ECONOMICS_COMPLETE_UNVERIFIED",
                      ("fee, slippage, latency and venue assumptions require independent validation; no profitability claim is implied",))

@dataclass(frozen=True)
class TestEvidenceProvenance:
    source_commit: str
    workflow_run_ref: str
    exact_command_ref: str
    environment_digest: str
    results_artifact_ref: str
    independent_review_ref: str
    assessed_at_utc: str
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    tests_collected: int
    result_commit_matches_source: bool
    workflow_conclusion_success: bool

def evaluate_test_evidence(e: TestEvidenceProvenance) -> Assessment:
    r: list[str] = []
    _commit(e.source_commit, "source_commit", r)
    _digest(e.environment_digest, "environment_digest", r)
    for n in ("workflow_run_ref", "exact_command_ref", "results_artifact_ref",
              "independent_review_ref"):
        _ref(getattr(e, n), n, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    for n in ("tests_passed", "tests_failed", "tests_skipped", "tests_collected"):
        _nonnegative(getattr(e, n), n, r)
    if e.tests_collected == 0 or e.tests_passed + e.tests_failed + e.tests_skipped != e.tests_collected:
        r.append("test result counts must reconcile to a non-zero collected total")
    if e.tests_failed != 0:
        r.append("tests_failed must be zero")
    if e.tests_skipped != 0:
        r.append("tests_skipped must be zero for this evidence gate")
    for n in ("result_commit_matches_source", "workflow_conclusion_success"):
        if getattr(e, n) is not True:
            r.append(f"{n} must be explicitly attested true")
    if r:
        return Assessment(71, "TEST_EVIDENCE_HOLD", tuple(r))
    return Assessment(71, "TEST_EVIDENCE_COMPLETE_UNVERIFIED",
                      ("test provenance is structurally complete but does not substitute for full repository regression or independent execution",))
