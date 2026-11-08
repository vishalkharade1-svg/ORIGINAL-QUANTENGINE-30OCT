"""Focused tests for Stages 28–31 offline evidence gates."""
from dataclasses import replace
from core.governance.production_hardening_stages28_31 import (
    MarketDataIntegrityEvidence, OrderLifecycleEvidence, ObservabilityEvidence,
    ControlledReleaseEvidence, evaluate_market_data_integrity,
    evaluate_order_lifecycle, evaluate_observability, evaluate_controlled_release,
)


def market(**kw):
    d = dict(provider="provider", instrument="BTCUSDT", timeframe="1m",
        source_commit="a"*40, raw_capture_ref="raw:1", normalized_capture_ref="norm:1",
        raw_digest="b"*64, normalized_digest="c"*64,
        event_time_start_utc="2026-11-08T09:00:00Z",
        event_time_end_utc="2026-11-08T09:10:00Z",
        received_at_utc="2026-11-08T09:10:01Z", max_observed_lag_seconds=1,
        allowed_lag_seconds=5, duplicate_count=0, gap_count=0,
        correction_policy_ref="policy:1", independent_data_review_ref="review:data")
    d.update(kw)
    return MarketDataIntegrityEvidence(**d)


def orders(**kw):
    d = dict(venue="venue", instrument="BTCUSDT", source_commit="a"*40,
        scenario_matrix_ref="matrix:1", submit_ack_ref="submit:1",
        partial_fill_ref="partial:1", cancel_ack_ref="cancel:1", reject_ref="reject:1",
        timeout_recovery_ref="timeout:1", reconciliation_ref="reconcile:1",
        client_order_id_unique=True, duplicate_submission_count=0,
        orphan_order_count=0, unprotected_exposure_count=0,
        position_delta_reconciled=True, independent_execution_review_ref="review:exec")
    d.update(kw)
    return OrderLifecycleEvidence(**d)


def observability(**kw):
    d = dict(service="paper-engine", source_commit="a"*40, dashboard_ref="dash:1",
        alert_rules_ref="alerts:1", paging_drill_ref="paging:1",
        log_retention_policy_ref="logs:1", metric_retention_policy_ref="metrics:1",
        evaluated_at_utc="2026-11-08T12:00:00Z",
        window_start_utc="2026-11-08T10:00:00Z",
        window_end_utc="2026-11-08T11:00:00Z",
        availability_percent=99.99, availability_target_percent=99.9,
        alert_delivery_success_percent=100.0, alert_delivery_target_percent=99.0,
        missing_critical_metrics=(), unresolved_critical_alerts=0,
        independent_operations_review_ref="review:ops")
    d.update(kw)
    return ObservabilityEvidence(**d)


def release(**kw):
    d = dict(stage24_status="CREDENTIAL_CLOSURE_EVIDENCE_COMPLETE_UNVERIFIED",
        stage25_status="REPOSITORY_INTEGRITY_EVIDENCE_COMPLETE_UNVERIFIED",
        stage26_status="GOVERNANCE_INVENTORY_COMPLETE_UNVERIFIED",
        stage27_status="AUDIT_COVERAGE_COMPLETE_UNVERIFIED",
        stage28_status="MARKET_DATA_EVIDENCE_COMPLETE_UNVERIFIED",
        stage29_status="ORDER_LIFECYCLE_EVIDENCE_COMPLETE_UNVERIFIED",
        stage30_status="OBSERVABILITY_EVIDENCE_COMPLETE_UNVERIFIED",
        stage4_lineage_verified=True, full_regression_passed=True,
        oos_review_ref="review:oos", venue_economics_review_ref="review:venue",
        credential_revocation_review_ref="review:credential",
        risk_reward_policy_reconciled=True, critical_findings_open=0,
        candidate_digest="d"*64, independent_release_review_ref="review:release",
        operational_owner_approval_ref="approval:owner")
    d.update(kw)
    return ControlledReleaseEvidence(**d)


def test_stage28_accepts_clean_window_and_holds_on_gaps_lag_duplicates():
    assert evaluate_market_data_integrity(market()).status == "MARKET_DATA_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_market_data_integrity(market(gap_count=1)).status == "MARKET_DATA_HOLD"
    assert evaluate_market_data_integrity(market(max_observed_lag_seconds=6)).status == "MARKET_DATA_HOLD"
    assert evaluate_market_data_integrity(market(duplicate_count=1)).status == "MARKET_DATA_HOLD"


def test_stage28_rejects_reversed_window_and_bad_digest():
    assert evaluate_market_data_integrity(market(raw_digest="bad")).status == "MARKET_DATA_HOLD"
    assert evaluate_market_data_integrity(market(event_time_start_utc="2026-11-08T10:00:00Z")).status == "MARKET_DATA_HOLD"


def test_stage29_requires_all_lifecycle_paths_and_zero_exposure():
    assert evaluate_order_lifecycle(orders()).status == "ORDER_LIFECYCLE_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_order_lifecycle(orders(orphan_order_count=1)).status == "ORDER_LIFECYCLE_HOLD"
    assert evaluate_order_lifecycle(orders(unprotected_exposure_count=1)).status == "ORDER_LIFECYCLE_HOLD"
    assert evaluate_order_lifecycle(orders(client_order_id_unique=False)).status == "ORDER_LIFECYCLE_HOLD"


def test_stage30_enforces_slos_and_alert_closure():
    assert evaluate_observability(observability()).status == "OBSERVABILITY_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_observability(observability(availability_percent=99.0)).status == "OBSERVABILITY_HOLD"
    assert evaluate_observability(observability(unresolved_critical_alerts=1)).status == "OBSERVABILITY_HOLD"
    assert evaluate_observability(observability(missing_critical_metrics=("feed_lag",))).status == "OBSERVABILITY_HOLD"


def test_stage30_rejects_invalid_window_and_percentages():
    assert evaluate_observability(observability(availability_percent=101)).status == "OBSERVABILITY_HOLD"
    assert evaluate_observability(observability(window_end_utc="2026-11-08T09:00:00Z")).status == "OBSERVABILITY_HOLD"


def test_stage31_aggregates_all_controls_and_keeps_live_disabled():
    result = evaluate_controlled_release(release())
    assert result.status == "READY_FOR_INDEPENDENT_CONTROLLED_REVIEW"
    assert result.live_arming_permitted is False
    assert evaluate_controlled_release(release(stage4_lineage_verified=False)).status == "CONTROLLED_RELEASE_HOLD"
    assert evaluate_controlled_release(release(risk_reward_policy_reconciled=False)).status == "CONTROLLED_RELEASE_HOLD"
    assert evaluate_controlled_release(release(stage29_status="HOLD")).status == "CONTROLLED_RELEASE_HOLD"


def test_every_assessment_is_non_live():
    assert not evaluate_market_data_integrity(market()).live_arming_permitted
    assert not evaluate_order_lifecycle(orders()).live_arming_permitted
    assert not evaluate_observability(observability()).live_arming_permitted
    assert not evaluate_controlled_release(release()).live_arming_permitted
