"""Focused tests for offline production-hardening Stages 20–23."""
from dataclasses import replace
from core.governance.production_hardening_stages20_23 import (
    SupplyChainEvidence, RestoreDrillEvidence, IncidentDrillEvidence,
    FinalReadinessEvidence, evaluate_supply_chain, evaluate_restore_drill,
    evaluate_incident_drill, evaluate_final_readiness,
)

def supply(**kw):
    d=dict(source_commit="a"*64,build_run_ref="build:1",builder_identity_ref="builder:1",
           dependency_lock_ref="lock:1",dependency_scan_ref="scan:1",artifact_digest="b"*64,
           provenance_ref="provenance:1",independent_review_ref="review:1",
           build_reproducible=True,critical_vulnerabilities=0,
           evaluated_at_utc="2026-11-08T11:00:00Z",evidence_valid_until_utc="2026-12-08T11:00:00Z")
    d.update(kw); return SupplyChainEvidence(**d)

def restore(**kw):
    d=dict(backup_ref="backup:1",backup_digest="a"*64,backup_created_at_utc="2026-11-08T09:00:00Z",
           restore_started_at_utc="2026-11-08T10:00:00Z",restore_completed_at_utc="2026-11-08T10:05:00Z",
           restored_state_digest="b"*64,expected_state_digest="b"*64,
           independent_restore_review_ref="review:restore",recovery_point_objective_seconds=60,
           recovery_time_objective_seconds=600,measured_data_loss_seconds=10,
           measured_restore_seconds=300,integrity_check_passed=True)
    d.update(kw); return RestoreDrillEvidence(**d)

def incident(**kw):
    d=dict(incident_id="drill-01",severity="SEV2",declared_at_utc="2026-11-08T10:00:00Z",
           contained_at_utc="2026-11-08T10:02:00Z",closed_at_utc="2026-11-08T10:30:00Z",
           incident_timeline_ref="timeline:1",escalation_record_ref="escalation:1",
           kill_switch_drill_ref="kill-switch:1",credential_containment_ref="credential:1",
           postmortem_ref="postmortem:1",independent_observer_ref="observer:1",
           unauthorized_actions=0,containment_sla_seconds=300,
           measured_containment_seconds=120,corrective_actions_open=0)
    d.update(kw); return IncidentDrillEvidence(**d)

def readiness(**kw):
    d=dict(stage20_status="SUPPLY_CHAIN_EVIDENCE_COMPLETE_UNVERIFIED",
           stage21_status="RESTORE_DRILL_EVIDENCE_COMPLETE_UNVERIFIED",
           stage22_status="INCIDENT_DRILL_EVIDENCE_COMPLETE_UNVERIFIED",
           stage19_status="READY_FOR_CONTROLLED_TESTNET_REVIEW",
           full_regression_passed=True,stage4_lineage_verified=True,
           oos_independent_review_ref="oos:review",venue_economics_review_ref="venue:review",
           credential_revocation_review_ref="credential:review",
           operational_owner_approval_ref="owner:approval",
           release_candidate_digest="c"*64,reviewed_candidate_digest="c"*64,
           open_critical_findings=0)
    d.update(kw); return FinalReadinessEvidence(**d)

def test_stage20_complete_evidence_remains_unauthenticated():
    r=evaluate_supply_chain(supply())
    assert r.status=="SUPPLY_CHAIN_EVIDENCE_COMPLETE_UNVERIFIED"
    assert not r.live_arming_permitted

def test_stage20_blocks_expired_nonreproducible_and_vulnerable_builds():
    assert evaluate_supply_chain(supply(evidence_valid_until_utc="2026-11-08T10:00:00Z")).status=="HOLD"
    assert evaluate_supply_chain(supply(build_reproducible=False)).status=="HOLD"
    assert evaluate_supply_chain(supply(critical_vulnerabilities=1)).status=="HOLD"

def test_stage21_restore_drill_requires_exact_state_and_objectives():
    assert evaluate_restore_drill(restore()).status=="RESTORE_DRILL_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_restore_drill(restore(restored_state_digest="d"*64)).status=="RESTORE_DRILL_FAILED"
    assert evaluate_restore_drill(restore(measured_restore_seconds=700)).status=="RESTORE_DRILL_FAILED"

def test_stage21_blocks_bad_order_or_integrity():
    assert evaluate_restore_drill(restore(integrity_check_passed=False)).status=="RESTORE_DRILL_FAILED"
    assert evaluate_restore_drill(restore(restore_started_at_utc="2026-11-08T08:00:00Z")).status=="RESTORE_DRILL_FAILED"

def test_stage22_incident_drill_is_unverified_and_non_live():
    r=evaluate_incident_drill(incident())
    assert r.status=="INCIDENT_DRILL_EVIDENCE_COMPLETE_UNVERIFIED"
    assert not r.live_arming_permitted

def test_stage22_unauthorized_action_or_sla_breach_fails():
    assert evaluate_incident_drill(incident(unauthorized_actions=1)).status=="INCIDENT_DRILL_FAILED"
    assert evaluate_incident_drill(incident(measured_containment_seconds=400)).status=="INCIDENT_DRILL_FAILED"

def test_stage22_open_corrective_action_fails():
    assert evaluate_incident_drill(incident(corrective_actions_open=1)).status=="INCIDENT_DRILL_FAILED"

def test_stage23_full_gate_is_review_only():
    r=evaluate_final_readiness(readiness())
    assert r.status=="READY_FOR_INDEPENDENT_RELEASE_REVIEW"
    assert not r.live_arming_permitted

def test_stage23_holds_for_lineage_regression_or_digest_mismatch():
    assert evaluate_final_readiness(readiness(stage4_lineage_verified=False)).status=="HOLD"
    assert evaluate_final_readiness(readiness(full_regression_passed=False)).status=="HOLD"
    assert evaluate_final_readiness(readiness(reviewed_candidate_digest="d"*64)).status=="HOLD"

def test_stage23_holds_for_critical_findings_and_missing_oos_review():
    assert evaluate_final_readiness(readiness(open_critical_findings=1)).status=="HOLD"
    assert evaluate_final_readiness(readiness(oos_independent_review_ref="")).status=="HOLD"
