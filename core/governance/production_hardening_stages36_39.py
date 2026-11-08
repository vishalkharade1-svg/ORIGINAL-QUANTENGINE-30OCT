"""Offline evidence gates for production-hardening Stages 36–39.

Validators inspect operator-supplied records only. They do not calculate live
portfolio state, reconcile with a venue, mutate orders, deploy, or arm trading.
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


def _nonnegative(value: int, name: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append(f"{name} must be a non-negative integer")


def _finite(value: float, name: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        reasons.append(f"{name} must be a finite number")


def _utc(value: str, name: str, reasons: list[str]) -> datetime | None:
    try:
        if not isinstance(value, str) or not value.strip():
            raise ValueError
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        reasons.append(f"{name} must be an ISO-8601 timestamp with UTC offset")
        return None


@dataclass(frozen=True)
class PortfolioRiskEvidence:
    portfolio_id: str
    as_of_utc: str
    source_commit: str
    positions_snapshot_digest: str
    risk_model_ref: str
    stress_suite_ref: str
    independent_risk_review_ref: str
    gross_exposure: float
    net_exposure: float
    equity: float
    gross_exposure_limit: float
    net_exposure_limit: float
    leverage: float
    leverage_limit: float
    largest_single_name_percent: float
    single_name_limit_percent: float
    concentration_hhi: float
    concentration_hhi_limit: float
    stress_loss_percent: float
    stress_loss_limit_percent: float
    margin_buffer_percent: float
    minimum_margin_buffer_percent: float
    unhedged_position_count: int
    unresolved_limit_breaches: int


def evaluate_portfolio_risk(e: PortfolioRiskEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("portfolio_id", "risk_model_ref", "stress_suite_ref",
                 "independent_risk_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    _digest(e.positions_snapshot_digest, "positions_snapshot_digest", reasons)
    _utc(e.as_of_utc, "as_of_utc", reasons)
    metrics = ("gross_exposure", "net_exposure", "equity", "gross_exposure_limit",
               "net_exposure_limit", "leverage", "leverage_limit",
               "largest_single_name_percent", "single_name_limit_percent",
               "concentration_hhi", "concentration_hhi_limit",
               "stress_loss_percent", "stress_loss_limit_percent",
               "margin_buffer_percent", "minimum_margin_buffer_percent")
    for name in metrics:
        _finite(getattr(e, name), name, reasons)
    if isinstance(e.equity, (int, float)) and not isinstance(e.equity, bool) and e.equity <= 0:
        reasons.append("equity must be positive")
    checks = (
        ("gross_exposure", "gross_exposure_limit"),
        ("net_exposure", "net_exposure_limit"),
        ("leverage", "leverage_limit"),
        ("largest_single_name_percent", "single_name_limit_percent"),
        ("concentration_hhi", "concentration_hhi_limit"),
        ("stress_loss_percent", "stress_loss_limit_percent"),
    )
    for actual, limit in checks:
        a, b = getattr(e, actual), getattr(e, limit)
        if (isinstance(a, (int, float)) and not isinstance(a, bool) and math.isfinite(a)
                and isinstance(b, (int, float)) and not isinstance(b, bool)
                and math.isfinite(b) and a > b):
            reasons.append(f"{actual} exceeds {limit}")
    if (isinstance(e.margin_buffer_percent, (int, float))
            and isinstance(e.minimum_margin_buffer_percent, (int, float))
            and e.margin_buffer_percent < e.minimum_margin_buffer_percent):
        reasons.append("margin buffer is below the required minimum")
    _nonnegative(e.unhedged_position_count, "unhedged_position_count", reasons)
    _nonnegative(e.unresolved_limit_breaches, "unresolved_limit_breaches", reasons)
    if isinstance(e.unhedged_position_count, int) and e.unhedged_position_count:
        reasons.append("unhedged positions remain unresolved")
    if isinstance(e.unresolved_limit_breaches, int) and e.unresolved_limit_breaches:
        reasons.append("portfolio risk-limit breaches remain unresolved")
    if reasons:
        return StageAssessment(36, "PORTFOLIO_RISK_HOLD", tuple(reasons))
    return StageAssessment(36, "PORTFOLIO_RISK_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("position snapshots, model assumptions, and stress outputs require independent recomputation",))


@dataclass(frozen=True)
class LedgerReconciliationEvidence:
    account_ref: str
    venue_ref: str
    source_commit: str
    internal_ledger_digest: str
    external_statement_digest: str
    positions_snapshot_digest: str
    reconciliation_report_ref: str
    independent_finance_review_ref: str
    period_start_utc: str
    period_end_utc: str
    reconciled_at_utc: str
    internal_cash: float
    external_cash: float
    internal_position_value: float
    external_position_value: float
    allowed_cash_delta: float
    allowed_position_delta: float
    duplicate_ledger_event_count: int
    missing_external_event_count: int
    orphan_internal_event_count: int
    unresolved_fee_count: int
    sequence_gap_count: int
    watermark_monotonic: bool


def evaluate_ledger_reconciliation(e: LedgerReconciliationEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("account_ref", "venue_ref", "reconciliation_report_ref",
                 "independent_finance_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    for name in ("internal_ledger_digest", "external_statement_digest",
                 "positions_snapshot_digest"):
        _digest(getattr(e, name), name, reasons)
    start = _utc(e.period_start_utc, "period_start_utc", reasons)
    end = _utc(e.period_end_utc, "period_end_utc", reasons)
    reconciled = _utc(e.reconciled_at_utc, "reconciled_at_utc", reasons)
    if start and end and end <= start:
        reasons.append("reconciliation period must have positive duration")
    if end and reconciled and reconciled < end:
        reasons.append("reconciliation timestamp predates period end")
    numeric = ("internal_cash", "external_cash", "internal_position_value",
               "external_position_value", "allowed_cash_delta", "allowed_position_delta")
    for name in numeric:
        _finite(getattr(e, name), name, reasons)
    for left, right, limit, label in (
        ("internal_cash", "external_cash", "allowed_cash_delta", "cash"),
        ("internal_position_value", "external_position_value", "allowed_position_delta", "position value"),
    ):
        a, b, tol = getattr(e, left), getattr(e, right), getattr(e, limit)
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (a, b, tol)) and tol >= 0 and abs(a - b) > tol:
            reasons.append(f"{label} reconciliation delta exceeds tolerance")
    counts = ("duplicate_ledger_event_count", "missing_external_event_count",
              "orphan_internal_event_count", "unresolved_fee_count", "sequence_gap_count")
    for name in counts:
        _nonnegative(getattr(e, name), name, reasons)
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    if e.watermark_monotonic is not True:
        reasons.append("ledger watermark is not attested monotonic")
    if reasons:
        return StageAssessment(37, "LEDGER_RECONCILIATION_HOLD", tuple(reasons))
    return StageAssessment(37, "LEDGER_RECONCILIATION_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("ledger events, statements, and reconciliation arithmetic require independent verification",))


@dataclass(frozen=True)
class ChangeIncidentEvidence:
    service: str
    source_commit: str
    change_ticket_ref: str
    impact_assessment_ref: str
    test_report_ref: str
    rollback_plan_ref: str
    rollback_artifact_digest: str
    incident_register_ref: str
    independent_change_review_ref: str
    operational_owner_approval_ref: str
    change_window_start_utc: str
    change_window_end_utc: str
    tested_in_paper_environment: bool
    rollback_rehearsed: bool
    monitoring_and_alerts_verified: bool
    operator_runbook_updated: bool
    unresolved_critical_incidents: int
    unapproved_changes: int
    emergency_change_count: int
    emergency_changes_reviewed: bool


def evaluate_change_incident_control(e: ChangeIncidentEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("service", "change_ticket_ref", "impact_assessment_ref",
                 "test_report_ref", "rollback_plan_ref", "incident_register_ref",
                 "independent_change_review_ref", "operational_owner_approval_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    _digest(e.rollback_artifact_digest, "rollback_artifact_digest", reasons)
    start = _utc(e.change_window_start_utc, "change_window_start_utc", reasons)
    end = _utc(e.change_window_end_utc, "change_window_end_utc", reasons)
    if start and end and end <= start:
        reasons.append("change window must have positive duration")
    for name in ("tested_in_paper_environment", "rollback_rehearsed",
                 "monitoring_and_alerts_verified", "operator_runbook_updated",
                 "emergency_changes_reviewed"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    for name in ("unresolved_critical_incidents", "unapproved_changes", "emergency_change_count"):
        _nonnegative(getattr(e, name), name, reasons)
    for name in ("unresolved_critical_incidents", "unapproved_changes"):
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    if isinstance(e.emergency_change_count, int) and not isinstance(e.emergency_change_count, bool):
        if e.emergency_change_count and e.emergency_changes_reviewed is not True:
            reasons.append("all emergency changes require retrospective review")
    if reasons:
        return StageAssessment(38, "CHANGE_INCIDENT_CONTROL_HOLD", tuple(reasons))
    return StageAssessment(38, "CHANGE_INCIDENT_CONTROL_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("approvals, paper-environment test evidence, and rollback rehearsal require independent confirmation",))


@dataclass(frozen=True)
class GovernanceReadinessEvidence:
    stage32_status: str
    stage33_status: str
    stage34_status: str
    stage35_status: str
    stage36_status: str
    stage37_status: str
    stage38_status: str
    stage4_lineage_verified: bool
    credentials_revoked_and_reviewed: bool
    full_repository_regression_passed: bool
    independent_oos_review_complete: bool
    independent_venue_economics_review_complete: bool
    risk_reward_policy_reconciled: bool
    critical_findings_open: int
    candidate_digest: str
    independent_governance_review_ref: str
    paper_operator_approval_ref: str


def evaluate_governance_readiness(e: GovernanceReadinessEvidence) -> StageAssessment:
    reasons: list[str] = []
    expected = (
        ("stage32", e.stage32_status, "STRATEGY_PROVENANCE_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage33", e.stage33_status, "BACKTEST_VALIDITY_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage34", e.stage34_status, "EXECUTION_CAPACITY_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage35", e.stage35_status, "RUNTIME_CONTAINMENT_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage36", e.stage36_status, "PORTFOLIO_RISK_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage37", e.stage37_status, "LEDGER_RECONCILIATION_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage38", e.stage38_status, "CHANGE_INCIDENT_CONTROL_EVIDENCE_COMPLETE_UNVERIFIED"),
    )
    for label, actual, required in expected:
        if actual != required:
            reasons.append(f"{label} prerequisite is not satisfied")
    blockers = (
        ("stage4_lineage_verified", e.stage4_lineage_verified),
        ("credentials_revoked_and_reviewed", e.credentials_revoked_and_reviewed),
        ("full_repository_regression_passed", e.full_repository_regression_passed),
        ("independent_oos_review_complete", e.independent_oos_review_complete),
        ("independent_venue_economics_review_complete", e.independent_venue_economics_review_complete),
        ("risk_reward_policy_reconciled", e.risk_reward_policy_reconciled),
    )
    for name, value in blockers:
        if value is not True:
            reasons.append(f"{name} remains an unresolved release blocker")
    _nonnegative(e.critical_findings_open, "critical_findings_open", reasons)
    if isinstance(e.critical_findings_open, int) and not isinstance(e.critical_findings_open, bool) and e.critical_findings_open:
        reasons.append("critical findings remain open")
    _digest(e.candidate_digest, "candidate_digest", reasons)
    _required(e.independent_governance_review_ref, "independent_governance_review_ref", reasons)
    _required(e.paper_operator_approval_ref, "paper_operator_approval_ref", reasons)
    if reasons:
        return StageAssessment(39, "GOVERNANCE_READINESS_HOLD", tuple(reasons))
    return StageAssessment(39, "PAPER_OPERATIONAL_REVIEW_HANDOFF_ONLY",
                           ("paper operational review only; no deployment, exchange access, Testnet, or LIVE authorization",))
