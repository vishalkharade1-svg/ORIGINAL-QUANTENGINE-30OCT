from dataclasses import replace
from core.governance.production_hardening_stages92_95 import (
    ContinuityReadiness, TestAssurance, OperationalHandoff, SafetyInterlockAssurance,
    evaluate_continuity_readiness, evaluate_test_assurance,
    evaluate_operational_handoff, evaluate_safety_interlocks,
)

TS = "2026-11-09T10:00:00Z"

def continuity():
    return ContinuityReadiness("assessment","criticality","dependency-map","rto-rpo","backup","exercise",
        "communications",TS,6,6,6,6,0,0,True,True)

def tests():
    return TestAssurance("assessment","inventory","traceability","replay","property","mutation","defects",TS,
        40,40,120,120,8,8,30,30,0,True)

def handoff():
    return OperationalHandoff("assessment","runbooks","owners","escalations","training","acceptance",
        "maintenance",TS,10,10,10,4,4,0,0,True,True)

def interlocks():
    return SafetyInterlockAssurance("assessment","requirements","design","fail-closed","stale-tests",
        "bypass-analysis","independent-review",TS,5,5,5,12,12,0,0,True)

def test_all_stages_complete_unverified_and_never_arm():
    results = [evaluate_continuity_readiness(continuity()), evaluate_test_assurance(tests()),
        evaluate_operational_handoff(handoff()), evaluate_safety_interlocks(interlocks())]
    assert [x.stage for x in results] == [92,93,94,95]
    assert all(x.status.endswith("COMPLETE_UNVERIFIED") for x in results)
    assert all(x.live_arming_permitted is False for x in results)

def test_continuity_holds_on_missing_recovery_objective():
    result = evaluate_continuity_readiness(replace(continuity(), services_with_rto_rpo=5))
    assert result.status == "CONTINUITY_READINESS_HOLD"

def test_test_assurance_holds_on_uncovered_requirement_and_critical_defect():
    result = evaluate_test_assurance(replace(tests(), requirements_with_tests=39, unresolved_critical_defects=1))
    assert result.status == "TEST_ASSURANCE_HOLD" and len(result.reasons) >= 2

def test_handoff_holds_on_unaccepted_handoff_and_missing_owner():
    result = evaluate_operational_handoff(replace(handoff(), services_with_named_owners=9, unaccepted_handoffs=1))
    assert result.status == "OPERATIONAL_HANDOFF_HOLD" and len(result.reasons) >= 2

def test_interlocks_hold_on_bypass_and_unrejected_stale_evidence():
    result = evaluate_safety_interlocks(replace(interlocks(), bypass_paths_identified=1, stale_evidence_cases_rejected=11))
    assert result.status == "SAFETY_INTERLOCK_HOLD" and len(result.reasons) >= 2

def test_invalid_count_types_fail_closed():
    result = evaluate_safety_interlocks(replace(interlocks(), interlocks_in_scope=True))
    assert result.status == "SAFETY_INTERLOCK_HOLD"
