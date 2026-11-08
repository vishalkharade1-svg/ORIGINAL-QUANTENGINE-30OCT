"""Focused tests for Stages 48–51 evidence-only validators."""
from core.governance.production_hardening_stages48_51 import (
    CapacityResilienceEvidence, ModelChangeEvidence, FinancialControlEvidence, ReleaseDecisionEvidence,
    evaluate_capacity_resilience, evaluate_model_change, evaluate_financial_controls, evaluate_release_decision,
)


def capacity(**kw):
    d=dict(service="paper-engine",source_commit="a"*40,workload_digest="b"*64,
        test_report_ref="capacity:report",environment_attestation_ref="capacity:env",
        failover_drill_ref="capacity:failover",recovery_report_ref="capacity:recovery",
        independent_review_ref="capacity:review",tested_at_utc="2026-11-08T09:00:00Z",
        requests_per_second=1200,required_requests_per_second=1000,p95_latency_ms=80,
        p95_latency_limit_ms=100,p99_latency_ms=150,p99_latency_limit_ms=200,
        error_rate=0.001,error_rate_limit=0.01,recovery_seconds=30,recovery_limit_seconds=60,
        saturation_events=0,dropped_requests=0,test_environment_isolated=True,
        failover_tested=True,recovery_verified=True)
    d.update(kw);return CapacityResilienceEvidence(**d)


def model(**kw):
    d=dict(strategy="paper-alpha",source_commit="a"*40,model_artifact_digest="b"*64,
        training_dataset_digest="c"*64,evaluation_dataset_digest="d"*64,
        evaluation_report_ref="model:evaluation",data_lineage_ref="model:lineage",
        leakage_review_ref="model:leakage",approval_record_ref="model:approval",
        rollback_record_ref="model:rollback",independent_validation_ref="model:independent",
        training_end_utc="2026-10-01T00:00:00Z",evaluation_start_utc="2026-10-02T00:00:00Z",
        prior_model_digest="e"*64,performance_degradation=0.01,maximum_allowed_degradation=0.03,
        leakage_findings=0,unapproved_features=0,reproducibility_verified=True,
        chronological_split_verified=True,rollback_tested=True,approval_complete=True)
    d.update(kw);return ModelChangeEvidence(**d)


def financial(**kw):
    d=dict(entity="paper-fund",source_commit="a"*40,accounting_period="2026-10",
        ledger_snapshot_digest="b"*64,bank_or_custody_statement_digest="c"*64,
        reconciliation_report_ref="finance:recon",fee_schedule_ref="finance:fees",
        valuation_policy_ref="finance:valuation",exception_register_ref="finance:exceptions",
        independent_reviewer_ref="finance:reviewer",closed_at_utc="2026-11-08T10:00:00Z",
        ledger_rows=100,matched_rows=100,unexplained_cash_difference=0.0,
        unexplained_position_difference=0.0,unexplained_fee_difference=0.0,
        open_critical_exceptions=0,stale_prices=0,duplicate_entries=0,
        reconciliation_independent=True,valuation_policy_applied=True,period_locked=True)
    d.update(kw);return FinancialControlEvidence(**d)


def release(**kw):
    d=dict(release_candidate="paper-release-rc1",source_commit="a"*40,
        build_artifact_digest="b"*64,test_evidence_ref="release:tests",
        security_review_ref="release:security",risk_assessment_ref="release:risk",
        operations_review_ref="release:ops",compliance_review_ref="release:compliance",
        decision_record_ref="release:decision",dissent_record_ref="release:dissent",
        rollback_plan_ref="release:rollback",independent_chair_review_ref="release:chair",
        decided_at_utc="2026-11-08T10:00:00Z",required_approvals=4,recorded_approvals=4,
        unresolved_blockers=0,unresolved_critical_risks=0,material_dissent_count=0,
        paper_only_scope=True,rollback_plan_tested=True,evidence_snapshot_frozen=True,
        decision_is_authorization=False)
    d.update(kw);return ReleaseDecisionEvidence(**d)


def test_stage48_capacity_latency_error_and_recovery_gates():
    assert evaluate_capacity_resilience(capacity()).status == "CAPACITY_RESILIENCE_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_capacity_resilience(capacity(p99_latency_ms=250)).status == "CAPACITY_RESILIENCE_HOLD"
    assert evaluate_capacity_resilience(capacity(error_rate=0.02)).status == "CAPACITY_RESILIENCE_HOLD"
    assert evaluate_capacity_resilience(capacity(failover_tested=False)).status == "CAPACITY_RESILIENCE_HOLD"


def test_stage49_model_change_chronology_leakage_and_rollback_gates():
    assert evaluate_model_change(model()).status == "MODEL_CHANGE_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_model_change(model(evaluation_start_utc="2026-09-30T00:00:00Z")).status == "MODEL_CHANGE_HOLD"
    assert evaluate_model_change(model(leakage_findings=1)).status == "MODEL_CHANGE_HOLD"
    assert evaluate_model_change(model(rollback_tested=False)).status == "MODEL_CHANGE_HOLD"


def test_stage50_financial_reconciliation_exception_and_period_lock_gates():
    assert evaluate_financial_controls(financial()).status == "FINANCIAL_CONTROLS_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_financial_controls(financial(unexplained_cash_difference=0.01)).status == "FINANCIAL_CONTROLS_HOLD"
    assert evaluate_financial_controls(financial(stale_prices=1)).status == "FINANCIAL_CONTROLS_HOLD"
    assert evaluate_financial_controls(financial(period_locked=False)).status == "FINANCIAL_CONTROLS_HOLD"


def test_stage51_release_record_is_never_an_authorization():
    assert evaluate_release_decision(release()).status == "RELEASE_DECISION_RECORDED_NOT_AUTHORIZED"
    assert evaluate_release_decision(release(recorded_approvals=2)).status == "RELEASE_DECISION_HOLD"
    assert evaluate_release_decision(release(unresolved_blockers=1)).status == "RELEASE_DECISION_HOLD"
    assert evaluate_release_decision(release(decision_is_authorization=True)).status == "RELEASE_DECISION_HOLD"


def test_all_stage48_to_51_assessments_keep_live_arming_disabled():
    results=(evaluate_capacity_resilience(capacity()),evaluate_model_change(model()),
             evaluate_financial_controls(financial()),evaluate_release_decision(release()))
    assert all(x.live_arming_permitted is False for x in results)
