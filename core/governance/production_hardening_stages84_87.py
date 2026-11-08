"""Offline, reference-only evidence gates for QuantEngine Stages 84–87."""
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
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            reasons.append(f"{name} must be a non-negative integer")
    for name, value in flags:
        if value is not True:
            reasons.append(f"{name} must be explicitly attested true")
    return reasons

def _result(stage: int, prefix: str, reasons: list[str], note: str) -> Assessment:
    if reasons:
        return Assessment(stage, f"{prefix}_HOLD", tuple(reasons))
    return Assessment(stage, f"{prefix}_COMPLETE_UNVERIFIED", (note,))

@dataclass(frozen=True)
class StrategyGovernance:
    assessment_ref: str
    strategy_spec_ref: str
    strategy_hash: str
    approval_record_ref: str
    preregistration_ref: str
    research_boundary_ref: str
    change_register_ref: str
    assessed_at: str
    changes_in_scope: int
    changes_approved: int
    changes_with_reproducible_tests: int
    unresolved_strategy_identity_mismatches: int
    research_oos_separation_attested: bool
    independent_approval_attested: bool

def evaluate_strategy_governance(e: StrategyGovernance) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "strategy_spec_ref", "approval_record_ref",
        "preregistration_ref", "research_boundary_ref", "change_register_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "changes_in_scope", "changes_approved", "changes_with_reproducible_tests",
        "unresolved_strategy_identity_mismatches"))
    flags = (("research_oos_separation_attested", e.research_oos_separation_attested),
             ("independent_approval_attested", e.independent_approval_attested))
    r = _check(refs, counts, flags, e.assessed_at)
    if not isinstance(e.strategy_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", e.strategy_hash):
        r.append("strategy_hash must be a 64-character SHA-256 hex digest")
    if e.changes_approved != e.changes_in_scope:
        r.append("every in-scope strategy change must have approval evidence")
    if e.changes_with_reproducible_tests != e.changes_in_scope:
        r.append("every in-scope strategy change must have reproducible test evidence")
    if e.unresolved_strategy_identity_mismatches != 0:
        r.append("unresolved_strategy_identity_mismatches must be zero")
    return _result(84, "STRATEGY_GOVERNANCE", r,
        "strategy identity, preregistration and research/OOS boundaries remain independently unverified; no strategy is modified or executed")

@dataclass(frozen=True)
class MonitoringGovernance:
    assessment_ref: str
    control_catalog_ref: str
    threshold_register_ref: str
    routing_matrix_ref: str
    escalation_plan_ref: str
    dry_run_report_ref: str
    assessed_at: str
    controls_in_scope: int
    controls_with_thresholds: int
    controls_with_routes: int
    controls_with_escalation: int
    unowned_critical_alerts: int
    critical_coverage_gaps: int
    dry_run_completed: bool
    independent_review_attested: bool

def evaluate_monitoring_governance(e: MonitoringGovernance) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "control_catalog_ref", "threshold_register_ref",
        "routing_matrix_ref", "escalation_plan_ref", "dry_run_report_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "controls_in_scope", "controls_with_thresholds", "controls_with_routes",
        "controls_with_escalation", "unowned_critical_alerts", "critical_coverage_gaps"))
    flags = (("dry_run_completed", e.dry_run_completed),
             ("independent_review_attested", e.independent_review_attested))
    r = _check(refs, counts, flags, e.assessed_at)
    for name in ("controls_with_thresholds", "controls_with_routes", "controls_with_escalation"):
        if getattr(e, name) != e.controls_in_scope:
            r.append(f"{name} must cover every in-scope control")
    for name in ("unowned_critical_alerts", "critical_coverage_gaps"):
        if getattr(e, name) != 0:
            r.append(f"{name} must be zero")
    return _result(85, "MONITORING_GOVERNANCE", r,
        "catalog, thresholds, routes and dry-run evidence require independent verification; no production telemetry is read and no alert is fired")

@dataclass(frozen=True)
class FinancialReconciliation:
    assessment_ref: str
    ledger_snapshot_ref: str
    counterparty_statement_ref: str
    transaction_population_ref: str
    break_register_ref: str
    independent_review_ref: str
    assessed_at: str
    transactions_in_scope: int
    transactions_matched: int
    breaks_identified: int
    breaks_independently_resolved: int
    unresolved_value_breaks: int
    unexplained_balance_breaks: int
    independent_review_completed: bool

def evaluate_financial_reconciliation(e: FinancialReconciliation) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "ledger_snapshot_ref", "counterparty_statement_ref",
        "transaction_population_ref", "break_register_ref", "independent_review_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "transactions_in_scope", "transactions_matched", "breaks_identified",
        "breaks_independently_resolved", "unresolved_value_breaks", "unexplained_balance_breaks"))
    flags = (("independent_review_completed", e.independent_review_completed),)
    r = _check(refs, counts, flags, e.assessed_at)
    if e.transactions_matched != e.transactions_in_scope:
        r.append("every in-scope transaction must be matched to the referenced counterparty evidence")
    if e.breaks_independently_resolved != e.breaks_identified:
        r.append("every identified break must have independent resolution evidence")
    for name in ("unresolved_value_breaks", "unexplained_balance_breaks"):
        if getattr(e, name) != 0:
            r.append(f"{name} must be zero")
    return _result(86, "FINANCIAL_RECONCILIATION", r,
        "ledger and statement references require independent authenticity and completeness checks; no broker, bank or exchange system is queried")

@dataclass(frozen=True)
class ReleaseRollbackReadiness:
    assessment_ref: str
    artifact_ref: str
    source_commit: str
    manifest_ref: str
    test_evidence_ref: str
    release_approval_ref: str
    rollback_plan_ref: str
    tabletop_report_ref: str
    assessed_at: str
    release_blockers: int
    required_tests_passed: int
    required_tests_in_scope: int
    rollback_steps_in_scope: int
    rollback_steps_documented: int
    rollback_tabletop_completed: bool
    independent_release_review: bool

def evaluate_release_rollback_readiness(e: ReleaseRollbackReadiness) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "artifact_ref", "manifest_ref", "test_evidence_ref",
        "release_approval_ref", "rollback_plan_ref", "tabletop_report_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "release_blockers", "required_tests_passed", "required_tests_in_scope",
        "rollback_steps_in_scope", "rollback_steps_documented"))
    flags = (("rollback_tabletop_completed", e.rollback_tabletop_completed),
             ("independent_release_review", e.independent_release_review))
    r = _check(refs, counts, flags, e.assessed_at)
    if not isinstance(e.source_commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", e.source_commit):
        r.append("source_commit must be a 40-character Git commit SHA")
    if e.release_blockers != 0:
        r.append("release_blockers must be zero for an evidence-complete assessment")
    if e.required_tests_passed != e.required_tests_in_scope:
        r.append("all required tests must have passing evidence")
    if e.rollback_steps_documented != e.rollback_steps_in_scope:
        r.append("every rollback step must be documented and tabletop-reviewed")
    return _result(87, "RELEASE_ROLLBACK", r,
        "artifact, approvals and rollback tabletop evidence remain independently unverified; no deployment or rollback is performed")
