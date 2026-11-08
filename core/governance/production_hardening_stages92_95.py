"""Offline, reference-only evidence gates for QuantEngine Stages 92–95."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import re

@dataclass(frozen=True)
class Assessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False

def _valid_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0

def _check(refs: tuple[tuple[str, str], ...], counts: tuple[tuple[str, int], ...],
           flags: tuple[tuple[str, bool], ...], assessed_at: str) -> list[str]:
    reasons: list[str] = []
    for name, value in refs:
        if not isinstance(value, str) or not value.strip():
            reasons.append(f"{name} reference is required")
    try:
        parsed = datetime.fromisoformat(assessed_at.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        reasons.append("assessed_at must be ISO-8601 with an explicit UTC offset")
    for name, value in counts:
        if not _valid_count(value):
            reasons.append(f"{name} must be a non-negative integer")
    for name, value in flags:
        if value is not True:
            reasons.append(f"{name} must be explicitly attested true")
    return reasons

def _eq(a: object, b: object) -> bool:
    return _valid_count(a) and _valid_count(b) and a == b

def _result(stage: int, prefix: str, reasons: list[str], note: str) -> Assessment:
    if reasons:
        return Assessment(stage, f"{prefix}_HOLD", tuple(reasons))
    return Assessment(stage, f"{prefix}_COMPLETE_UNVERIFIED", (note,))

@dataclass(frozen=True)
class ContinuityReadiness:
    assessment_ref: str
    service_criticality_ref: str
    dependency_map_ref: str
    recovery_objectives_ref: str
    backup_evidence_ref: str
    recovery_exercise_ref: str
    communications_plan_ref: str
    assessed_at: str
    critical_services_in_scope: int
    services_with_rto_rpo: int
    services_with_backup_evidence: int
    services_in_recovery_exercise: int
    recovery_objective_misses: int
    unowned_recovery_dependencies: int
    exercise_completed: bool
    independent_observer_attested: bool

def evaluate_continuity_readiness(e: ContinuityReadiness) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "service_criticality_ref", "dependency_map_ref", "recovery_objectives_ref",
        "backup_evidence_ref", "recovery_exercise_ref", "communications_plan_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "critical_services_in_scope", "services_with_rto_rpo", "services_with_backup_evidence",
        "services_in_recovery_exercise", "recovery_objective_misses", "unowned_recovery_dependencies"))
    flags = (("exercise_completed", e.exercise_completed),
             ("independent_observer_attested", e.independent_observer_attested))
    r = _check(refs, counts, flags, e.assessed_at)
    for name in ("services_with_rto_rpo", "services_with_backup_evidence", "services_in_recovery_exercise"):
        if not _eq(getattr(e, name), e.critical_services_in_scope):
            r.append(f"{name} must cover every critical service")
    for name in ("recovery_objective_misses", "unowned_recovery_dependencies"):
        if _valid_count(getattr(e, name)) and getattr(e, name) != 0:
            r.append(f"{name} must be zero")
    return _result(92, "CONTINUITY_READINESS", r,
        "recovery objectives and exercise artifacts remain independently unverified; no restore, failover or service operation is performed")

@dataclass(frozen=True)
class TestAssurance:
    assessment_ref: str
    test_inventory_ref: str
    requirements_traceability_ref: str
    deterministic_replay_ref: str
    property_test_report_ref: str
    mutation_test_report_ref: str
    defect_register_ref: str
    assessed_at: str
    requirements_in_scope: int
    requirements_with_tests: int
    test_cases_in_scope: int
    deterministic_cases_verified: int
    property_suites_in_scope: int
    property_suites_passed: int
    mutation_targets_in_scope: int
    mutation_targets_killed: int
    unresolved_critical_defects: int
    independent_review_attested: bool

def evaluate_test_assurance(e: TestAssurance) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "test_inventory_ref", "requirements_traceability_ref", "deterministic_replay_ref",
        "property_test_report_ref", "mutation_test_report_ref", "defect_register_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "requirements_in_scope", "requirements_with_tests", "test_cases_in_scope",
        "deterministic_cases_verified", "property_suites_in_scope", "property_suites_passed",
        "mutation_targets_in_scope", "mutation_targets_killed", "unresolved_critical_defects"))
    r = _check(refs, counts, (("independent_review_attested", e.independent_review_attested),), e.assessed_at)
    for a,b,label in (
        (e.requirements_with_tests,e.requirements_in_scope,"requirements_with_tests"),
        (e.deterministic_cases_verified,e.test_cases_in_scope,"deterministic_cases_verified"),
        (e.property_suites_passed,e.property_suites_in_scope,"property_suites_passed"),
        (e.mutation_targets_killed,e.mutation_targets_in_scope,"mutation_targets_killed")):
        if not _eq(a,b):
            r.append(f"{label} must cover every in-scope item")
    if _valid_count(e.unresolved_critical_defects) and e.unresolved_critical_defects != 0:
        r.append("unresolved_critical_defects must be zero")
    return _result(93, "TEST_ASSURANCE", r,
        "test adequacy and reproducibility references remain independently unverified; this does not substitute for full repository regression")

@dataclass(frozen=True)
class OperationalHandoff:
    assessment_ref: str
    runbook_inventory_ref: str
    service_ownership_ref: str
    escalation_matrix_ref: str
    training_evidence_ref: str
    handoff_acceptance_ref: str
    maintenance_calendar_ref: str
    assessed_at: str
    services_in_scope: int
    services_with_runbooks: int
    services_with_named_owners: int
    escalation_paths_in_scope: int
    escalation_paths_tested: int
    unaccepted_handoffs: int
    unowned_critical_services: int
    training_completed: bool
    independent_review_attested: bool

def evaluate_operational_handoff(e: OperationalHandoff) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "runbook_inventory_ref", "service_ownership_ref", "escalation_matrix_ref",
        "training_evidence_ref", "handoff_acceptance_ref", "maintenance_calendar_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "services_in_scope", "services_with_runbooks", "services_with_named_owners",
        "escalation_paths_in_scope", "escalation_paths_tested", "unaccepted_handoffs",
        "unowned_critical_services"))
    flags = (("training_completed", e.training_completed),
             ("independent_review_attested", e.independent_review_attested))
    r = _check(refs, counts, flags, e.assessed_at)
    for name in ("services_with_runbooks", "services_with_named_owners"):
        if not _eq(getattr(e, name), e.services_in_scope):
            r.append(f"{name} must cover every in-scope service")
    if not _eq(e.escalation_paths_tested, e.escalation_paths_in_scope):
        r.append("every escalation path must have test evidence")
    for name in ("unaccepted_handoffs", "unowned_critical_services"):
        if _valid_count(getattr(e, name)) and getattr(e, name) != 0:
            r.append(f"{name} must be zero")
    return _result(94, "OPERATIONAL_HANDOFF", r,
        "runbooks, ownership and handoff records require independent verification; no staff are contacted and no operational shift is assumed")

@dataclass(frozen=True)
class SafetyInterlockAssurance:
    assessment_ref: str
    safety_requirements_ref: str
    control_design_ref: str
    fail_closed_test_ref: str
    stale_evidence_test_ref: str
    bypass_analysis_ref: str
    independent_assessment_ref: str
    assessed_at: str
    interlocks_in_scope: int
    interlocks_with_design: int
    interlocks_with_fail_closed_tests: int
    stale_evidence_cases_in_scope: int
    stale_evidence_cases_rejected: int
    bypass_paths_identified: int
    unresolved_safety_findings: int
    independent_review_attested: bool

def evaluate_safety_interlocks(e: SafetyInterlockAssurance) -> Assessment:
    refs = tuple((n, getattr(e, n)) for n in (
        "assessment_ref", "safety_requirements_ref", "control_design_ref", "fail_closed_test_ref",
        "stale_evidence_test_ref", "bypass_analysis_ref", "independent_assessment_ref"))
    counts = tuple((n, getattr(e, n)) for n in (
        "interlocks_in_scope", "interlocks_with_design", "interlocks_with_fail_closed_tests",
        "stale_evidence_cases_in_scope", "stale_evidence_cases_rejected", "bypass_paths_identified",
        "unresolved_safety_findings"))
    r = _check(refs, counts, (("independent_review_attested", e.independent_review_attested),), e.assessed_at)
    for name in ("interlocks_with_design", "interlocks_with_fail_closed_tests"):
        if not _eq(getattr(e, name), e.interlocks_in_scope):
            r.append(f"{name} must cover every in-scope interlock")
    if not _eq(e.stale_evidence_cases_rejected, e.stale_evidence_cases_in_scope):
        r.append("every stale-evidence case must be rejected in test evidence")
    for name in ("bypass_paths_identified", "unresolved_safety_findings"):
        if _valid_count(getattr(e, name)) and getattr(e, name) != 0:
            r.append(f"{name} must be zero")
    return _result(95, "SAFETY_INTERLOCK", r,
        "fail-closed control design and test evidence remain independently unverified; no interlock is activated or live-arming path enabled")
