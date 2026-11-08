"""Focused tests for Stages 40–43 offline evidence gates."""
from core.governance.production_hardening_stages40_43 import (
    DataGovernanceEvidence, DisasterRecoveryEvidence, AccessControlEvidence, AuditEvidence,
    evaluate_data_governance, evaluate_disaster_recovery, evaluate_access_control,
    evaluate_audit_evidence,
)


def data(**kw):
    d = dict(dataset_ref="dataset:paper", source_commit="a"*40, dataset_digest="b"*64,
        schema_digest="c"*64, lineage_manifest_ref="lineage:1", data_owner_ref="owner:data",
        classification="INTERNAL", permitted_use_ref="use:paper",
        retention_policy_ref="retention:1", deletion_attestation_ref="deletion:1",
        quality_report_ref="quality:1", privacy_review_ref="privacy:1",
        consent_or_lawful_basis_ref="basis:1", collected_at_utc="2026-11-01T00:00:00Z",
        reviewed_at_utc="2026-11-02T00:00:00Z", required_fields_present=True,
        schema_compatible=True, provenance_complete=True, personal_data_minimized=True,
        retention_within_policy=True, deletion_requests_satisfied=True,
        unresolved_quality_critical=0, unauthorized_data_sources=0)
    d.update(kw)
    return DataGovernanceEvidence(**d)


def recovery(**kw):
    d = dict(service="paper-engine", source_commit="a"*40, recovery_plan_ref="dr:plan",
        backup_catalog_ref="backup:catalog", backup_digest="b"*64,
        restore_test_report_ref="restore:test", failover_test_report_ref="failover:test",
        dependency_map_ref="deps:map", independent_recovery_review_ref="review:dr",
        recovery_point_objective_seconds=300, measured_data_loss_seconds=120,
        recovery_time_objective_seconds=1800, measured_recovery_seconds=900,
        backup_age_seconds=600, maximum_backup_age_seconds=3600,
        restore_success=True, failover_success=True, backup_integrity_verified=True,
        dependencies_recovered=True, rollback_path_tested=True,
        unresolved_critical_recovery_findings=0, last_drill_at_utc="2026-11-07T10:00:00Z")
    d.update(kw)
    return DisasterRecoveryEvidence(**d)


def access(**kw):
    d = dict(system="paper-engine", source_commit="a"*40, access_inventory_digest="b"*64,
        identity_provider_review_ref="idp:review", privileged_access_review_ref="priv:review",
        service_account_inventory_ref="svc:inventory", joiner_mover_leaver_report_ref="jml:report",
        separation_of_duties_matrix_ref="sod:matrix", independent_security_review_ref="review:security",
        reviewed_at_utc="2026-11-08T10:00:00Z", mfa_coverage_percent=100.0,
        mfa_minimum_percent=99.0, privileged_accounts_reviewed=12,
        privileged_accounts_total=12, stale_accounts=0, orphaned_service_accounts=0,
        shared_human_accounts=0, excessive_privilege_findings=0, unapproved_access_changes=0,
        break_glass_accounts_tested=True, break_glass_use_audited=True,
        dual_control_for_critical_actions=True)
    d.update(kw)
    return AccessControlEvidence(**d)


def audit(**kw):
    d = dict(system="paper-engine", source_commit="a"*40, audit_bundle_digest="b"*64,
        event_schema_ref="schema:audit", immutable_storage_ref="storage:immutable",
        retention_schedule_ref="retention:audit", time_sync_evidence_ref="clock:report",
        independent_audit_review_ref="review:audit", period_start_utc="2026-11-01T00:00:00Z",
        period_end_utc="2026-11-02T00:00:00Z", generated_at_utc="2026-11-02T01:00:00Z",
        required_event_coverage_percent=100.0, minimum_event_coverage_percent=99.9,
        tamper_check_passed=True, retention_lock_enabled=True,
        access_to_audit_logs_restricted=True, privileged_events_attributed=True,
        event_sequence_gaps=0, missing_critical_events=0, unexplained_clock_skew_ms=0,
        unresolved_audit_findings=0)
    d.update(kw)
    return AuditEvidence(**d)


def test_stage40_enforces_dataset_lineage_privacy_retention_and_quality():
    assert evaluate_data_governance(data()).status == "DATA_GOVERNANCE_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_data_governance(data(classification="SECRET")).status == "DATA_GOVERNANCE_HOLD"
    assert evaluate_data_governance(data(unauthorized_data_sources=1)).status == "DATA_GOVERNANCE_HOLD"
    assert evaluate_data_governance(data(deletion_requests_satisfied=False)).status == "DATA_GOVERNANCE_HOLD"


def test_stage41_enforces_restore_failover_and_rpo_rto_targets():
    assert evaluate_disaster_recovery(recovery()).status == "DISASTER_RECOVERY_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_disaster_recovery(recovery(measured_recovery_seconds=2400)).status == "DISASTER_RECOVERY_HOLD"
    assert evaluate_disaster_recovery(recovery(backup_integrity_verified=False)).status == "DISASTER_RECOVERY_HOLD"
    assert evaluate_disaster_recovery(recovery(unresolved_critical_recovery_findings=1)).status == "DISASTER_RECOVERY_HOLD"


def test_stage42_enforces_privileged_access_mfa_and_separation_of_duties():
    assert evaluate_access_control(access()).status == "ACCESS_CONTROL_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_access_control(access(mfa_coverage_percent=80.0)).status == "ACCESS_CONTROL_HOLD"
    assert evaluate_access_control(access(privileged_accounts_reviewed=10)).status == "ACCESS_CONTROL_HOLD"
    assert evaluate_access_control(access(orphaned_service_accounts=1)).status == "ACCESS_CONTROL_HOLD"


def test_stage43_enforces_audit_immutability_coverage_and_completeness():
    assert evaluate_audit_evidence(audit()).status == "AUDIT_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_audit_evidence(audit(required_event_coverage_percent=90.0)).status == "AUDIT_EVIDENCE_HOLD"
    assert evaluate_audit_evidence(audit(tamper_check_passed=False)).status == "AUDIT_EVIDENCE_HOLD"
    assert evaluate_audit_evidence(audit(missing_critical_events=1)).status == "AUDIT_EVIDENCE_HOLD"


def test_all_stage40_to_43_assessments_keep_live_arming_disabled():
    results = (evaluate_data_governance(data()), evaluate_disaster_recovery(recovery()),
               evaluate_access_control(access()), evaluate_audit_evidence(audit()))
    assert all(item.live_arming_permitted is False for item in results)
