"""Unit tests for evidence-only production hardening Stages 8–11."""
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from core.governance.production_hardening import (
    CredentialIncidentEvidence,
    ReleaseEvidence,
    RestartRecoveryEvidence,
    VenueCostEvidence,
    evaluate_credential_incident,
    evaluate_release_gate,
    evaluate_restart_recovery,
    evaluate_venue_cost_evidence,
)


def credential(**overrides):
    values = dict(
        old_key_revoked=True,
        provider_revocation_ref="provider-ticket:revoked-123",
        account_activity_reviewed=True,
        account_review_ref="security-review:account-456",
        replacement_key_ref="vault-ref:delta-testnet-new",
        replacement_is_testnet_only=True,
        replacement_is_least_privilege=True,
        secret_store_ref="vault://quantengine/delta-testnet",
        secret_scan_passed=True,
        independent_review_ref="review:security-789",
        attested_at_utc="2026-11-08T10:00:00Z",
    )
    values.update(overrides)
    return CredentialIncidentEvidence(**values)


def cost(**overrides):
    values = dict(
        profile_id="delta-india-testnet",
        version="2026-11-08.1",
        venue="DELTA_INDIA_TESTNET",
        instruments=("BTCUSD", "ETHUSD"),
        per_trade=0.0,
        rate=0.0005,
        slippage_bps=2.5,
        source_ref="venue-doc:fees-v3",
        observed_at_utc="2026-11-08T10:00:00Z",
        funding_model_ref="funding-spec:perpetual-v1",
        funding_model_integrated=True,
        independent_review_ref="review:economics-123",
    )
    values.update(overrides)
    return VenueCostEvidence(**values)


def recovery(**overrides):
    values = dict(
        journal_sha256="a" * 64,
        schema_version="3",
        checkpoint_at_utc="2026-11-08T10:00:00Z",
        evaluated_at_utc="2026-11-08T10:00:30Z",
        exchange_snapshot_ref="snapshot:delta-read-only-123",
        exchange_snapshot_at_utc="2026-11-08T10:00:25Z",
        query_complete=True,
        pagination_complete=True,
        balances_complete=True,
        positions_complete=True,
        open_orders_complete=True,
        fills_complete=True,
        local_exchange_identity_match=True,
        state_digest_match=True,
        unresolved_order_count=0,
        anomalies=(),
        kill_switch_active=True,
        max_snapshot_age_seconds=60,
    )
    values.update(overrides)
    return RestartRecoveryEvidence(**values)


def test_stage8_never_accepts_or_stores_raw_credential_fields():
    names = {field.name for field in fields(CredentialIncidentEvidence)}
    assert "api_key" not in names
    assert "api_secret" not in names
    assert "secret" not in names


def test_stage8_complete_operator_attestation_is_not_called_verified():
    result = evaluate_credential_incident(credential())
    assert result.status == "ATTESTATION_COMPLETE_UNVERIFIED"
    assert result.live_arming_permitted is False
    assert "independent verification" in result.reasons[0]


@pytest.mark.parametrize("override", [
    {"old_key_revoked": False},
    {"account_activity_reviewed": False},
    {"replacement_is_testnet_only": False},
    {"replacement_is_least_privilege": False},
    {"secret_scan_passed": False},
    {"provider_revocation_ref": ""},
    {"independent_review_ref": ""},
    {"attested_at_utc": "2026-11-08T10:00:00"},
    {"old_key_revoked": "yes"},
])
def test_stage8_missing_security_evidence_fails_closed(override):
    assert evaluate_credential_incident(credential(**override)).status == "INCOMPLETE"


def test_stage9_complete_cost_inputs_remain_unverified_until_external_validation():
    result = evaluate_venue_cost_evidence(cost())
    assert result.status == "COST_EVIDENCE_COMPLETE_UNVERIFIED"
    assert result.live_arming_permitted is False


