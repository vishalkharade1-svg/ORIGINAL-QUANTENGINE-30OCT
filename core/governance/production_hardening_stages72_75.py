"""Offline evidence governance gates, Stages 72–75. No live system access."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{40,64}$")

@dataclass(frozen=True)
class Assessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False

def _ref(v: str, name: str, r: list[str]) -> None:
    if not isinstance(v, str) or not v.strip():
        r.append(f"{name} reference is required")

def _time(v: str, name: str, r: list[str]) -> None:
    try:
        d=datetime.fromisoformat(v.strip().replace("Z","+00:00"))
        if d.tzinfo is None or d.utcoffset() is None: raise ValueError
    except (AttributeError,TypeError,ValueError):
        r.append(f"{name} must be ISO-8601 with explicit UTC offset")

def _count(v: int, name: str, r: list[str]) -> None:
    if isinstance(v,bool) or not isinstance(v,int) or v<0:
        r.append(f"{name} must be a non-negative integer")

@dataclass(frozen=True)
class EvidenceIntegrity:
    evidence_index_ref: str
    artifact_inventory_ref: str
    signature_verification_report_ref: str
    independent_reproduction_ref: str
    signer_key_fingerprint: str
    signature_algorithm: str
    assessed_at_utc: str
    artifacts_in_scope: int
    artifacts_hashed: int
    digest_mismatches: int
    signature_verified: bool
    signer_trust_independently_checked: bool
    key_revocation_status_checked: bool

def evaluate_evidence_integrity(e: EvidenceIntegrity) -> Assessment:
    r=[]
    for n in ("evidence_index_ref","artifact_inventory_ref","signature_verification_report_ref","independent_reproduction_ref"):
        _ref(getattr(e,n),n,r)
    if not isinstance(e.signer_key_fingerprint,str) or not _FINGERPRINT.fullmatch(e.signer_key_fingerprint):
        r.append("signer_key_fingerprint must be a 40–64 character lowercase fingerprint")
    if not isinstance(e.signature_algorithm,str) or not e.signature_algorithm.strip():
        r.append("signature_algorithm is required")
    _time(e.assessed_at_utc,"assessed_at_utc",r)
    for n in ("artifacts_in_scope","artifacts_hashed","digest_mismatches"):_count(getattr(e,n),n,r)
    if isinstance(e.artifacts_in_scope,int) and not isinstance(e.artifacts_in_scope,bool) and e.artifacts_hashed!=e.artifacts_in_scope:
        r.append("every in-scope artifact must be hashed")
    if isinstance(e.digest_mismatches,int) and not isinstance(e.digest_mismatches,bool) and e.digest_mismatches!=0:
        r.append("digest_mismatches must be zero")
    for n in ("signature_verified","signer_trust_independently_checked","key_revocation_status_checked"):
        if getattr(e,n) is not True:r.append(f"{n} must be explicitly attested true")
    if r:return Assessment(72,"EVIDENCE_INTEGRITY_HOLD",tuple(r))
    return Assessment(72,"EVIDENCE_INTEGRITY_COMPLETE_UNVERIFIED",("artifact hashes and signature assertions require independent cryptographic reproduction; no key material is inspected",))

@dataclass(frozen=True)
class ReviewerIndependence:
    review_scope_ref: str
    reviewer_identity_ref: str
    reviewer_qualification_ref: str
    conflict_declaration_ref: str
    independent_approval_ref: str
    assessed_at_utc: str
    reviewer_is_author: bool
    reviewer_controls_evidence_creation: bool
    conflicts_disclosed: bool
    conflicts_mitigated: bool
    required_competencies: int
    evidenced_competencies: int
    review_findings_open: int

def evaluate_reviewer_independence(e: ReviewerIndependence) -> Assessment:
    r=[]
    for n in ("review_scope_ref","reviewer_identity_ref","reviewer_qualification_ref","conflict_declaration_ref","independent_approval_ref"):_ref(getattr(e,n),n,r)
    _time(e.assessed_at_utc,"assessed_at_utc",r)
    for n in ("required_competencies","evidenced_competencies","review_findings_open"):_count(getattr(e,n),n,r)
    if e.reviewer_is_author is not False:r.append("reviewer must not be the author of the assessed control/evidence")
    if e.reviewer_controls_evidence_creation is not False:r.append("reviewer must not control evidence creation")
    for n in ("conflicts_disclosed","conflicts_mitigated"):
        if getattr(e,n) is not True:r.append(f"{n} must be explicitly attested true")
    if isinstance(e.required_competencies,int) and isinstance(e.evidenced_competencies,int) and e.evidenced_competencies<e.required_competencies:
        r.append("reviewer competency evidence is incomplete")
    if isinstance(e.review_findings_open,int) and e.review_findings_open!=0:r.append("review_findings_open must be zero")
    if r:return Assessment(73,"REVIEWER_INDEPENDENCE_HOLD",tuple(r))
    return Assessment(73,"REVIEWER_INDEPENDENCE_COMPLETE_UNVERIFIED",("reviewer identity, competence and independence require independent confirmation",))

@dataclass(frozen=True)
class RiskExceptionRegister:
    register_ref: str
    risk_assessment_ref: str
    accountable_owner_ref: str
    independent_approval_ref: str
    assessed_at_utc: str
    exceptions_in_scope: int
    open_p0: int
    open_p1: int
    expired_exceptions: int
    exceptions_without_owner: int
    exceptions_without_expiry: int
    p0_p1_accepted: int
    all_exceptions_have_rationale: bool
    compensating_controls_tested: bool
    periodic_review_scheduled: bool

def evaluate_risk_exceptions(e: RiskExceptionRegister) -> Assessment:
    r=[]
    for n in ("register_ref","risk_assessment_ref","accountable_owner_ref","independent_approval_ref"):_ref(getattr(e,n),n,r)
    _time(e.assessed_at_utc,"assessed_at_utc",r)
    for n in ("exceptions_in_scope","open_p0","open_p1","expired_exceptions","exceptions_without_owner","exceptions_without_expiry","p0_p1_accepted"):_count(getattr(e,n),n,r)
    if e.exceptions_in_scope==0:r.append("exceptions_in_scope must be non-zero")
    for n in ("open_p0","open_p1","expired_exceptions","exceptions_without_owner","exceptions_without_expiry","p0_p1_accepted"):
        v=getattr(e,n)
        if isinstance(v,int) and not isinstance(v,bool) and v!=0:r.append(f"{n} must be zero")
    for n in ("all_exceptions_have_rationale","compensating_controls_tested","periodic_review_scheduled"):
        if getattr(e,n) is not True:r.append(f"{n} must be explicitly attested true")
    if r:return Assessment(74,"RISK_EXCEPTION_HOLD",tuple(r))
    return Assessment(74,"RISK_EXCEPTION_REGISTER_COMPLETE_UNVERIFIED",("risk acceptance remains subject to independent authority and cannot waive P0/P1 or authorize live operation",))

@dataclass(frozen=True)
class ReleaseDecisionRecord:
    decision_record_ref: str
    evidence_matrix_ref: str
    accountable_decision_owner_ref: str
    independent_challenge_ref: str
    assessed_at_utc: str
    decision: str
    open_critical_blockers: int
    open_high_blockers: int
    prerequisite_gates_unverified: int
    decision_owner_is_independent: bool
    decision_is_authorized: bool
    live_arming_permitted: bool

def evaluate_release_decision(e: ReleaseDecisionRecord) -> Assessment:
    r=[]
    for n in ("decision_record_ref","evidence_matrix_ref","accountable_decision_owner_ref","independent_challenge_ref"):_ref(getattr(e,n),n,r)
    _time(e.assessed_at_utc,"assessed_at_utc",r)
    if e.decision not in {"HOLD","PAPER_ONLY"}:r.append("decision must be HOLD or PAPER_ONLY")
    for n in ("open_critical_blockers","open_high_blockers","prerequisite_gates_unverified"):_count(getattr(e,n),n,r)
    if e.decision_owner_is_independent is not True:r.append("decision owner independence must be attested")
    if e.decision_is_authorized is not False:r.append("this validator cannot authorize release")
    if e.live_arming_permitted is not False:r.append("live_arming_permitted must remain false")
    if r:return Assessment(75,"RELEASE_DECISION_HOLD",tuple(r))
    return Assessment(75,"RELEASE_DECISION_RECORDED_UNVERIFIED",("recorded decision is a hold/paper-only posture, not release approval or operational authorization",))
