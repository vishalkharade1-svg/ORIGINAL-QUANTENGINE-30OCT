"""Offline evidence gates for production-hardening Stages 48–51.

Pure structural validators over operator-supplied evidence. They do not
benchmark live services, run strategies, modify ledgers, approve releases,
deploy software, or authorize live trading.
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


def _finite(value: float, name: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        reasons.append(f"{name} must be a finite number")


def _timestamp(value: str, name: str, reasons: list[str]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (AttributeError, TypeError, ValueError):
        reasons.append(f"{name} must be ISO-8601 with an explicit UTC offset")
        return None


@dataclass(frozen=True)
class CapacityResilienceEvidence:
    service: str
    source_commit: str
    workload_digest: str
    test_report_ref: str
    environment_attestation_ref: str
    failover_drill_ref: str
    recovery_report_ref: str
    independent_review_ref: str
    tested_at_utc: str
    requests_per_second: float
    required_requests_per_second: float
    p95_latency_ms: float
    p95_latency_limit_ms: float
    p99_latency_ms: float
    p99_latency_limit_ms: float
    error_rate: float
    error_rate_limit: float
    recovery_seconds: float
    recovery_limit_seconds: float
    saturation_events: int
    dropped_requests: int
    test_environment_isolated: bool
    failover_tested: bool
    recovery_verified: bool


def evaluate_capacity_resilience(e: CapacityResilienceEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("service", "test_report_ref", "environment_attestation_ref",
                 "failover_drill_ref", "recovery_report_ref", "independent_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    _digest(e.workload_digest, "workload_digest", reasons)
    _timestamp(e.tested_at_utc, "tested_at_utc", reasons)
    numeric = ("requests_per_second", "required_requests_per_second", "p95_latency_ms",
               "p95_latency_limit_ms", "p99_latency_ms", "p99_latency_limit_ms",
               "error_rate", "error_rate_limit", "recovery_seconds", "recovery_limit_seconds")
    for name in numeric:
        _finite(getattr(e, name), name, reasons)
    for name in ("saturation_events", "dropped_requests"):
        _count(getattr(e, name), name, reasons)
    pairs = (("requests_per_second", "required_requests_per_second", "throughput below required capacity"),
             ("p95_latency_ms", "p95_latency_limit_ms", "p95 latency limit exceeded"),
             ("p99_latency_ms", "p99_latency_limit_ms", "p99 latency limit exceeded"),
             ("error_rate", "error_rate_limit", "error rate limit exceeded"),
             ("recovery_seconds", "recovery_limit_seconds", "recovery time limit exceeded"))
    for observed, limit, message in pairs:
        a, b = getattr(e, observed), getattr(e, limit)
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (a, b)):
            if a < 0 or b < 0:
                reasons.append(f"{observed} and {limit} must be non-negative")
            elif (observed == "requests_per_second" and a < b) or (observed != "requests_per_second" and a > b):
                reasons.append(message)
    if isinstance(e.error_rate, (int, float)) and not isinstance(e.error_rate, bool) and not 0 <= e.error_rate <= 1:
        reasons.append("error_rate must be between zero and one")
    for name in ("test_environment_isolated", "failover_tested", "recovery_verified"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    for name in ("saturation_events", "dropped_requests"):
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    if reasons:
        return StageAssessment(48, "CAPACITY_RESILIENCE_HOLD", tuple(reasons))
    return StageAssessment(48, "CAPACITY_RESILIENCE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("load profile, latency, failover and recovery claims require independent reproduction",))


@dataclass(frozen=True)
class ModelChangeEvidence:
    strategy: str
    source_commit: str
    model_artifact_digest: str
    training_dataset_digest: str
    evaluation_dataset_digest: str
    evaluation_report_ref: str
    data_lineage_ref: str
    leakage_review_ref: str
    approval_record_ref: str
    rollback_record_ref: str
    independent_validation_ref: str
    training_end_utc: str
    evaluation_start_utc: str
    prior_model_digest: str
    performance_degradation: float
    maximum_allowed_degradation: float
    leakage_findings: int
    unapproved_features: int
    reproducibility_verified: bool
    chronological_split_verified: bool
    rollback_tested: bool
    approval_complete: bool


def evaluate_model_change(e: ModelChangeEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("strategy", "evaluation_report_ref", "data_lineage_ref", "leakage_review_ref",
                 "approval_record_ref", "rollback_record_ref", "independent_validation_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    for name in ("model_artifact_digest", "training_dataset_digest", "evaluation_dataset_digest",
                 "prior_model_digest"):
        _digest(getattr(e, name), name, reasons)
    train_end = _timestamp(e.training_end_utc, "training_end_utc", reasons)
    eval_start = _timestamp(e.evaluation_start_utc, "evaluation_start_utc", reasons)
    if train_end and eval_start and eval_start <= train_end:
        reasons.append("evaluation window must begin after training window ends")
    for name in ("performance_degradation", "maximum_allowed_degradation"):
        _finite(getattr(e, name), name, reasons)
        value = getattr(e, name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
            reasons.append(f"{name} must be non-negative")
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
           for v in (e.performance_degradation, e.maximum_allowed_degradation)):
        if e.performance_degradation > e.maximum_allowed_degradation:
            reasons.append("performance degradation exceeds approved limit")
    for name in ("leakage_findings", "unapproved_features"):
        _count(getattr(e, name), name, reasons)
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    for name in ("reproducibility_verified", "chronological_split_verified",
                 "rollback_tested", "approval_complete"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if e.model_artifact_digest == e.prior_model_digest:
        reasons.append("model artifact digest must differ from prior model for a model-change record")
    if reasons:
        return StageAssessment(49, "MODEL_CHANGE_HOLD", tuple(reasons))
    return StageAssessment(49, "MODEL_CHANGE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("model artifact, data lineage, evaluation and approval require independent validation",))


@dataclass(frozen=True)
class FinancialControlEvidence:
    entity: str
    source_commit: str
    accounting_period: str
    ledger_snapshot_digest: str
    bank_or_custody_statement_digest: str
    reconciliation_report_ref: str
    fee_schedule_ref: str
    valuation_policy_ref: str
    exception_register_ref: str
    independent_reviewer_ref: str
    closed_at_utc: str
    ledger_rows: int
    matched_rows: int
    unexplained_cash_difference: float
    unexplained_position_difference: float
    unexplained_fee_difference: float
    open_critical_exceptions: int
    stale_prices: int
    duplicate_entries: int
    reconciliation_independent: bool
    valuation_policy_applied: bool
    period_locked: bool


def evaluate_financial_controls(e: FinancialControlEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("entity", "accounting_period", "reconciliation_report_ref", "fee_schedule_ref",
                 "valuation_policy_ref", "exception_register_ref", "independent_reviewer_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    for name in ("ledger_snapshot_digest", "bank_or_custody_statement_digest"):
        _digest(getattr(e, name), name, reasons)
    _timestamp(e.closed_at_utc, "closed_at_utc", reasons)
    for name in ("ledger_rows", "matched_rows", "open_critical_exceptions", "stale_prices", "duplicate_entries"):
        _count(getattr(e, name), name, reasons)
    if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
           for v in (e.ledger_rows, e.matched_rows)) and e.matched_rows > e.ledger_rows:
        reasons.append("matched_rows cannot exceed ledger_rows")
    for name in ("unexplained_cash_difference", "unexplained_position_difference",
                 "unexplained_fee_difference"):
        _finite(getattr(e, name), name, reasons)
        value = getattr(e, name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0:
            reasons.append(f"{name} must be exactly zero")
    for name in ("open_critical_exceptions", "stale_prices", "duplicate_entries"):
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    for name in ("reconciliation_independent", "valuation_policy_applied", "period_locked"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if reasons:
        return StageAssessment(50, "FINANCIAL_CONTROLS_HOLD", tuple(reasons))
    return StageAssessment(50, "FINANCIAL_CONTROLS_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("ledger completeness, statements and independent reconciliation require source verification",))


@dataclass(frozen=True)
class ReleaseDecisionEvidence:
    release_candidate: str
    source_commit: str
    build_artifact_digest: str
    test_evidence_ref: str
    security_review_ref: str
    risk_assessment_ref: str
    operations_review_ref: str
    compliance_review_ref: str
    decision_record_ref: str
    dissent_record_ref: str
    rollback_plan_ref: str
    independent_chair_review_ref: str
    decided_at_utc: str
    required_approvals: int
    recorded_approvals: int
    unresolved_blockers: int
    unresolved_critical_risks: int
    material_dissent_count: int
    paper_only_scope: bool
    rollback_plan_tested: bool
    evidence_snapshot_frozen: bool
    decision_is_authorization: bool


def evaluate_release_decision(e: ReleaseDecisionEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("release_candidate", "test_evidence_ref", "security_review_ref", "risk_assessment_ref",
                 "operations_review_ref", "compliance_review_ref", "decision_record_ref",
                 "dissent_record_ref", "rollback_plan_ref", "independent_chair_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    _digest(e.build_artifact_digest, "build_artifact_digest", reasons)
    _timestamp(e.decided_at_utc, "decided_at_utc", reasons)
    for name in ("required_approvals", "recorded_approvals", "unresolved_blockers",
                 "unresolved_critical_risks", "material_dissent_count"):
        _count(getattr(e, name), name, reasons)
    if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
           for v in (e.required_approvals, e.recorded_approvals)):
        if e.recorded_approvals < e.required_approvals:
            reasons.append("required release approvals are incomplete")
    for name in ("unresolved_blockers", "unresolved_critical_risks"):
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value:
            reasons.append(f"{name} must be zero")
    for name in ("paper_only_scope", "rollback_plan_tested", "evidence_snapshot_frozen"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if e.decision_is_authorization is not False:
        reasons.append("decision record must explicitly state it is not an authorization")
    if reasons:
        return StageAssessment(51, "RELEASE_DECISION_HOLD", tuple(reasons))
    return StageAssessment(51, "RELEASE_DECISION_RECORDED_NOT_AUTHORIZED",
                           ("governance record completeness is not release approval or live-trading authorization",))
