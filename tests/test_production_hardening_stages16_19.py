"""Tests for production hardening Stages 16–19 (offline, evidence-only)."""
from core.governance.production_hardening_runtime import (
    EvidenceArtifactDescriptor,
    EvidencePackageEvidence,
    TestnetDrillEvidence as DrillEvidence,
    OperationalMonitorEvidence,
    ControlledReviewEvidence,
    evaluate_evidence_package,
    evaluate_testnet_drill,
    evaluate_operational_monitor,
    evaluate_controlled_review,
)


def package(**overrides):
    values = dict(
        package_id="release-evidence-2026-11",
        scope="quantengine-paper",
        issuer_ref="operator:release-owner",
        independent_reviewer_ref="reviewer:independent-01",
        source_commit="a" * 64,
        reviewed_at_utc="2026-11-08T10:00:00Z",
        valid_until_utc="2026-12-08T10:00:00Z",
        required_artifact_ids=("source", "regression", "oos"),
        artifacts=(
            EvidenceArtifactDescriptor("source", "1" * 64, "artifact:source"),
            EvidenceArtifactDescriptor("regression", "2" * 64, "artifact:regression"),
            EvidenceArtifactDescriptor("oos", "3" * 64, "artifact:oos"),
        ),
    )
    values.update(overrides)
    return EvidencePackageEvidence(**values)


