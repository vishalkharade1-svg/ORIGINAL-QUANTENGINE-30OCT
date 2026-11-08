from dataclasses import replace
from core.governance.production_hardening_stages80_83 import (
    PrivacyGovernance, AccessGovernance, IncidentReadiness, ChangeControl,
    evaluate_privacy_governance, evaluate_access_governance,
    evaluate_incident_readiness, evaluate_change_control,
)

def privacy():
    return PrivacyGovernance("assessment","inventory","purposes","minimization","retention","impact",
        "2026-11-09T10:00:00Z",8,8,0,0,0,True,True)

def access():
    return AccessGovernance("assessment","identities","roles","privileged-review","segregation","certification",
        "2026-11-09T10:00:00Z",20,20,4,4,0,0,0,True)

def incident():
    return IncidentReadiness("assessment","plan","severity","roster","communications","exercise","lessons",
        "2026-11-09T10:00:00Z",5,5,8,8,0,0,0,True,True)

def change():
    return ChangeControl("assessment","policy","register","impact","tests","approvals","rollback",
        "2026-11-09T10:00:00Z",7,7,7,7,7,0,0,True)

def test_all_complete_are_unverified_and_never_arm():
    results=[evaluate_privacy_governance(privacy()),evaluate_access_governance(access()),
             evaluate_incident_readiness(incident()),evaluate_change_control(change())]
    assert [x.stage for x in results]==[80,81,82,83]
    assert all(x.status.endswith("COMPLETE_UNVERIFIED") for x in results)
    assert all(x.live_arming_permitted is False for x in results)

def test_privacy_requires_purpose_and_zero_excess_data():
    result=evaluate_privacy_governance(replace(privacy(),data_elements_with_purpose=7,unnecessary_elements_retained=1))
    assert result.status=="PRIVACY_GOVERNANCE_HOLD" and len(result.reasons)>=2

def test_access_requires_complete_reviews_and_zero_orphans():
    result=evaluate_access_governance(replace(access(),privileged_identities_reviewed=3,orphaned_accounts=1))
    assert result.status=="ACCESS_GOVERNANCE_HOLD" and len(result.reasons)>=2

def test_incident_readiness_requires_full_exercise_and_owned_lessons():
    result=evaluate_incident_readiness(replace(incident(),scenarios_exercised=4,overdue_lessons=1))
    assert result.status=="INCIDENT_READINESS_HOLD" and len(result.reasons)>=2

def test_change_control_requires_approval_and_rollback_evidence():
    result=evaluate_change_control(replace(change(),changes_with_required_approval=6,unauthorized_changes=1))
    assert result.status=="CHANGE_CONTROL_HOLD" and len(result.reasons)>=2
