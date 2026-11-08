"""Focused tests for Stages 36–39 offline evidence gates."""
from core.governance.production_hardening_stages36_39 import (
    PortfolioRiskEvidence, LedgerReconciliationEvidence, ChangeIncidentEvidence,
    GovernanceReadinessEvidence, evaluate_portfolio_risk, evaluate_ledger_reconciliation,
    evaluate_change_incident_control, evaluate_governance_readiness,
)


def portfolio(**kw):
    d = dict(portfolio_id="paper-book", as_of_utc="2026-11-08T10:00:00Z",
        source_commit="a"*40, positions_snapshot_digest="b"*64, risk_model_ref="risk:1",
        stress_suite_ref="stress:1", independent_risk_review_ref="review:risk",
        gross_exposure=50000.0, net_exposure=5000.0, equity=25000.0,
        gross_exposure_limit=60000.0, net_exposure_limit=10000.0,
        leverage=2.0, leverage_limit=3.0, largest_single_name_percent=20.0,
        single_name_limit_percent=30.0, concentration_hhi=0.15,
        concentration_hhi_limit=0.25, stress_loss_percent=8.0,
        stress_loss_limit_percent=12.0, margin_buffer_percent=40.0,
        minimum_margin_buffer_percent=25.0, unhedged_position_count=0,
        unresolved_limit_breaches=0)
    d.update(kw)
    return PortfolioRiskEvidence(**d)


def ledger(**kw):
    d = dict(account_ref="paper-account", venue_ref="simulated-venue", source_commit="a"*40,
        internal_ledger_digest="b"*64, external_statement_digest="c"*64,
        positions_snapshot_digest="d"*64, reconciliation_report_ref="reconcile:1",
        independent_finance_review_ref="review:finance",
        period_start_utc="2026-11-01T00:00:00Z", period_end_utc="2026-11-02T00:00:00Z",
        reconciled_at_utc="2026-11-02T00:01:00Z", internal_cash=1000.0,
        external_cash=1000.01, internal_position_value=5000.0,
        external_position_value=5000.02, allowed_cash_delta=0.05,
        allowed_position_delta=0.05, duplicate_ledger_event_count=0,
        missing_external_event_count=0, orphan_internal_event_count=0,
        unresolved_fee_count=0, sequence_gap_count=0, watermark_monotonic=True)
    d.update(kw)
    return LedgerReconciliationEvidence(**d)


def change(**kw):
    d = dict(service="paper-engine", source_commit="a"*40, change_ticket_ref="change:1",
        impact_assessment_ref="impact:1", test_report_ref="tests:1",
        rollback_plan_ref="rollback:1", rollback_artifact_digest="b"*64,
        incident_register_ref="incidents:1", independent_change_review_ref="review:change",
        operational_owner_approval_ref="approval:ops",
        change_window_start_utc="2026-11-08T09:00:00Z",
        change_window_end_utc="2026-11-08T10:00:00Z",
        tested_in_paper_environment=True, rollback_rehearsed=True,
        monitoring_and_alerts_verified=True, operator_runbook_updated=True,
        unresolved_critical_incidents=0, unapproved_changes=0,
        emergency_change_count=0, emergency_changes_reviewed=True)
    d.update(kw)
    return ChangeIncidentEvidence(**d)


def governance(**kw):
    d = dict(stage32_status="STRATEGY_PROVENANCE_EVIDENCE_COMPLETE_UNVERIFIED",
        stage33_status="BACKTEST_VALIDITY_EVIDENCE_COMPLETE_UNVERIFIED",
        stage34_status="EXECUTION_CAPACITY_EVIDENCE_COMPLETE_UNVERIFIED",
        stage35_status="RUNTIME_CONTAINMENT_EVIDENCE_COMPLETE_UNVERIFIED",
        stage36_status="PORTFOLIO_RISK_EVIDENCE_COMPLETE_UNVERIFIED",
        stage37_status="LEDGER_RECONCILIATION_EVIDENCE_COMPLETE_UNVERIFIED",
        stage38_status="CHANGE_INCIDENT_CONTROL_EVIDENCE_COMPLETE_UNVERIFIED",
        stage4_lineage_verified=True, credentials_revoked_and_reviewed=True,
        full_repository_regression_passed=True, independent_oos_review_complete=True,
        independent_venue_economics_review_complete=True, risk_reward_policy_reconciled=True,
        critical_findings_open=0, candidate_digest="e"*64,
        independent_governance_review_ref="review:governance",
        paper_operator_approval_ref="approval:paper")
    d.update(kw)
    return GovernanceReadinessEvidence(**d)


def test_stage36_enforces_portfolio_exposure_concentration_and_stress_limits():
    assert evaluate_portfolio_risk(portfolio()).status == "PORTFOLIO_RISK_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_portfolio_risk(portfolio(leverage=4.0)).status == "PORTFOLIO_RISK_HOLD"
    assert evaluate_portfolio_risk(portfolio(unresolved_limit_breaches=1)).status == "PORTFOLIO_RISK_HOLD"
    assert evaluate_portfolio_risk(portfolio(margin_buffer_percent=10.0)).status == "PORTFOLIO_RISK_HOLD"


def test_stage37_requires_balanced_ledger_and_zero_unmatched_events():
    assert evaluate_ledger_reconciliation(ledger()).status == "LEDGER_RECONCILIATION_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_ledger_reconciliation(ledger(external_cash=1100.0)).status == "LEDGER_RECONCILIATION_HOLD"
    assert evaluate_ledger_reconciliation(ledger(orphan_internal_event_count=1)).status == "LEDGER_RECONCILIATION_HOLD"
    assert evaluate_ledger_reconciliation(ledger(watermark_monotonic=False)).status == "LEDGER_RECONCILIATION_HOLD"


def test_stage38_requires_paper_tests_rollback_and_change_approvals():
    assert evaluate_change_incident_control(change()).status == "CHANGE_INCIDENT_CONTROL_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_change_incident_control(change(rollback_rehearsed=False)).status == "CHANGE_INCIDENT_CONTROL_HOLD"
    assert evaluate_change_incident_control(change(unapproved_changes=1)).status == "CHANGE_INCIDENT_CONTROL_HOLD"
    assert evaluate_change_incident_control(change(unresolved_critical_incidents=1)).status == "CHANGE_INCIDENT_CONTROL_HOLD"


def test_stage39_aggregates_new_stages_and_prior_blockers():
    result = evaluate_governance_readiness(governance())
    assert result.status == "PAPER_OPERATIONAL_REVIEW_HANDOFF_ONLY"
    assert result.live_arming_permitted is False
    assert evaluate_governance_readiness(governance(stage35_status="HOLD")).status == "GOVERNANCE_READINESS_HOLD"
    assert evaluate_governance_readiness(governance(credentials_revoked_and_reviewed=False)).status == "GOVERNANCE_READINESS_HOLD"
    assert evaluate_governance_readiness(governance(risk_reward_policy_reconciled=False)).status == "GOVERNANCE_READINESS_HOLD"


def test_all_stage36_to_39_assessments_keep_live_arming_disabled():
    results = (evaluate_portfolio_risk(portfolio()), evaluate_ledger_reconciliation(ledger()),
               evaluate_change_incident_control(change()), evaluate_governance_readiness(governance()))
    assert all(item.live_arming_permitted is False for item in results)
