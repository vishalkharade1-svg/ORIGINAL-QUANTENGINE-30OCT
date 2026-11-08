"""Focused tests for Stages 24–27 offline governance gates."""
from dataclasses import replace
from core.governance.production_hardening_stages24_27 import (
    CredentialClosureEvidence, RepositoryIntegrityEvidence, Classification,
    GovernanceInventoryEvidence, AuditFinding, AuditCoverageEvidence,
    evaluate_credential_closure, evaluate_repository_integrity,
    evaluate_governance_inventory, evaluate_audit_coverage,
)

def credential(**kw):
    d=dict(provider_revocation_confirmed=True,provider_case_ref="case:1",
      revocation_effective_at_utc="2026-11-08T10:00:00Z",
      replacement_key_testnet_only=True,least_privilege_review_ref="review:least",
      secret_scan_ref="scan:1",history_exposure_decision="PURGED_AND_VERIFIED",
      history_remediation_ref="history:1",independent_security_review_ref="security:1")
    d.update(kw); return CredentialClosureEvidence(**d)

def repository(**kw):
    d=dict(source_commit="a"*64,clean_tree_attested=True,uncommitted_path_count=0,
      index_lock_present=False,canonical_ancestor_verified=True,
      canonical_ancestor_commit="b"*64,line_ending_policy_ref="policy:1",
      lf_fingerprint="c"*64,crlf_fingerprint="c"*64,
      fingerprint_reproducible=True,independent_repo_review_ref="review:repo")
    d.update(kw); return RepositoryIntegrityEvidence(**d)

def inventory(**kw):
    d=dict(canonical_dependency_manifest="requirements.lock",
      dependency_manifest_digest="a"*64,compared_manifest_digests=("a"*64,),
      dependency_comparison_ref="compare:1",dependency_drift_resolved=True,
      classifications=(Classification("core/x.py","ACTIVE","review:x"),),
      required_classification_paths=("core/x.py",),independent_review_ref="review:inventory")
    d.update(kw); return GovernanceInventoryEvidence(**d)

DOMAINS=("indicators","order_flow","wyckoff_smc","options","backtest_bias",
"paper_realism","concurrency_async","performance","reconciliation",
"protective_orders","exception_handling","execution_bypass","stub_triage","dependency_drift")

def audit(**kw):
    d=dict(findings=tuple(AuditFinding(x,"VERIFIED_PASS",f"evidence:{x}") for x in DOMAINS),
      independent_audit_review_ref="review:audit",scope_commit="d"*64)
    d.update(kw); return AuditCoverageEvidence(**d)

def test_stage24_requires_external_revocation_and_history_disposition():
    assert evaluate_credential_closure(credential()).status=="CREDENTIAL_CLOSURE_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_credential_closure(credential(provider_revocation_confirmed=False)).status=="SECURITY_HOLD"
    assert evaluate_credential_closure(credential(history_exposure_decision="UNKNOWN")).status=="SECURITY_HOLD"

def test_stage25_requires_clean_tree_lineage_and_reproducible_hash():
    assert evaluate_repository_integrity(repository()).status=="REPOSITORY_INTEGRITY_EVIDENCE_COMPLETE_UNVERIFIED"
    assert evaluate_repository_integrity(repository(uncommitted_path_count=1)).status=="REPOSITORY_INTEGRITY_HOLD"
    assert evaluate_repository_integrity(repository(index_lock_present=True)).status=="REPOSITORY_INTEGRITY_HOLD"
    assert evaluate_repository_integrity(repository(crlf_fingerprint="e"*64)).status=="REPOSITORY_INTEGRITY_HOLD"

def test_stage26_requires_every_stub_path_classified_and_manifest_resolved():
    assert evaluate_governance_inventory(inventory()).status=="GOVERNANCE_INVENTORY_COMPLETE_UNVERIFIED"
    assert evaluate_governance_inventory(inventory(classifications=())).status=="GOVERNANCE_INVENTORY_HOLD"
    assert evaluate_governance_inventory(inventory(dependency_drift_resolved=False)).status=="GOVERNANCE_INVENTORY_HOLD"

def test_stage26_rejects_unresolved_disposition():
    bad=(Classification("core/x.py","UNKNOWN","review:x"),)
    assert evaluate_governance_inventory(inventory(classifications=bad)).status=="GOVERNANCE_INVENTORY_HOLD"

def test_stage27_requires_full_audit_domain_coverage():
    assert evaluate_audit_coverage(audit()).status=="AUDIT_COVERAGE_COMPLETE_UNVERIFIED"
    assert evaluate_audit_coverage(audit(findings=())).status=="AUDIT_COVERAGE_HOLD"

def test_stage27_rejects_unknown_or_duplicate_domains():
    bad=(AuditFinding("options","UNKNOWN","evidence:options"),)
    assert evaluate_audit_coverage(audit(findings=bad)).status=="AUDIT_COVERAGE_HOLD"
    dup=tuple(AuditFinding(x,"VERIFIED_PASS",f"evidence:{x}") for x in DOMAINS)+(AuditFinding("options","VERIFIED_PASS","evidence:dup"),)
    assert evaluate_audit_coverage(audit(findings=dup)).status=="AUDIT_COVERAGE_HOLD"

def test_all_stages_never_authorize_live():
    assert not evaluate_credential_closure(credential()).live_arming_permitted
    assert not evaluate_repository_integrity(repository()).live_arming_permitted
    assert not evaluate_governance_inventory(inventory()).live_arming_permitted
    assert not evaluate_audit_coverage(audit()).live_arming_permitted
