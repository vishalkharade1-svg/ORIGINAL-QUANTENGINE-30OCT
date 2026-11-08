"""Tests for production hardening Stages 12–15 (offline, paper-only)."""
import pytest

from core.governance.production_hardening_runtime import (
    CostProfileActivationEvidence,
    DeploymentControlEvidence,
    PaperCanaryEvidence,
    activate_cost_profile,
    evaluate_paper_canary,
    evaluate_paper_deployment,
    make_audit_record,
    verify_audit_chain,
)


def cost(**overrides):
    values = dict(
        profile_id="delta-btc-paper",
        version="2026.11.08.1",
        venue="DELTA_INDIA_TESTNET",
        instrument="BTCUSD",
        per_trade=0.25,
        rate=0.0005,
        slippage_bps=2.0,
        source_ref="venue-fees:document-v4",
        observed_at_utc="2026-11-08T10:00:00Z",
        valid_until_utc="2026-12-08T10:00:00Z",
        independent_review_ref="review:economics-44",
        venue_verified=False,
        venue_verification_ref="",
    )
    values.update(overrides)
    return CostProfileActivationEvidence(**values)


def test_stage12_unverified_cost_profile_is_simulation_only():
    result = activate_cost_profile(
        cost(), expected_venue="DELTA_INDIA_TESTNET",
        expected_instrument="BTCUSD", evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert result.status == "PAPER_SIMULATION_ONLY"
    assert result.cost_spec is not None
    assert result.cost_spec.venue_source == ""
    assert result.live_arming_permitted is False


def test_stage12_verified_profile_requires_explicit_reference_and_exact_scope():
    result = activate_cost_profile(
        cost(venue_verified=True, venue_verification_ref="independent-check:77"),
        expected_venue="DELTA_INDIA_TESTNET", expected_instrument="BTCUSD",
        evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert result.status == "VENUE_VERIFIED_COST_PROFILE"
    assert result.cost_spec.venue_source == "independent-check:77"


def test_stage12_rejects_scope_mismatch_expiry_and_unknown_costs():
    mismatch = activate_cost_profile(
        cost(instrument="ETHUSD"), expected_venue="DELTA_INDIA_TESTNET",
        expected_instrument="BTCUSD", evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert mismatch.status == "BLOCKED"
    assert mismatch.cost_spec is None
    expired = activate_cost_profile(
        cost(valid_until_utc="2026-11-08T10:30:00Z"),
        expected_venue="DELTA_INDIA_TESTNET", expected_instrument="BTCUSD",
        evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert expired.status == "BLOCKED"
    unknown = activate_cost_profile(
        cost(rate=float("nan")), expected_venue="DELTA_INDIA_TESTNET",
        expected_instrument="BTCUSD", evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert unknown.status == "BLOCKED"


def test_stage12_zero_cost_requires_explicit_source_and_is_never_inferred():
    result = activate_cost_profile(
        cost(per_trade=0, rate=0, slippage_bps=0),
        expected_venue="DELTA_INDIA_TESTNET", expected_instrument="BTCUSD",
        evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert result.status == "PAPER_SIMULATION_ONLY"
    assert result.cost_spec.compute(1000) == (0.0, 0.0)


def deployment(**overrides):
    values = dict(
        release_assessment_stage=11,
        release_assessment_status="READY_FOR_INDEPENDENT_RELEASE_REVIEW",
        release_assessment_live_arming_permitted=False,
        independent_review_ref="review:release-1",
        strategy_digest="a" * 64,
        deployment_digest="a" * 64,
        rollback_artifact_ref="artifact:rollback-1",
        paper_dry_run_ref="paper-run:dry-1",
        kill_switch_tested=True,
    )
    values.update(overrides)
    return DeploymentControlEvidence(**values)


def test_stage13_only_marks_paper_deployment_ready():
    result = evaluate_paper_deployment(deployment())
    assert result.status == "PAPER_DEPLOYMENT_READY"
    assert result.live_arming_permitted is False


@pytest.mark.parametrize("override", [
    {"release_assessment_status": "HOLD"},
    {"release_assessment_live_arming_permitted": True},
    {"deployment_digest": "b" * 64},
    {"rollback_artifact_ref": ""},
    {"paper_dry_run_ref": ""},
    {"kill_switch_tested": False},
    {"independent_review_ref": ""},
])
def test_stage13_missing_or_conflicting_control_blocks(override):
    assert evaluate_paper_deployment(deployment(**override)).status == "BLOCKED"


def test_stage14_builds_and_verifies_hash_chain():
    first = make_audit_record(
        sequence=1, previous_sha256="0" * 64,
        occurred_at_utc="2026-11-08T10:00:00Z",
        event_type="PAPER_GATE_ASSESSED",
        attributes={"mode": "PAPER", "allowed": False, "reason_code": "COST_PROFILE_UNVERIFIED"},
    )
    second = make_audit_record(
        sequence=2, previous_sha256=first["sha256"],
        occurred_at_utc="2026-11-08T10:01:00+00:00",
        event_type="KILL_SWITCH_DRILL",
        attributes={"result": "PASS", "exchange_write_count": 0},
    )
    result = verify_audit_chain([first, second])
    assert result.valid is True
    assert result.records_verified == 2
    assert result.head_sha256 == second["sha256"]


def test_stage14_detects_tampering_and_broken_links():
    first = make_audit_record(
        sequence=1, previous_sha256="0" * 64,
        occurred_at_utc="2026-11-08T10:00:00Z",
        event_type="PAPER_GATE_ASSESSED", attributes={"mode": "PAPER"},
    )
    second = make_audit_record(
        sequence=2, previous_sha256=first["sha256"],
        occurred_at_utc="2026-11-08T10:01:00Z",
        event_type="PAPER_GATE_ASSESSED", attributes={"mode": "PAPER"},
    )
    tampered = dict(second, attributes={"mode": "LIVE"})
    assert verify_audit_chain([first, tampered]).valid is False
    broken = dict(second, previous_sha256="f" * 64)
    assert verify_audit_chain([first, broken]).valid is False


@pytest.mark.parametrize("attributes", [
    {"api_key_ref": "should-not-be-recorded"},
    {"nested": {"access_token": "redacted"}},
    {"authorization": "Bearer ..."},
])
def test_stage14_rejects_sensitive_attribute_names(attributes):
    with pytest.raises(ValueError, match="sensitive field"):
        make_audit_record(
            sequence=1, previous_sha256="0" * 64,
            occurred_at_utc="2026-11-08T10:00:00Z",
            event_type="UNSAFE", attributes=attributes,
        )


def canary(**overrides):
    values = dict(
        canary_id="paper-canary-2026-11-08-a",
        started_at_utc="2026-11-08T09:00:00Z",
        ended_at_utc="2026-11-08T10:00:00Z",
        evaluated_at_utc="2026-11-08T10:01:00Z",
        minimum_samples=100,
        observed_samples=125,
        max_latency_ms=180,
        latency_budget_ms=250,
        data_gap_count=0,
        exchange_write_count=0,
        rejected_order_count=1,
        max_rejected_orders=3,
        realized_loss=2.5,
        loss_budget=10.0,
        kill_switch_tested=True,
        rollback_artifact_ref="artifact:rollback-paper-1",
    )
    values.update(overrides)
    return PaperCanaryEvidence(**values)


def test_stage15_clean_paper_canary_passes_but_never_arms_live():
    result = evaluate_paper_canary(canary())
    assert result.status == "PAPER_CANARY_PASS"
    assert result.live_arming_permitted is False


@pytest.mark.parametrize("override", [
    {"exchange_write_count": 1},
    {"data_gap_count": 1},
    {"max_latency_ms": 300},
    {"rejected_order_count": 4},
    {"realized_loss": 11.0},
])
def test_stage15_operational_breach_requires_rollback(override):
    assert evaluate_paper_canary(canary(**override)).status == "ROLLBACK_REQUIRED"


def test_stage15_insufficient_sample_or_missing_kill_switch_holds():
    result = evaluate_paper_canary(canary(observed_samples=20))
    assert result.status == "HOLD"
    result = evaluate_paper_canary(canary(kill_switch_tested=False))
    assert result.status == "HOLD"


def test_stage15_exchange_write_takes_rollback_priority_over_other_holds():
    result = evaluate_paper_canary(canary(observed_samples=2, exchange_write_count=1))
    assert result.status == "ROLLBACK_REQUIRED"


def test_stage15_wrong_metric_types_fail_closed_without_type_error():
    assert evaluate_paper_canary(canary(observed_samples="many")).status == "HOLD"
    assert evaluate_paper_canary(canary(data_gap_count=True)).status == "HOLD"


def test_stage15_invalid_time_window_and_negative_metrics_hold():
    assert evaluate_paper_canary(canary(ended_at_utc="2026-11-08T08:00:00Z")).status == "HOLD"
    assert evaluate_paper_canary(canary(exchange_write_count=-1)).status == "HOLD"