@pytest.mark.parametrize("override", [
    {"source_ref": ""},
    {"instruments": ()},
    {"funding_model_ref": ""},
    {"funding_model_integrated": False},
    {"independent_review_ref": ""},
    {"observed_at_utc": "2026-11-08T10:00:00"},
    {"slippage_bps": float("nan")},
    {"rate": -0.01},
    {"instruments": ("BTCUSD", "BTCUSD")},
    {"funding_model_integrated": "true"},
])
def test_stage9_incomplete_or_invalid_cost_evidence_fails_closed(override):
    assert evaluate_venue_cost_evidence(cost(**override)).status == "INCOMPLETE"


def test_stage9_explicit_zero_fee_component_is_allowed_when_provenanced():
    result = evaluate_venue_cost_evidence(cost(per_trade=0.0))
    assert result.status == "COST_EVIDENCE_COMPLETE_UNVERIFIED"


def test_stage10_clean_recovery_is_paper_only_and_keeps_kill_switch():
    result = evaluate_restart_recovery(recovery())
    assert result.status == "PAPER_RECOVERY_ONLY"
    assert result.live_arming_permitted is False
    assert "automatic restart" in result.reasons[0]


@pytest.mark.parametrize("override", [
    {"journal_sha256": "not-a-digest"},
    {"query_complete": False},
    {"pagination_complete": False},
    {"balances_complete": False},
    {"positions_complete": False},
    {"open_orders_complete": False},
    {"fills_complete": False},
    {"local_exchange_identity_match": False},
    {"state_digest_match": False},
    {"unresolved_order_count": 1},
    {"anomalies": ("UNKNOWN_EXCHANGE_ORDER",)},
    {"kill_switch_active": False},
    {"exchange_snapshot_at_utc": "2026-11-08T09:50:00Z"},
    {"query_complete": "yes"},
    {"unresolved_order_count": False},
    {"max_snapshot_age_seconds": 0},
])
def test_stage10_any_recovery_gap_blocks_resume(override):
    assert evaluate_restart_recovery(recovery(**override)).status == "BLOCKED"


def test_stage10_rejects_naive_timestamps():
    assert evaluate_restart_recovery(
        recovery(evaluated_at_utc="2026-11-08T10:00:30")
    ).status == "BLOCKED"


def test_stage11_baseline_release_gate_is_hold_and_never_arms_live():
    from core.governance.production_hardening import GateAssessment
    evidence = ReleaseEvidence(
        credential_assessment=GateAssessment(8, "INCOMPLETE", ("not rotated",)),
        cost_assessment=GateAssessment(9, "INCOMPLETE", ("zero-cost default",)),
        recovery_assessment=GateAssessment(10, "BLOCKED", ("journal missing",)),
        rr_policy_reconciled=False,
        source_lineage_verified=False,
        full_regression_green=False,
        oos_certificate_ref="",
        independent_oos_review_ref="",
        frozen_strategy_digest="frozen",
        evaluated_strategy_digest="changed",
        edge_established_by_oos=False,
        operator_release_approval_ref="",
    )
    result = evaluate_release_gate(evidence)
    assert result.status == "HOLD"
    assert result.live_arming_permitted is False
    assert any("strategy digest differs" in reason for reason in result.reasons)


def test_stage11_even_complete_fields_only_advance_to_independent_review():
    from core.governance.production_hardening import GateAssessment
    evidence = ReleaseEvidence(
        credential_assessment=GateAssessment(8, "ATTESTATION_COMPLETE_UNVERIFIED", ()),
        cost_assessment=GateAssessment(9, "COST_EVIDENCE_COMPLETE_UNVERIFIED", ()),
        recovery_assessment=GateAssessment(10, "PAPER_RECOVERY_ONLY", ()),
        rr_policy_reconciled=True,
        source_lineage_verified=True,
        full_regression_green=True,
        oos_certificate_ref="oos:certificate-1",
        independent_oos_review_ref="review:oos-1",
        frozen_strategy_digest="same",
        evaluated_strategy_digest="same",
        edge_established_by_oos=True,
        operator_release_approval_ref="approval:owner-1",
    )
    result = evaluate_release_gate(evidence)
    assert result.status == "READY_FOR_INDEPENDENT_RELEASE_REVIEW"
    assert result.live_arming_permitted is False
