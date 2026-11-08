"""Offline evidence gates for production-hardening Stages 28–31.

Operator evidence is structurally checked only. No market-data provider,
broker, deployment system, secrets store, or live execution endpoint is called.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _ref(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{name} is required")


def _digest(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        reasons.append(f"{name} must be lowercase SHA-256")


def _utc(value: str, name: str, reasons: list[str]) -> datetime | None:
    try:
        if not isinstance(value, str) or not value.strip():
            raise ValueError
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        reasons.append(f"{name} must be an ISO-8601 timestamp with UTC offset")
        return None


@dataclass(frozen=True)
class StageAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


@dataclass(frozen=True)
class MarketDataIntegrityEvidence:
    provider: str
    instrument: str
    timeframe: str
    source_commit: str
    raw_capture_ref: str
    normalized_capture_ref: str
    raw_digest: str
    normalized_digest: str
    event_time_start_utc: str
    event_time_end_utc: str
    received_at_utc: str
    max_observed_lag_seconds: int
    allowed_lag_seconds: int
    duplicate_count: int
    gap_count: int
    correction_policy_ref: str
    independent_data_review_ref: str


def evaluate_market_data_integrity(e: MarketDataIntegrityEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("provider", "instrument", "timeframe", "raw_capture_ref",
                 "normalized_capture_ref", "correction_policy_ref",
                 "independent_data_review_ref"):
        _ref(getattr(e, name), name, reasons)
    if not isinstance(e.source_commit, str) or not _GIT_SHA.fullmatch(e.source_commit):
        reasons.append("source_commit must be a 40-character Git commit ID")
    for name in ("raw_digest", "normalized_digest"):
        _digest(getattr(e, name), name, reasons)
    start = _utc(e.event_time_start_utc, "event_time_start_utc", reasons)
    end = _utc(e.event_time_end_utc, "event_time_end_utc", reasons)
    received = _utc(e.received_at_utc, "received_at_utc", reasons)
    if start and end and end < start:
        reasons.append("event-time window is reversed")
    if end and received and received < end:
        reasons.append("receipt timestamp predates final event timestamp")
    for name in ("max_observed_lag_seconds", "allowed_lag_seconds",
                 "duplicate_count", "gap_count"):
        value = getattr(e, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            reasons.append(f"{name} must be a non-negative integer")
    if (isinstance(e.max_observed_lag_seconds, int) and
            isinstance(e.allowed_lag_seconds, int) and
            e.max_observed_lag_seconds > e.allowed_lag_seconds):
        reasons.append("observed market-data lag exceeds the declared limit")
    if isinstance(e.duplicate_count, int) and e.duplicate_count:
        reasons.append("duplicate market-data events remain unresolved")
    if isinstance(e.gap_count, int) and e.gap_count:
        reasons.append("market-data gaps remain unresolved")
    if reasons:
        return StageAssessment(28, "MARKET_DATA_HOLD", tuple(reasons))
    return StageAssessment(28, "MARKET_DATA_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("capture digests, provider records, and gap/correction claims require independent verification",))


@dataclass(frozen=True)
class OrderLifecycleEvidence:
    venue: str
    instrument: str
    source_commit: str
    scenario_matrix_ref: str
    submit_ack_ref: str
    partial_fill_ref: str
    cancel_ack_ref: str
    reject_ref: str
    timeout_recovery_ref: str
    reconciliation_ref: str
    client_order_id_unique: bool
    duplicate_submission_count: int
    orphan_order_count: int
    unprotected_exposure_count: int
    position_delta_reconciled: bool
    independent_execution_review_ref: str


def evaluate_order_lifecycle(e: OrderLifecycleEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("venue", "instrument", "scenario_matrix_ref", "submit_ack_ref",
                 "partial_fill_ref", "cancel_ack_ref", "reject_ref",
                 "timeout_recovery_ref", "reconciliation_ref",
                 "independent_execution_review_ref"):
        _ref(getattr(e, name), name, reasons)
    if not isinstance(e.source_commit, str) or not _GIT_SHA.fullmatch(e.source_commit):
        reasons.append("source_commit must be a 40-character Git commit ID")
    if e.client_order_id_unique is not True:
        reasons.append("client order IDs are not attested unique")
    for name in ("duplicate_submission_count", "orphan_order_count",
                 "unprotected_exposure_count"):
        value = getattr(e, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            reasons.append(f"{name} must be a non-negative integer")
        elif value:
            reasons.append(f"{name} must be zero")
    if e.position_delta_reconciled is not True:
        reasons.append("position delta is not reconciled")
    if reasons:
        return StageAssessment(29, "ORDER_LIFECYCLE_HOLD", tuple(reasons))
    return StageAssessment(29, "ORDER_LIFECYCLE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("venue acknowledgements and reconciliation evidence are not independently authenticated",))


@dataclass(frozen=True)
class ObservabilityEvidence:
    service: str
    source_commit: str
    dashboard_ref: str
    alert_rules_ref: str
    paging_drill_ref: str
    log_retention_policy_ref: str
    metric_retention_policy_ref: str
    evaluated_at_utc: str
    window_start_utc: str
    window_end_utc: str
    availability_percent: float
    availability_target_percent: float
    alert_delivery_success_percent: float
    alert_delivery_target_percent: float
    missing_critical_metrics: tuple[str, ...]
    unresolved_critical_alerts: int
    independent_operations_review_ref: str


def evaluate_observability(e: ObservabilityEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("service", "dashboard_ref", "alert_rules_ref", "paging_drill_ref",
                 "log_retention_policy_ref", "metric_retention_policy_ref",
                 "independent_operations_review_ref"):
        _ref(getattr(e, name), name, reasons)
    if not isinstance(e.source_commit, str) or not _GIT_SHA.fullmatch(e.source_commit):
        reasons.append("source_commit must be a 40-character Git commit ID")
    evaluated = _utc(e.evaluated_at_utc, "evaluated_at_utc", reasons)
    start = _utc(e.window_start_utc, "window_start_utc", reasons)
    end = _utc(e.window_end_utc, "window_end_utc", reasons)
    if start and end and end <= start:
        reasons.append("observability window must have positive duration")
    if evaluated and end and evaluated < end:
        reasons.append("evaluation time predates the end of the evidence window")
    for name in ("availability_percent", "availability_target_percent",
                 "alert_delivery_success_percent", "alert_delivery_target_percent"):
        value = getattr(e, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            reasons.append(f"{name} must be between 0 and 100")
    if (isinstance(e.availability_percent, (int, float)) and
            isinstance(e.availability_target_percent, (int, float)) and
            e.availability_percent < e.availability_target_percent):
        reasons.append("availability SLO is not met")
    if (isinstance(e.alert_delivery_success_percent, (int, float)) and
            isinstance(e.alert_delivery_target_percent, (int, float)) and
            e.alert_delivery_success_percent < e.alert_delivery_target_percent):
        reasons.append("alert delivery SLO is not met")
    if e.missing_critical_metrics:
        reasons.append("critical metrics are missing: " + ", ".join(e.missing_critical_metrics))
    value = e.unresolved_critical_alerts
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append("unresolved_critical_alerts must be a non-negative integer")
    elif value:
        reasons.append("critical alerts remain unresolved")
    if reasons:
        return StageAssessment(30, "OBSERVABILITY_HOLD", tuple(reasons))
    return StageAssessment(30, "OBSERVABILITY_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("SLO measurements, paging delivery, and retention settings require independent verification",))


@dataclass(frozen=True)
class ControlledReleaseEvidence:
    stage24_status: str
    stage25_status: str
    stage26_status: str
    stage27_status: str
    stage28_status: str
    stage29_status: str
    stage30_status: str
    stage4_lineage_verified: bool
    full_regression_passed: bool
    oos_review_ref: str
    venue_economics_review_ref: str
    credential_revocation_review_ref: str
    risk_reward_policy_reconciled: bool
    critical_findings_open: int
    candidate_digest: str
    independent_release_review_ref: str
    operational_owner_approval_ref: str


def evaluate_controlled_release(e: ControlledReleaseEvidence) -> StageAssessment:
    reasons: list[str] = []
    prerequisites = (
        ("stage24", e.stage24_status, "CREDENTIAL_CLOSURE_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage25", e.stage25_status, "REPOSITORY_INTEGRITY_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage26", e.stage26_status, "GOVERNANCE_INVENTORY_COMPLETE_UNVERIFIED"),
        ("stage27", e.stage27_status, "AUDIT_COVERAGE_COMPLETE_UNVERIFIED"),
        ("stage28", e.stage28_status, "MARKET_DATA_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage29", e.stage29_status, "ORDER_LIFECYCLE_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("stage30", e.stage30_status, "OBSERVABILITY_EVIDENCE_COMPLETE_UNVERIFIED"),
    )
    for label, actual, expected in prerequisites:
        if actual != expected:
            reasons.append(f"{label} prerequisite is not satisfied")
    if e.stage4_lineage_verified is not True:
        reasons.append("Stage 4 canonical lineage remains unverified")
    if e.full_regression_passed is not True:
        reasons.append("full repository regression is not certified")
    for name in ("oos_review_ref", "venue_economics_review_ref",
                 "credential_revocation_review_ref", "independent_release_review_ref",
                 "operational_owner_approval_ref"):
        _ref(getattr(e, name), name, reasons)
    if e.risk_reward_policy_reconciled is not True:
        reasons.append("risk/reward policy discrepancy remains unresolved")
    value = e.critical_findings_open
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append("critical_findings_open must be a non-negative integer")
    elif value:
        reasons.append("critical findings remain open")
    _digest(e.candidate_digest, "candidate_digest", reasons)
    if reasons:
        return StageAssessment(31, "CONTROLLED_RELEASE_HOLD", tuple(reasons))
    return StageAssessment(31, "READY_FOR_INDEPENDENT_CONTROLLED_REVIEW",
                           ("this is a review handoff only; it does not authorize deployment, Testnet execution, or LIVE trading",))
