from dataclasses import replace
from core.governance.production_hardening_stages72_75 import (
 EvidenceIntegrity,ReviewerIndependence,RiskExceptionRegister,ReleaseDecisionRecord,
 evaluate_evidence_integrity,evaluate_reviewer_independence,evaluate_risk_exceptions,evaluate_release_decision)

def integrity():
 return EvidenceIntegrity("index","inventory","signature-report","reproduction","a"*40,"Ed25519","2026-11-09T10:00:00Z",8,8,0,True,True,True)
def reviewer():
 return ReviewerIndependence("scope","identity","qualifications","conflicts","approval","2026-11-09T10:00:00Z",False,False,True,True,4,4,0)
def exceptions():
 return RiskExceptionRegister("register","risk","owner","approval","2026-11-09T10:00:00Z",3,0,0,0,0,0,0,True,True,True)
def decision():
 return ReleaseDecisionRecord("decision","matrix","owner","challenge","2026-11-09T10:00:00Z","HOLD",2,3,4,True,False,False)

def test_complete_results_are_unverified_and_never_arm():
 results=[evaluate_evidence_integrity(integrity()),evaluate_reviewer_independence(reviewer()),evaluate_risk_exceptions(exceptions()),evaluate_release_decision(decision())]
 assert [x.stage for x in results]==[72,73,74,75]
 assert all(x.status.endswith("UNVERIFIED") for x in results)
 assert all(x.live_arming_permitted is False for x in results)

def test_artifact_hash_or_signature_gap_holds():
 x=evaluate_evidence_integrity(replace(integrity(),artifacts_hashed=7,signature_verified=False))
 assert x.status=="EVIDENCE_INTEGRITY_HOLD" and len(x.reasons)>=2

def test_author_or_evidence_owner_cannot_independently_review():
 x=evaluate_reviewer_independence(replace(reviewer(),reviewer_is_author=True,reviewer_controls_evidence_creation=True))
 assert x.status=="REVIEWER_INDEPENDENCE_HOLD" and len(x.reasons)>=2

def test_p0_p1_and_expired_exceptions_cannot_be_accepted():
 x=evaluate_risk_exceptions(replace(exceptions(),open_p0=1,p0_p1_accepted=1,expired_exceptions=1))
 assert x.status=="RISK_EXCEPTION_HOLD" and len(x.reasons)>=3

def test_release_authorization_or_live_arming_is_always_rejected():
 x=evaluate_release_decision(replace(decision(),decision="APPROVE",decision_is_authorized=True,live_arming_permitted=True))
 assert x.status=="RELEASE_DECISION_HOLD" and len(x.reasons)>=3
