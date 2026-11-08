"""Focused tests for Stages 44–47 offline evidence gates."""
from core.governance.production_hardening_stages44_47 import (
    SupplyChainEvidence, ConfigurationEvidence, IncidentResponseEvidence, ThirdPartyRiskEvidence,
    evaluate_supply_chain, evaluate_configuration, evaluate_incident_response, evaluate_third_party_risk,
)


def supply(**kw):
    d = dict(component="paper-engine", source_commit="a"*40, source_tree_digest="b"*64,
        dependency_lock_digest="c"*64, sbom_digest="d"*64, build_attestation_ref="build:1",
        builder_identity_ref="builder:ci", signature_verification_ref="sig:1",
        independent_review_ref="review:supply", built_at_utc="2026-11-07T10:00:00Z",
        source_matches_build=True, build_reproducible=True, signature_valid=True,
        dependencies_pinned=True, sbom_complete=True, critical_vulnerabilities=0,
        high_vulnerabilities=0, unapproved_components=0)
    d.update(kw)
    return SupplyChainEvidence(**d)


def config(**kw):
    d = dict(system="paper-engine", source_commit="a"*40, observed_config_digest="b"*64,
        approved_baseline_digest="b"*64, config_inventory_ref="config:inventory",
        change_approval_ref="change:approval", policy_review_ref="policy:review",
        rollback_test_ref="rollback:test", independent_review_ref="review:config",
        reviewed_at_utc="2026-11-08T10:00:00Z", environment="paper",
        drifted_settings=0, unapproved_changes=0, embedded_secret_findings=0,
        policy_exceptions=0, rollback_tested=True, baseline_approved=True,
        environment_isolated=True)
    d.update(kw)
    return ConfigurationEvidence(**d)


def incident(**kw):
    d = dict(service="paper-engine", source_commit="a"*40, incident_playbook_ref="ir:playbook",
        on_call_roster_ref="ir:oncall", exercise_or_incident_report_ref="ir:exercise",
        evidence_preservation_ref="ir:evidence", communications_record_ref="ir:comms",
        postmortem_ref="ir:postmortem", independent_review_ref="ir:review",
        detected_at_utc="2026-11-07T10:00:00Z", acknowledged_at_utc="2026-11-07T10:01:00Z",
        contained_at_utc="2026-11-07T10:10:00Z", maximum_acknowledgement_seconds=120,
        maximum_containment_seconds=900, evidence_preserved=True, escalation_tested=True,
        stakeholder_communications_complete=True, corrective_actions_tracked=True,
        unresolved_critical_findings=0)
    d.update(kw)
    return IncidentResponseEvidence(**d)


def third_party(**kw):
    d = dict(service="paper-engine", source_commit="a"*40, vendor_inventory_digest="b"*64,
        critical_vendor_register_ref="vendor:register", due_diligence_report_ref="vendor:dd",
        contractual_controls_ref="vendor:contracts", service_level_report_ref="vendor:sla",
        exit_and_portability_plan_ref="vendor:exit", independent_risk_review_ref="vendor:review",
        reviewed_at_utc="2026-11-08T10:00:00Z", critical_vendors_total=5,
        critical_vendors_reviewed=5, overdue_assessments=0, unresolved_critical_findings=0,
        unapproved_subprocessors=0, tested_exit_plan=True, service_levels_met=True,
        concentration_risk_accepted=True, material_incidents_disclosed=True)
    d.update(kw)
    return ThirdPartyRiskEvidence(**d)


def test_stage44_supply_chain_provenance_and_vulnerability_gates():
    assert evaluate_supply_chain(supply()).status == "SUPPLY_CHAIN_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_supply_chain(supply(signature_valid=False)).status == "SUPPLY_CHAIN_HOLD"
    assert evaluate_supply_chain(supply(critical_vulnerabilities=1)).status == "SUPPLY_CHAIN_HOLD"
    assert evaluate_supply_chain(supply(dependencies_pinned=False)).status == "SUPPLY_CHAIN_HOLD"


def test_stage45_configuration_drift_secrets_and_rollback_gates():
    assert evaluate_configuration(config()).status == "CONFIGURATION_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_configuration(config(unapproved_changes=1)).status == "CONFIGURATION_HOLD"
    assert evaluate_configuration(config(embedded_secret_findings=1)).status == "CONFIGURATION_HOLD"
    assert evaluate_configuration(config(rollback_tested=False)).status == "CONFIGURATION_HOLD"


def test_stage46_incident_response_timing_and_evidence_gates():
    assert evaluate_incident_response(incident()).status == "INCIDENT_RESPONSE_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_incident_response(incident(acknowledged_at_utc="2026-11-07T10:05:00Z")).status == "INCIDENT_RESPONSE_HOLD"
    assert evaluate_incident_response(incident(evidence_preserved=False)).status == "INCIDENT_RESPONSE_HOLD"
    assert evaluate_incident_response(incident(unresolved_critical_findings=1)).status == "INCIDENT_RESPONSE_HOLD"


def test_stage47_third_party_due_diligence_and_exit_gates():
    assert evaluate_third_party_risk(third_party()).status == "THIRD_PARTY_RISK_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_third_party_risk(third_party(critical_vendors_reviewed=4)).status == "THIRD_PARTY_RISK_HOLD"
    assert evaluate_third_party_risk(third_party(tested_exit_plan=False)).status == "THIRD_PARTY_RISK_HOLD"
    assert evaluate_third_party_risk(third_party(unapproved_subprocessors=1)).status == "THIRD_PARTY_RISK_HOLD"


def test_all_stage44_to_47_assessments_keep_live_arming_disabled():
    results = (evaluate_supply_chain(supply()), evaluate_configuration(config()),
               evaluate_incident_response(incident()), evaluate_third_party_risk(third_party()))
    assert all(item.live_arming_permitted is False for item in results)
