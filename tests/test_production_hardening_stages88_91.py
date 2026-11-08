from dataclasses import replace
from core.governance.production_hardening_stages88_91 import (
    DataQualityGovernance, CapacityGovernance, DependencyResilience, AuditLogIntegrity,
    evaluate_data_quality, evaluate_capacity_governance, evaluate_dependency_resilience,
    evaluate_audit_log_integrity,
)

TS = "2026-11-09T10:00:00Z"

def data_quality():
    return DataQualityGovernance("assessment","sources","schemas","quality","freshness","exceptions",TS,
        4,4,4,1000,1000,0,0,0,True)

def capacity():
    return CapacityGovernance("assessment","inventory","forecast","headroom","stress","queues","recovery",TS,
        8,8,8,12,12,0,0,0,True)

def dependencies():
    return DependencyResilience("assessment","inventory","criticality","assurance","continuity","concentration",
        "remediation",TS,20,20,5,5,5,0,0,True)

def audit():
    return AuditLogIntegrity("assessment","catalog","coverage","append-only","checkpoints","retention",
        "time-sync","incidents",TS,9,9,24,24,0,0,0,0,True)

def test_all_four_stages_complete_unverified_and_never_arm():
    results = [evaluate_data_quality(data_quality()), evaluate_capacity_governance(capacity()),
        evaluate_dependency_resilience(dependencies()), evaluate_audit_log_integrity(audit())]
    assert [x.stage for x in results] == [88,89,90,91]
    assert all(x.status.endswith("COMPLETE_UNVERIFIED") for x in results)
    assert all(x.live_arming_permitted is False for x in results)

def test_data_quality_holds_on_stale_feed_and_missing_validation():
    result = evaluate_data_quality(replace(data_quality(), sources_with_schema_validation=3, stale_critical_feeds=1))
    assert result.status == "DATA_QUALITY_HOLD" and len(result.reasons) >= 2

def test_capacity_holds_on_headroom_breach_and_unbounded_queue():
    result = evaluate_capacity_governance(replace(capacity(), headroom_breaches=1, unbounded_queues=1))
    assert result.status == "CAPACITY_GOVERNANCE_HOLD" and len(result.reasons) >= 2

def test_dependency_holds_on_unassured_critical_vendor():
    result = evaluate_dependency_resilience(replace(dependencies(), critical_dependencies_with_assurance=4))
    assert result.status == "DEPENDENCY_RESILIENCE_HOLD"

def test_audit_integrity_holds_on_uncovered_events_and_retention_gaps():
    result = evaluate_audit_log_integrity(replace(audit(), event_classes_logged=8, retention_gaps=1))
    assert result.status == "AUDIT_LOG_INTEGRITY_HOLD" and len(result.reasons) >= 2

def test_invalid_count_types_fail_closed_without_exception():
    result = evaluate_capacity_governance(replace(capacity(), resources_in_scope=True))
    assert result.status == "CAPACITY_GOVERNANCE_HOLD"
