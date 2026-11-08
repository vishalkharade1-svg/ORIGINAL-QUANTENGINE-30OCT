"""Focused tests for Stages 32–35 offline evidence gates."""
from core.governance.production_hardening_stages32_35 import (
    StrategyArtifactEvidence, BacktestValidityEvidence, ExecutionCapacityEvidence,
    RuntimeContainmentEvidence, evaluate_strategy_artifact, evaluate_backtest_validity,
    evaluate_execution_capacity, evaluate_runtime_containment,
)


def strategy(**kw):
    d = dict(strategy_name="sample", strategy_version="v1", source_commit="a"*40,
        strategy_spec_digest="b"*64, config_digest="c"*64, feature_schema_digest="d"*64,
        dependency_lock_digest="e"*64, runtime_image_digest="f"*64, artifact_digest="1"*64,
        deterministic_seed=7, deterministic_replay_count=2,
        replay_output_digests=("2"*64, "2"*64), environment_fingerprint_ref="env:1",
        independent_reproducibility_review_ref="review:repro")
    d.update(kw)
    return StrategyArtifactEvidence(**d)


def backtest(**kw):
    d = dict(dataset_ref="dataset:1", dataset_digest="a"*64, source_commit="b"*40,
        train_start_utc="2024-01-01T00:00:00Z", train_end_utc="2024-06-01T00:00:00Z",
        validation_start_utc="2024-06-02T00:00:00Z", validation_end_utc="2024-08-01T00:00:00Z",
        test_start_utc="2024-08-02T00:00:00Z", test_end_utc="2024-10-01T00:00:00Z",
        maximum_label_horizon_seconds=3600, purge_seconds=3600, embargo_seconds=3600,
        split_is_chronological=True, feature_availability_audited=True,
        lookahead_tests_passed=True, survivorship_bias_reviewed=True,
        costs_and_fees_included=True, out_of_sample_set_untouched=True,
        independent_research_review_ref="review:research")
    d.update(kw)
    return BacktestValidityEvidence(**d)


def capacity(**kw):
    d = dict(venue="venue", instrument="BTCUSDT", source_commit="a"*40,
        sample_window_ref="sample:1", volume_profile_ref="volume:1",
        spread_model_ref="spread:1", impact_model_ref="impact:1", fee_schedule_ref="fees:1",
        stress_scenario_ref="stress:1", independent_execution_economics_review_ref="review:capacity",
        maximum_participation_rate_percent=2.0, allowed_participation_rate_percent=5.0,
        maximum_spread_bps=3.0, allowed_spread_bps=5.0,
        maximum_slippage_bps=4.0, allowed_slippage_bps=8.0,
        maximum_impact_bps=5.0, allowed_impact_bps=10.0,
        capacity_breach_count=0, rejected_stress_scenario_count=0,
        costs_included_in_performance=True)
    d.update(kw)
    return ExecutionCapacityEvidence(**d)


def containment(**kw):
    d = dict(service="paper-engine", source_commit="a"*40, drill_matrix_ref="drills:1",
        independent_safety_review_ref="review:safety",
        completed_drills=("stale_market_data", "venue_disconnect", "risk_limit_breach",
                          "operator_kill_switch", "process_crash", "clock_skew"),
        maximum_detection_latency_ms=100, allowed_detection_latency_ms=500,
        maximum_containment_latency_ms=500, allowed_containment_latency_ms=2000,
        open_orders_cancelled_or_reconciled=True, residual_exposure_reconciled=True,
        restart_requires_manual_rearm=True, automatic_rearm_disabled=True,
        unresolved_critical_drills=0)
    d.update(kw)
    return RuntimeContainmentEvidence(**d)


def test_stage32_requires_pinned_artifacts_and_matching_replays():
    assert evaluate_strategy_artifact(strategy()).status == "STRATEGY_PROVENANCE_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_strategy_artifact(strategy(replay_output_digests=("2"*64, "3"*64))).status == "STRATEGY_PROVENANCE_HOLD"
    assert evaluate_strategy_artifact(strategy(source_commit="unpinned")).status == "STRATEGY_PROVENANCE_HOLD"


def test_stage33_enforces_chronology_purge_embargo_and_bias_controls():
    assert evaluate_backtest_validity(backtest()).status == "BACKTEST_VALIDITY_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_backtest_validity(backtest(embargo_seconds=10)).status == "BACKTEST_VALIDITY_HOLD"
    assert evaluate_backtest_validity(backtest(out_of_sample_set_untouched=False)).status == "BACKTEST_VALIDITY_HOLD"
    assert evaluate_backtest_validity(backtest(test_start_utc="2024-07-01T00:00:00Z")).status == "BACKTEST_VALIDITY_HOLD"


def test_stage34_holds_on_capacity_cost_or_stress_breaches():
    assert evaluate_execution_capacity(capacity()).status == "EXECUTION_CAPACITY_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_execution_capacity(capacity(maximum_slippage_bps=9)).status == "EXECUTION_CAPACITY_HOLD"
    assert evaluate_execution_capacity(capacity(capacity_breach_count=1)).status == "EXECUTION_CAPACITY_HOLD"
    assert evaluate_execution_capacity(capacity(costs_included_in_performance=False)).status == "EXECUTION_CAPACITY_HOLD"


def test_stage35_requires_all_kill_switch_drills_and_manual_rearm():
    assert evaluate_runtime_containment(containment()).status == "RUNTIME_CONTAINMENT_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_runtime_containment(containment(completed_drills=("venue_disconnect",))).status == "RUNTIME_CONTAINMENT_HOLD"
    assert evaluate_runtime_containment(containment(automatic_rearm_disabled=False)).status == "RUNTIME_CONTAINMENT_HOLD"
    assert evaluate_runtime_containment(containment(maximum_containment_latency_ms=3000)).status == "RUNTIME_CONTAINMENT_HOLD"


def test_all_stage_assessments_keep_live_arming_disabled():
    results = (evaluate_strategy_artifact(strategy()), evaluate_backtest_validity(backtest()),
               evaluate_execution_capacity(capacity()), evaluate_runtime_containment(containment()))
    assert all(result.live_arming_permitted is False for result in results)
