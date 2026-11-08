"""Offline evidence governance gates, Stages 76–79. No live system access."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class Assessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False

def _ref(value: str, field: str, reasons: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"{field} reference is required")

def _time(value: str, field: str, reasons: list[str]) -> None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        reasons.append(f"{field} must be ISO-8601 with an explicit UTC offset")

def _count(value: int, field: str, reasons: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        reasons.append(f"{field} must be a non-negative integer")

@dataclass(frozen=True)
class EvidenceRetention:
    policy_ref: str
    schedule_ref: str
    classification_ref: str
    legal_hold_register_ref: str
    disposition_authority_ref: str
    assessment_ref: str
    assessed_at_utc: str
    artifacts_in_scope: int
    artifacts_with_classification: int
    artifacts_with_retention_rule: int
    artifacts_under_legal_hold: int
    unauthorized_dispositions: int
    disposition_proofs_reviewed: int
    retention_policy_approved: bool
    legal_hold_checks_completed: bool

def evaluate_evidence_retention(e: EvidenceRetention) -> Assessment:
    r: list[str] = []
    for name in ("policy_ref", "schedule_ref", "classification_ref", "legal_hold_register_ref",
                 "disposition_authority_ref", "assessment_ref"):
        _ref(getattr(e, name), name, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    for name in ("artifacts_in_scope", "artifacts_with_classification", "artifacts_with_retention_rule",
                 "artifacts_under_legal_hold", "unauthorized_dispositions", "disposition_proofs_reviewed"):
        _count(getattr(e, name), name, r)
    if isinstance(e.artifacts_in_scope, int) and not isinstance(e.artifacts_in_scope, bool):
        if e.artifacts_with_classification != e.artifacts_in_scope:
            r.append("every in-scope artifact must have a classification")
        if e.artifacts_with_retention_rule != e.artifacts_in_scope:
            r.append("every in-scope artifact must map to a retention rule")
    if isinstance(e.unauthorized_dispositions, int) and not isinstance(e.unauthorized_dispositions, bool) and e.unauthorized_dispositions != 0:
        r.append("unauthorized_dispositions must be zero")
    if e.retention_policy_approved is not True:
        r.append("retention_policy_approved must be explicitly attested true")
    if e.legal_hold_checks_completed is not True:
        r.append("legal_hold_checks_completed must be explicitly attested true")
    if r:
        return Assessment(76, "EVIDENCE_RETENTION_HOLD", tuple(r))
    return Assessment(76, "EVIDENCE_RETENTION_COMPLETE_UNVERIFIED",
                      ("retention, legal-hold and disposition evidence require independent source verification; no deletion is performed",))

@dataclass(frozen=True)
class DataLineagePackage:
    package_ref: str
    source_inventory_ref: str
    transformation_registry_ref: str
    environment_lock_ref: str
    reproducibility_report_ref: str
    independent_reproduction_ref: str
    assessed_at_utc: str
    sources_in_scope: int
    sources_identified: int
    transformations_in_scope: int
    transformations_documented: int
    source_checksum_mismatches: int
    environment_differences: int
    independent_reproduction_passed: bool
    lineage_reviewed: bool

def evaluate_data_lineage(e: DataLineagePackage) -> Assessment:
    r: list[str] = []
    for name in ("package_ref", "source_inventory_ref", "transformation_registry_ref", "environment_lock_ref",
                 "reproducibility_report_ref", "independent_reproduction_ref"):
        _ref(getattr(e, name), name, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    for name in ("sources_in_scope", "sources_identified", "transformations_in_scope",
                 "transformations_documented", "source_checksum_mismatches", "environment_differences"):
        _count(getattr(e, name), name, r)
    if isinstance(e.sources_in_scope, int) and not isinstance(e.sources_in_scope, bool) and e.sources_identified != e.sources_in_scope:
        r.append("every in-scope source must be identified")
    if isinstance(e.transformations_in_scope, int) and not isinstance(e.transformations_in_scope, bool) and e.transformations_documented != e.transformations_in_scope:
        r.append("every in-scope transformation must be documented")
    for name in ("source_checksum_mismatches", "environment_differences"):
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value != 0:
            r.append(f"{name} must be zero")
    if e.independent_reproduction_passed is not True:
        r.append("independent_reproduction_passed must be explicitly attested true")
    if e.lineage_reviewed is not True:
        r.append("lineage_reviewed must be explicitly attested true")
    if r:
        return Assessment(77, "DATA_LINEAGE_HOLD", tuple(r))
    return Assessment(77, "DATA_LINEAGE_COMPLETE_UNVERIFIED",
                      ("source identity, checksums and reproducibility require independent verification; no data is fetched",))

@dataclass(frozen=True)
class SupplyChainAssurance:
    assurance_ref: str
    sbom_ref: str
    build_provenance_ref: str
    dependency_attestations_ref: str
    vulnerability_register_ref: str
    independent_review_ref: str
    assessed_at_utc: str
    components_in_scope: int
    components_in_sbom: int
    components_with_provenance: int
    critical_vulnerabilities_open: int
    high_vulnerabilities_open: int
    vulnerabilities_without_disposition: int
    attestations_verified: bool
    independent_review_passed: bool

def evaluate_supply_chain_assurance(e: SupplyChainAssurance) -> Assessment:
    r: list[str] = []
    for name in ("assurance_ref", "sbom_ref", "build_provenance_ref", "dependency_attestations_ref",
                 "vulnerability_register_ref", "independent_review_ref"):
        _ref(getattr(e, name), name, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    for name in ("components_in_scope", "components_in_sbom", "components_with_provenance",
                 "critical_vulnerabilities_open", "high_vulnerabilities_open", "vulnerabilities_without_disposition"):
        _count(getattr(e, name), name, r)
    if isinstance(e.components_in_scope, int) and not isinstance(e.components_in_scope, bool):
        if e.components_in_sbom != e.components_in_scope:
            r.append("every in-scope component must appear in the SBOM")
        if e.components_with_provenance != e.components_in_scope:
            r.append("every in-scope component must have provenance")
    for name in ("critical_vulnerabilities_open", "high_vulnerabilities_open", "vulnerabilities_without_disposition"):
        value = getattr(e, name)
        if isinstance(value, int) and not isinstance(value, bool) and value != 0:
            r.append(f"{name} must be zero")
    if e.attestations_verified is not True:
        r.append("attestations_verified must be explicitly attested true")
    if e.independent_review_passed is not True:
        r.append("independent_review_passed must be explicitly attested true")
    if r:
        return Assessment(78, "SUPPLY_CHAIN_ASSURANCE_HOLD", tuple(r))
    return Assessment(78, "SUPPLY_CHAIN_ASSURANCE_COMPLETE_UNVERIFIED",
                      ("SBOM, provenance and vulnerability dispositions require independent verification; no packages are installed or fetched",))

@dataclass(frozen=True)
class TabletopExercise:
    exercise_ref: str
    scenario_ref: str
    participant_register_ref: str
    objectives_ref: str
    outcome_report_ref: str
    remediation_register_ref: str
    independent_observer_ref: str
    assessed_at_utc: str
    objectives_in_scope: int
    objectives_evaluated: int
    findings_in_scope: int
    findings_with_owner: int
    findings_with_deadline: int
    overdue_findings: int
    exercise_completed: bool
    observer_independent: bool
    operational_actions_executed: bool

def evaluate_tabletop_exercise(e: TabletopExercise) -> Assessment:
    r: list[str] = []
    for name in ("exercise_ref", "scenario_ref", "participant_register_ref", "objectives_ref",
                 "outcome_report_ref", "remediation_register_ref", "independent_observer_ref"):
        _ref(getattr(e, name), name, r)
    _time(e.assessed_at_utc, "assessed_at_utc", r)
    for name in ("objectives_in_scope", "objectives_evaluated", "findings_in_scope",
                 "findings_with_owner", "findings_with_deadline", "overdue_findings"):
        _count(getattr(e, name), name, r)
    if isinstance(e.objectives_in_scope, int) and not isinstance(e.objectives_in_scope, bool) and e.objectives_evaluated != e.objectives_in_scope:
        r.append("every exercise objective must be evaluated")
    if isinstance(e.findings_in_scope, int) and not isinstance(e.findings_in_scope, bool):
        if e.findings_with_owner != e.findings_in_scope:
            r.append("every finding must have an accountable owner")
        if e.findings_with_deadline != e.findings_in_scope:
            r.append("every finding must have a remediation deadline")
    if isinstance(e.overdue_findings, int) and not isinstance(e.overdue_findings, bool) and e.overdue_findings != 0:
        r.append("overdue_findings must be zero")
    if e.exercise_completed is not True:
        r.append("exercise_completed must be explicitly attested true")
    if e.observer_independent is not True:
        r.append("observer_independent must be explicitly attested true")
    if e.operational_actions_executed is not False:
        r.append("tabletop validation must not execute operational actions")
    if r:
        return Assessment(79, "TABLETOP_EXERCISE_HOLD", tuple(r))
    return Assessment(79, "TABLETOP_EXERCISE_COMPLETE_UNVERIFIED",
                      ("exercise outcomes and remediation closure require independent review; this gate performs no failover, restore or production action",))
