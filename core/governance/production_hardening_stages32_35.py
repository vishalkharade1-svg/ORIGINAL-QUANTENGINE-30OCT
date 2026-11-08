"""Offline evidence gates for production-hardening Stages 32–35.

These validators check operator-supplied evidence structure only. They never
run a strategy, query a venue, cancel orders, flatten positions, or deploy.
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


def _hash(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        reasons.append(f"{name} must be a lowercase SHA-256 digest")


def _commit(value: str, name: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not _GIT_SHA.fullmatch(value):
        reasons.append(f"{name} must be a 40-character Git commit ID")


def _time(value: str, name: str, reasons: list[str]) -> datetime | None:
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


def _nonnegative(value: int, name: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append(f"{name} must be a non-negative integer")


def _finite_nonnegative(value: float, name: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        reasons.append(f"{name} must be a finite non-negative number")


@dataclass(frozen=True)
class StrategyArtifactEvidence:
    strategy_name: str
    strategy_version: str
    source_commit: str
    strategy_spec_digest: str
    config_digest: str
    feature_schema_digest: str
    dependency_lock_digest: str
    runtime_image_digest: str
    artifact_digest: str
    deterministic_seed: int
    deterministic_replay_count: int
    replay_output_digests: tuple[str, ...]
    environment_fingerprint_ref: str
    independent_reproducibility_review_ref: str


def evaluate_strategy_artifact(e: StrategyArtifactEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("strategy_name", "strategy_version", "environment_fingerprint_ref",
                 "independent_reproducibility_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    for name in ("strategy_spec_digest", "config_digest", "feature_schema_digest",
                 "dependency_lock_digest", "runtime_image_digest", "artifact_digest"):
        _hash(getattr(e, name), name, reasons)
    _nonnegative(e.deterministic_seed, "deterministic_seed", reasons)
    _nonnegative(e.deterministic_replay_count, "deterministic_replay_count", reasons)
    if isinstance(e.deterministic_replay_count, int) and e.deterministic_replay_count < 2:
        reasons.append("at least two deterministic replays are required")
    if not isinstance(e.replay_output_digests, tuple) or len(e.replay_output_digests) < 2:
        reasons.append("at least two replay output digests are required")
    else:
        for index, digest in enumerate(e.replay_output_digests):
            _hash(digest, f"replay_output_digests[{index}]", reasons)
        if len(set(e.replay_output_digests)) != 1:
            reasons.append("deterministic replay outputs do not match")
    if isinstance(e.deterministic_replay_count, int) and not isinstance(e.deterministic_replay_count, bool):
        if isinstance(e.replay_output_digests, tuple) and len(e.replay_output_digests) != e.deterministic_replay_count:
            reasons.append("replay count does not match supplied output digests")
    if reasons:
        return StageAssessment(32, "STRATEGY_PROVENANCE_HOLD", tuple(reasons))
    return StageAssessment(32, "STRATEGY_PROVENANCE_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("artifact, environment, and replay digests require independent recomputation",))


@dataclass(frozen=True)
class BacktestValidityEvidence:
    dataset_ref: str
    dataset_digest: str
    source_commit: str
    train_start_utc: str
    train_end_utc: str
    validation_start_utc: str
    validation_end_utc: str
    test_start_utc: str
    test_end_utc: str
    maximum_label_horizon_seconds: int
    purge_seconds: int
    embargo_seconds: int
    split_is_chronological: bool
    feature_availability_audited: bool
    lookahead_tests_passed: bool
    survivorship_bias_reviewed: bool
    costs_and_fees_included: bool
    out_of_sample_set_untouched: bool
    independent_research_review_ref: str


def evaluate_backtest_validity(e: BacktestValidityEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("dataset_ref", "independent_research_review_ref"):
        _required(getattr(e, name), name, reasons)
    _hash(e.dataset_digest, "dataset_digest", reasons)
    _commit(e.source_commit, "source_commit", reasons)
    names = ("train_start_utc", "train_end_utc", "validation_start_utc",
             "validation_end_utc", "test_start_utc", "test_end_utc")
    times = {name: _time(getattr(e, name), name, reasons) for name in names}
    ordered = all(times[name] is not None for name in names)
    if ordered:
        if not (times["train_start_utc"] < times["train_end_utc"] <=
                times["validation_start_utc"] < times["validation_end_utc"] <=
                times["test_start_utc"] < times["test_end_utc"]):
            reasons.append("train/validation/test windows must be chronological and non-overlapping")
    for name in ("maximum_label_horizon_seconds", "purge_seconds", "embargo_seconds"):
        _nonnegative(getattr(e, name), name, reasons)
    if (isinstance(e.maximum_label_horizon_seconds, int) and
            isinstance(e.purge_seconds, int) and e.purge_seconds < e.maximum_label_horizon_seconds):
        reasons.append("purge window is shorter than the maximum label horizon")
    if (isinstance(e.maximum_label_horizon_seconds, int) and
            isinstance(e.embargo_seconds, int) and e.embargo_seconds < e.maximum_label_horizon_seconds):
        reasons.append("embargo window is shorter than the maximum label horizon")
    for name in ("split_is_chronological", "feature_availability_audited",
                 "lookahead_tests_passed", "survivorship_bias_reviewed",
                 "costs_and_fees_included", "out_of_sample_set_untouched"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if reasons:
        return StageAssessment(33, "BACKTEST_VALIDITY_HOLD", tuple(reasons))
    return StageAssessment(33, "BACKTEST_VALIDITY_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("dataset provenance, split construction, and research attestations require independent audit",))


@dataclass(frozen=True)
class ExecutionCapacityEvidence:
    venue: str
    instrument: str
    source_commit: str
    sample_window_ref: str
    volume_profile_ref: str
    spread_model_ref: str
    impact_model_ref: str
    fee_schedule_ref: str
    stress_scenario_ref: str
    independent_execution_economics_review_ref: str
    maximum_participation_rate_percent: float
    allowed_participation_rate_percent: float
    maximum_spread_bps: float
    allowed_spread_bps: float
    maximum_slippage_bps: float
    allowed_slippage_bps: float
    maximum_impact_bps: float
    allowed_impact_bps: float
    capacity_breach_count: int
    rejected_stress_scenario_count: int
    costs_included_in_performance: bool


def evaluate_execution_capacity(e: ExecutionCapacityEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("venue", "instrument", "sample_window_ref", "volume_profile_ref",
                 "spread_model_ref", "impact_model_ref", "fee_schedule_ref",
                 "stress_scenario_ref", "independent_execution_economics_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    metrics = ("maximum_participation_rate_percent", "allowed_participation_rate_percent",
               "maximum_spread_bps", "allowed_spread_bps", "maximum_slippage_bps",
               "allowed_slippage_bps", "maximum_impact_bps", "allowed_impact_bps")
    for name in metrics:
        _finite_nonnegative(getattr(e, name), name, reasons)
    comparisons = (("maximum_participation_rate_percent", "allowed_participation_rate_percent"),
                   ("maximum_spread_bps", "allowed_spread_bps"),
                   ("maximum_slippage_bps", "allowed_slippage_bps"),
                   ("maximum_impact_bps", "allowed_impact_bps"))
    for observed, limit in comparisons:
        a, b = getattr(e, observed), getattr(e, limit)
        if (isinstance(a, (int, float)) and not isinstance(a, bool) and math.isfinite(a) and
                isinstance(b, (int, float)) and not isinstance(b, bool) and math.isfinite(b) and a > b):
            reasons.append(f"{observed} exceeds {limit}")
    _nonnegative(e.capacity_breach_count, "capacity_breach_count", reasons)
    _nonnegative(e.rejected_stress_scenario_count, "rejected_stress_scenario_count", reasons)
    if isinstance(e.capacity_breach_count, int) and e.capacity_breach_count:
        reasons.append("capacity breaches remain unresolved")
    if isinstance(e.rejected_stress_scenario_count, int) and e.rejected_stress_scenario_count:
        reasons.append("stress scenarios were rejected or not completed")
    if e.costs_included_in_performance is not True:
        reasons.append("fees, spread, slippage, and impact are not attested in performance results")
    if reasons:
        return StageAssessment(34, "EXECUTION_CAPACITY_HOLD", tuple(reasons))
    return StageAssessment(34, "EXECUTION_CAPACITY_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("liquidity samples and execution-cost models require independent recomputation",))


_REQUIRED_DRILLS = {
    "stale_market_data", "venue_disconnect", "risk_limit_breach",
    "operator_kill_switch", "process_crash", "clock_skew",
}


@dataclass(frozen=True)
class RuntimeContainmentEvidence:
    service: str
    source_commit: str
    drill_matrix_ref: str
    independent_safety_review_ref: str
    completed_drills: tuple[str, ...]
    maximum_detection_latency_ms: int
    allowed_detection_latency_ms: int
    maximum_containment_latency_ms: int
    allowed_containment_latency_ms: int
    open_orders_cancelled_or_reconciled: bool
    residual_exposure_reconciled: bool
    restart_requires_manual_rearm: bool
    automatic_rearm_disabled: bool
    unresolved_critical_drills: int


def evaluate_runtime_containment(e: RuntimeContainmentEvidence) -> StageAssessment:
    reasons: list[str] = []
    for name in ("service", "drill_matrix_ref", "independent_safety_review_ref"):
        _required(getattr(e, name), name, reasons)
    _commit(e.source_commit, "source_commit", reasons)
    if not isinstance(e.completed_drills, tuple):
        reasons.append("completed_drills must be a tuple of scenario identifiers")
    else:
        missing = sorted(_REQUIRED_DRILLS - set(e.completed_drills))
        if missing:
            reasons.append("required containment drills missing: " + ", ".join(missing))
    for name in ("maximum_detection_latency_ms", "allowed_detection_latency_ms",
                 "maximum_containment_latency_ms", "allowed_containment_latency_ms",
                 "unresolved_critical_drills"):
        _nonnegative(getattr(e, name), name, reasons)
    if (isinstance(e.maximum_detection_latency_ms, int) and
            isinstance(e.allowed_detection_latency_ms, int) and
            e.maximum_detection_latency_ms > e.allowed_detection_latency_ms):
        reasons.append("detection latency exceeds the allowed limit")
    if (isinstance(e.maximum_containment_latency_ms, int) and
            isinstance(e.allowed_containment_latency_ms, int) and
            e.maximum_containment_latency_ms > e.allowed_containment_latency_ms):
        reasons.append("containment latency exceeds the allowed limit")
    for name in ("open_orders_cancelled_or_reconciled", "residual_exposure_reconciled",
                 "restart_requires_manual_rearm", "automatic_rearm_disabled"):
        if getattr(e, name) is not True:
            reasons.append(f"{name} must be explicitly attested true")
    if isinstance(e.unresolved_critical_drills, int) and e.unresolved_critical_drills:
        reasons.append("critical containment drill failures remain unresolved")
    if reasons:
        return StageAssessment(35, "RUNTIME_CONTAINMENT_HOLD", tuple(reasons))
    return StageAssessment(35, "RUNTIME_CONTAINMENT_EVIDENCE_COMPLETE_UNVERIFIED",
                           ("drill execution, venue-side cancellation, and containment timing require independent verification",))
