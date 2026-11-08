"""Offline evidence gates for privacy, access, incident and change governance (Stages 80–83)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class Assessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False

def _required(value: str, field: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{field} reference is required")

def _timestamp(value: str, reasons: list[str]) -> None:
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        reasons.append("assessed_at must be ISO-8601 with an explicit UTC offset")

def _nonnegative(value: int, field: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append(f"{field} must be a non-negative integer")

@dataclass(frozen=True)
class PrivacyGovernance:
    assessment_ref: str
    data_inventory_ref: str
    purpose_register_ref: str
    minimization_review_ref: str
    retention_mapping_ref: str
    privacy_impact_review_ref: str
    assessed_at: str
    data_elements_in_scope: int
    data_elements_with_purpose: int
    unnecessary_elements_retained: int
    unclassified_elements: int
    unresolved_high_privacy_findings: int
    minimization_review_approved: bool
    privacy_impact_review_completed: bool

def evaluate_privacy_governance(e: PrivacyGovernance) -> Assessment:
    r: list[str] = []
    for f in ("assessment_ref", "data_inventory_ref", "purpose_register_ref", "minimization_review_ref",
              "retention_mapping_ref", "privacy_impact_review_ref"):
        _required(getattr(e, f), f, r)
    _timestamp(e.assessed_at, r)
    for f in ("data_elements_in_scope", "data_elements_with_purpose", "unnecessary_elements_retained",
              "unclassified_elements", "unresolved_high_privacy_findings"):
        _nonnegative(getattr(e, f), f, r)
    if isinstance(e.data_elements_in_scope, int) and not isinstance(e.data_elements_in_scope, bool) and e.data_elements_with_purpose != e.data_elements_in_scope:
        r.append("every data element must have a documented purpose")
    for f in ("unnecessary_elements_retained", "unclassified_elements", "unresolved_high_privacy_findings"):
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v != 0:
            r.append(f"{f} must be zero")
    if e.minimization_review_approved is not True:
        r.append("minimization_review_approved must be explicitly attested true")
    if e.privacy_impact_review_completed is not True:
        r.append("privacy_impact_review_completed must be explicitly attested true")
    if r:
        return Assessment(80, "PRIVACY_GOVERNANCE_HOLD", tuple(r))
    return Assessment(80, "PRIVACY_GOVERNANCE_COMPLETE_UNVERIFIED",
                      ("purpose, minimization and privacy-impact evidence require independent verification; no personal data is accessed",))

@dataclass(frozen=True)
class AccessGovernance:
    assessment_ref: str
    identity_inventory_ref: str
    role_matrix_ref: str
    privileged_access_review_ref: str
    segregation_review_ref: str
    access_certification_ref: str
    assessed_at: str
    identities_in_scope: int
    identities_reviewed: int
    privileged_identities_in_scope: int
    privileged_identities_reviewed: int
    orphaned_accounts: int
    excessive_privileges: int
    unresolved_conflicts: int
    independent_certification: bool

def evaluate_access_governance(e: AccessGovernance) -> Assessment:
    r: list[str] = []
    for f in ("assessment_ref", "identity_inventory_ref", "role_matrix_ref", "privileged_access_review_ref",
              "segregation_review_ref", "access_certification_ref"):
        _required(getattr(e, f), f, r)
    _timestamp(e.assessed_at, r)
    for f in ("identities_in_scope", "identities_reviewed", "privileged_identities_in_scope",
              "privileged_identities_reviewed", "orphaned_accounts", "excessive_privileges", "unresolved_conflicts"):
        _nonnegative(getattr(e, f), f, r)
    if isinstance(e.identities_in_scope, int) and not isinstance(e.identities_in_scope, bool) and e.identities_reviewed != e.identities_in_scope:
        r.append("all identities must be reviewed")
    if isinstance(e.privileged_identities_in_scope, int) and not isinstance(e.privileged_identities_in_scope, bool) and e.privileged_identities_reviewed != e.privileged_identities_in_scope:
        r.append("all privileged identities must be reviewed")
    for f in ("orphaned_accounts", "excessive_privileges", "unresolved_conflicts"):
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v != 0:
            r.append(f"{f} must be zero")
    if e.independent_certification is not True:
        r.append("independent_certification must be explicitly attested true")
    if r:
        return Assessment(81, "ACCESS_GOVERNANCE_HOLD", tuple(r))
    return Assessment(81, "ACCESS_GOVERNANCE_COMPLETE_UNVERIFIED",
                      ("identity and access evidence requires independent verification; this gate does not inspect or change accounts or permissions",))

@dataclass(frozen=True)
class IncidentReadiness:
    assessment_ref: str
    response_plan_ref: str
    severity_matrix_ref: str
    escalation_roster_ref: str
    communications_plan_ref: str
    exercise_report_ref: str
    lessons_register_ref: str
    assessed_at: str
    scenarios_in_scope: int
    scenarios_exercised: int
    responders_in_scope: int
    responders_acknowledged: int
    critical_contact_gaps: int
    unowned_lessons: int
    overdue_lessons: int
    exercise_completed: bool
    independent_observer: bool

def evaluate_incident_readiness(e: IncidentReadiness) -> Assessment:
    r: list[str] = []
    for f in ("assessment_ref", "response_plan_ref", "severity_matrix_ref", "escalation_roster_ref",
              "communications_plan_ref", "exercise_report_ref", "lessons_register_ref"):
        _required(getattr(e, f), f, r)
    _timestamp(e.assessed_at, r)
    for f in ("scenarios_in_scope", "scenarios_exercised", "responders_in_scope", "responders_acknowledged",
              "critical_contact_gaps", "unowned_lessons", "overdue_lessons"):
        _nonnegative(getattr(e, f), f, r)
    if isinstance(e.scenarios_in_scope, int) and not isinstance(e.scenarios_in_scope, bool) and e.scenarios_exercised != e.scenarios_in_scope:
        r.append("all scoped incident scenarios must be exercised")
    if isinstance(e.responders_in_scope, int) and not isinstance(e.responders_in_scope, bool) and e.responders_acknowledged != e.responders_in_scope:
        r.append("all scoped responders must acknowledge the plan")
    for f in ("critical_contact_gaps", "unowned_lessons", "overdue_lessons"):
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v != 0:
            r.append(f"{f} must be zero")
    if e.exercise_completed is not True:
        r.append("exercise_completed must be explicitly attested true")
    if e.independent_observer is not True:
        r.append("independent_observer must be explicitly attested true")
    if r:
        return Assessment(82, "INCIDENT_READINESS_HOLD", tuple(r))
    return Assessment(82, "INCIDENT_READINESS_COMPLETE_UNVERIFIED",
                      ("incident response capability requires independent evidence validation; no incident is declared or response action initiated",))

@dataclass(frozen=True)
class ChangeControl:
    assessment_ref: str
    change_policy_ref: str
    change_register_ref: str
    impact_assessment_ref: str
    test_evidence_ref: str
    approval_record_ref: str
    rollback_plan_ref: str
    assessed_at: str
    changes_in_scope: int
    changes_with_impact_assessment: int
    changes_with_test_evidence: int
    changes_with_required_approval: int
    changes_with_rollback_plan: int
    unauthorized_changes: int
    emergency_changes_without_review: int
    independent_sample_review: bool

def evaluate_change_control(e: ChangeControl) -> Assessment:
    r: list[str] = []
    for f in ("assessment_ref", "change_policy_ref", "change_register_ref", "impact_assessment_ref",
              "test_evidence_ref", "approval_record_ref", "rollback_plan_ref"):
        _required(getattr(e, f), f, r)
    _timestamp(e.assessed_at, r)
    for f in ("changes_in_scope", "changes_with_impact_assessment", "changes_with_test_evidence",
              "changes_with_required_approval", "changes_with_rollback_plan", "unauthorized_changes",
              "emergency_changes_without_review"):
        _nonnegative(getattr(e, f), f, r)
    for f in ("changes_with_impact_assessment", "changes_with_test_evidence",
              "changes_with_required_approval", "changes_with_rollback_plan"):
        v = getattr(e, f)
        if isinstance(e.changes_in_scope, int) and not isinstance(e.changes_in_scope, bool) and v != e.changes_in_scope:
            r.append(f"{f} must cover every in-scope change")
    for f in ("unauthorized_changes", "emergency_changes_without_review"):
        v = getattr(e, f)
        if isinstance(v, int) and not isinstance(v, bool) and v != 0:
            r.append(f"{f} must be zero")
    if e.independent_sample_review is not True:
        r.append("independent_sample_review must be explicitly attested true")
    if r:
        return Assessment(83, "CHANGE_CONTROL_HOLD", tuple(r))
    return Assessment(83, "CHANGE_CONTROL_COMPLETE_UNVERIFIED",
                      ("change records and approval evidence require independent verification; no change is applied by this gate",))