def test_stage16_complete_index_is_not_authentication():
    result = evaluate_evidence_package(
        package(), expected_scope="quantengine-paper",
        evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert result.status == "EVIDENCE_INDEX_COMPLETE_UNAUTHENTICATED"
    assert result.artifact_count == 3
    assert result.live_arming_permitted is False


def test_stage16_blocks_scope_expiry_and_same_reviewer():
    mismatch = evaluate_evidence_package(
        package(), expected_scope="quantengine-live",
        evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert mismatch.status == "BLOCKED"
    expired = evaluate_evidence_package(
        package(valid_until_utc="2026-11-08T10:30:00Z"),
        expected_scope="quantengine-paper", evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert expired.status == "BLOCKED"
    same = evaluate_evidence_package(
        package(independent_reviewer_ref="operator:release-owner"),
        expected_scope="quantengine-paper", evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert same.status == "BLOCKED"


def test_stage16_blocks_missing_duplicate_and_bad_hash_artifacts():
    missing = evaluate_evidence_package(
        package(artifacts=()), expected_scope="quantengine-paper",
        evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert missing.status == "BLOCKED"
    duplicate = evaluate_evidence_package(
        package(artifacts=(
            EvidenceArtifactDescriptor("source", "1" * 64, "a"),
            EvidenceArtifactDescriptor("source", "2" * 64, "b"),
        )),
        expected_scope="quantengine-paper", evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert duplicate.status == "BLOCKED"
    malformed = evaluate_evidence_package(
        package(artifacts=(
            EvidenceArtifactDescriptor("source", "bad", "a"),
            EvidenceArtifactDescriptor("regression", "2" * 64, "b"),
            EvidenceArtifactDescriptor("oos", "3" * 64, "c"),
        )),
        expected_scope="quantengine-paper", evaluated_at_utc="2026-11-08T11:00:00Z",
    )
    assert malformed.status == "BLOCKED"


def drill(**overrides):
    values = dict(
        drill_id="delta-testnet-drill-001",
        environment="DELTA_INDIA_TESTNET",
        started_at_utc="2026-11-08T10:00:00Z",
        ended_at_utc="2026-11-08T10:30:00Z",
        evaluated_at_utc="2026-11-08T11:00:00Z",
        stage16_status="EVIDENCE_INDEX_COMPLETE_UNAUTHENTICATED",
        read_only_probe_ref="drill:read-only",
        market_data_stream_ref="drill:market-stream",
        write_guard_test_ref="drill:write-guard",
        reconciliation_ref="drill:reconciliation",
        restart_recovery_ref="drill:restart",
        observed_samples=100,
        minimum_samples=50,
        exchange_write_count=0,
        unresolved_reconciliation_count=0,
        restart_recovery_passed=True,
    )
    values.update(overrides)
    return DrillEvidence(**values)


def test_stage17_complete_drill_is_unverified_and_non_live():
    result = evaluate_testnet_drill(drill())
    assert result.status == "TESTNET_DRILL_EVIDENCE_COMPLETE_UNVERIFIED"
    assert result.live_arming_permitted is False


def test_stage17_any_exchange_write_or_unresolved_position_fails():
    write = evaluate_testnet_drill(drill(exchange_write_count=1))
    assert write.status == "DRILL_FAILED"
    mismatch = evaluate_testnet_drill(drill(unresolved_reconciliation_count=1))
    assert mismatch.status == "DRILL_FAILED"


def test_stage17_missing_samples_or_recovery_holds():
    samples = evaluate_testnet_drill(drill(observed_samples=2))
    assert samples.status == "HOLD"
    recovery = evaluate_testnet_drill(drill(restart_recovery_passed=False))
    assert recovery.status == "HOLD"


def monitor(**overrides):
    values = dict(
        observed_at_utc="2026-11-08T10:59:00Z",
        evaluated_at_utc="2026-11-08T11:00:00Z",
        max_age_seconds=30,
        data_age_seconds=5,
        latency_ms=100,
        latency_budget_ms=250,
        clock_skew_ms=5,
        clock_skew_budget_ms=50,
        data_gap_count=0,
        position_mismatch_count=0,
        unresolved_order_count=0,
        audit_chain_valid=True,
        kill_switch_tested=True,
    )
    values.update(overrides)
    return OperationalMonitorEvidence(**values)


def test_stage18_healthy_monitor_and_breach_halts():
    healthy = evaluate_operational_monitor(monitor())
    assert healthy.status == "PAPER_MONITORING_HEALTHY"
    stale = evaluate_operational_monitor(monitor(data_age_seconds=31))
    assert stale.status == "HALT_PAPER_OPERATIONS"
    mismatch = evaluate_operational_monitor(monitor(position_mismatch_count=1))
    assert mismatch.status == "HALT_PAPER_OPERATIONS"
    audit = evaluate_operational_monitor(monitor(audit_chain_valid=False))
    assert audit.status == "HALT_PAPER_OPERATIONS"


def test_stage18_missing_kill_switch_or_bad_budget_holds():
    result = evaluate_operational_monitor(monitor(kill_switch_tested=False))
    assert result.status == "HOLD"
    invalid = evaluate_operational_monitor(monitor(latency_budget_ms=0))
    assert invalid.status == "HOLD"


def review(**overrides):
    values = dict(
        stage16_status="EVIDENCE_INDEX_COMPLETE_UNAUTHENTICATED",
        stage17_status="TESTNET_DRILL_EVIDENCE_COMPLETE_UNVERIFIED",
        stage18_status="PAPER_MONITORING_HEALTHY",
        stage4_lineage_verified=True,
        full_regression_passed=True,
        oos_certification_ref="oos:certification-01",
        independent_oos_review_ref="oos:independent-review-01",
        rr_policy_reconciled=True,
        owner_approval_ref="approval:release-owner",
        strategy_digest="a" * 64,
        deployment_digest="a" * 64,
    )
    values.update(overrides)
    return ControlledReviewEvidence(**values)


def test_stage19_ready_state_is_review_only():
    result = evaluate_controlled_review(review())
    assert result.status == "READY_FOR_CONTROLLED_TESTNET_REVIEW"
    assert result.live_arming_permitted is False


def test_stage19_holds_for_unresolved_lineage_and_regression():
    lineage = evaluate_controlled_review(review(stage4_lineage_verified=False))
    assert lineage.status == "HOLD"
    regression = evaluate_controlled_review(review(full_regression_passed=False))
    assert regression.status == "HOLD"


def test_stage19_requires_distinct_oos_review_and_matching_digests():
    duplicate = evaluate_controlled_review(
        review(independent_oos_review_ref="oos:certification-01")
    )
    assert duplicate.status == "HOLD"
    mismatch = evaluate_controlled_review(review(deployment_digest="b" * 64))
    assert mismatch.status == "HOLD"
    malformed = evaluate_controlled_review(review(strategy_digest="not-a-digest"))
    assert malformed.status == "HOLD"
