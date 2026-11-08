from dataclasses import replace
from core.governance.production_hardening_stages84_87 import (
    StrategyGovernance, MonitoringGovernance, FinancialReconciliation,
    ReleaseRollbackReadiness, evaluate_strategy_governance,
    evaluate_monitoring_governance, evaluate_financial_reconciliation,
    evaluate_release_rollback_readiness,
)

TS = "2026-11-09T10:00:00Z"

def strategy():
    return StrategyGovernance("assessment","strategy-spec","a"*64,"approval","prereg","research-boundary",
        "change-register",TS,3,3,3,0,True,True)

def monitoring():
    return MonitoringGovernance("assessment","catalog","thresholds","routes","escalation","dry-run",TS,
        12,12,12,12,0,0,True,True)

def finance():
    return FinancialReconciliation("assessment","ledger-snapshot","counterparty-statement","population",
        "break-register","independent-review",TS,100,100,2,2,0,0,True)

def release():
    return ReleaseRollbackReadiness("assessment","artifact","a"*40,"manifest","tests","approval",
        "rollback-plan","tabletop",TS,0,15,15,6,6,True,True)

def test_all_stages_complete_unverified_and_never_arm():
    results = [evaluate_strategy_governance(strategy()), evaluate_monitoring_governance(monitoring()),
        evaluate_financial_reconciliation(finance()), evaluate_release_rollback_readiness(release())]
    assert [x.stage for x in results] == [84,85,86,87]
    assert all(x.status.endswith("COMPLETE_UNVERIFIED") for x in results)
    assert all(x.live_arming_permitted is False for x in results)

def test_strategy_requires_hash_and_full_approval():
    result = evaluate_strategy_governance(replace(strategy(), strategy_hash="bad", changes_approved=2))
    assert result.status == "STRATEGY_GOVERNANCE_HOLD" and len(result.reasons) >= 2

def test_monitoring_requires_full_coverage_and_owned_alerts():
    result = evaluate_monitoring_governance(replace(monitoring(), controls_with_routes=11, unowned_critical_alerts=1))
    assert result.status == "MONITORING_GOVERNANCE_HOLD" and len(result.reasons) >= 2

def test_financial_reconciliation_requires_matched_population_and_resolved_breaks():
    result = evaluate_financial_reconciliation(replace(finance(), transactions_matched=99, unresolved_value_breaks=1))
    assert result.status == "FINANCIAL_RECONCILIATION_HOLD" and len(result.reasons) >= 2

def test_release_requires_no_blockers_and_complete_rollback_tabletop():
    result = evaluate_release_rollback_readiness(replace(release(), release_blockers=1, rollback_steps_documented=5))
    assert result.status == "RELEASE_ROLLBACK_HOLD" and len(result.reasons) >= 2

def test_naive_timestamp_is_rejected():
    result = evaluate_strategy_governance(replace(strategy(), assessed_at="2026-11-09T10:00:00"))
    assert result.status == "STRATEGY_GOVERNANCE_HOLD"
