"""Machine-checkable evidence-gate contracts (G0-G14).

Implements the gate-dependency specifications as explicit rules,
not documentation:

* gate classes (structural / external / local / research);
* hard/soft/informative/none dependencies with conditional edges
  (G4 needs G2 only when its authoritative source requires auth;
  G5 needs G4 only when contract identity is required);
* ``BLOCKED_BY_PREREQUISITE`` vs independently ``BLOCKED`` vs
  ``NOT_ATTEMPTED`` execution states;
* field-level reconciliation domains (account/contract/economics/
  lifecycle reconcile independently);
* domain summaries plus the external-sandbox aggregate
  (``SANDBOX_EXTERNAL_EVIDENCE_*``);
* deterministic matrix identity reusing the existing stable hash
  authority (``research.phase11g.provenance.model.content_hash``).

No gate result can promote production readiness: every matrix
carries ``is_production_ready = False`` and construction refuses
``True``. No cross-gate inference is possible by construction:
a downstream VERIFIED/PARTIAL claim with an unsatisfied hard
prerequisite is rejected by ``validate_matrix``.
"""

from __future__ import annotations

import dataclasses

from research.phase11g.provenance.model import content_hash


MATRIX_SCHEMA_VERSION = "1"
MATRIX_TYPE = "QUANTENGINE_EVIDENCE_GATE_MATRIX"
MATRIX_IDENTITY_ALGORITHM = (
    "content_hash:research.phase11g.provenance.model:"
    "sha256-canonical-json"
)

GATE_IDS = ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7",
            "G8", "G9", "G10", "G11", "G12", "G13", "G14")

GATE_STATUS = ("VERIFIED", "PARTIAL", "BLOCKED", "NOT_ATTEMPTED")

EXECUTION_STATE = ("EXECUTED", "BLOCKED_BY_PREREQUISITE",
                   "NOT_APPLICABLE", "NOT_ATTEMPTED")

DEPENDENCY_TYPE = ("HARD", "SOFT", "INFORMATIVE", "NONE")

EXTERNAL_FINAL = ("SANDBOX_EXTERNAL_EVIDENCE_VERIFIED",
                  "SANDBOX_EXTERNAL_EVIDENCE_PARTIAL",
                  "SANDBOX_EXTERNAL_EVIDENCE_BLOCKED")


class GateError(ValueError):
    """A gate definition, result, or matrix is invalid."""


def _str_tuple(value, field):
    if isinstance(value, (tuple, list)):
        items = tuple(value)
    else:
        raise GateError("%s must be a tuple/list" % field)
    for item in items:
        if not isinstance(item, str):
            raise GateError("%s items must be str" % field)
    return items


@dataclasses.dataclass(frozen=True)
class Prerequisite:
    """One dependency edge: gate_id + type + applicability condition."""
    gate_id: str
    dependency: str
    condition: str = ""

    def __post_init__(self):
        if self.gate_id not in GATE_IDS:
            raise GateError("unknown prerequisite gate %r" % self.gate_id)
        if self.dependency not in DEPENDENCY_TYPE:
            raise GateError("unknown dependency type %r"
                            % self.dependency)


@dataclasses.dataclass(frozen=True)
class GateDefinition:
    gate_id: str
    title: str
    gate_class: str
    required_evidence: tuple
    prerequisites: tuple = ()

    def __post_init__(self):
        if self.gate_id not in GATE_IDS:
            raise GateError("unknown gate %r" % self.gate_id)
        if self.gate_class not in ("STRUCTURAL", "EXTERNAL",
                                   "LOCAL", "RESEARCH"):
            raise GateError("unknown gate class %r" % self.gate_class)
        object.__setattr__(self, "required_evidence",
                           _str_tuple(self.required_evidence,
                                      "required_evidence"))
        prereqs = tuple(self.prerequisites)
        for item in prereqs:
            if not isinstance(item, Prerequisite):
                raise GateError("prerequisites must be Prerequisite")
        object.__setattr__(self, "prerequisites", prereqs)


def _definitions():
    H = "HARD"
    S = "SOFT"
    I = "INFORMATIVE"
    return (
        GateDefinition("G0", "Repository / Architecture Integrity",
                       "STRUCTURAL",
                       ("repository_root", "head", "worktree_state",
                        "credential_authority", "exchange_authority",
                        "contract_authority", "economics_authority",
                        "reconciliation_authority",
                        "evidence_authority")),
        GateDefinition("G1", "Configuration Integrity", "STRUCTURAL",
                       ("variable_names", "variables_present_absent",
                        "env_loading", "credential_authority",
                        "sandbox_endpoint", "endpoint_selection_check",
                        "signing_authority")),
        GateDefinition("G2", "Sandbox Authentication", "EXTERNAL",
                       ("sandbox_environment", "sandbox_endpoint",
                        "auth_authority", "authenticated_read",
                        "exchange_response", "auth_outcome",
                        "failure_classification"),
                       (Prerequisite("G1", H,
                                     "configured credentials/endpoints"),)),
        GateDefinition("G3", "Sandbox Account Evidence", "EXTERNAL",
                       ("account_read", "account_class", "currency",
                        "available_balance", "equity_if_provided",
                        "margin_if_provided"),
                       (Prerequisite("G2", H, "authenticated identity"),)),
        GateDefinition("G4", "Contract / Product Evidence", "EXTERNAL",
                       ("symbol", "contract_type", "contract_status",
                        "quote_currency", "settlement_currency_if_applicable",
                        "tick_size", "price_precision",
                        "quantity_precision", "minimum_order_size",
                        "extended_terms_if_supported"),
                       (Prerequisite("G2", H,
                                     "when authoritative source requires "
                                     "authenticated access"),)),
        GateDefinition("G5", "Economics Evidence", "EXTERNAL",
                       ("maker_fee", "taker_fee", "funding_mechanism",
                        "funding_availability", "contract_value_economics",
                        "tick_economics", "minimum_quantity_economics",
                        "model_status_per_component"),
                       (Prerequisite("G4", H,
                                     "when economics require contract "
                                     "identity"),)),
        GateDefinition("G6", "Sandbox Order Lifecycle", "EXTERNAL",
                       ("sandbox_identity", "submission_accepted",
                        "order_identifier", "order_state", "fill_state",
                        "cancel_close", "final_state", "residual_orders",
                        "residual_positions", "cleanup", "reconciliation"),
                       (Prerequisite("G2", H, "sandbox identity"),
                        Prerequisite("G3", H, "account context"),
                        Prerequisite("G4", H, "instrument context"))),
        GateDefinition("G7", "Reconciliation", "EXTERNAL",
                       ("account_domain", "contract_domain",
                        "economics_domain", "lifecycle_domain"),
                       (Prerequisite("G3", H,
                                     "account domain only; field-level"),
                        Prerequisite("G4", H,
                                     "contract domain only; field-level"),
                        Prerequisite("G5", H,
                                     "economics domain only; field-level"),
                        Prerequisite("G6", H,
                                     "lifecycle domain only; field-level"))),
        GateDefinition("G8", "Local Paper Preview", "LOCAL",
                       ("public_data_received", "closed_candles_only",
                        "normalization", "routing", "paper_runtime",
                        "dry_run", "risk_gates_active",
                        "no_live_executor", "no_exchange_write",
                        "paper_only_flags", "observations")),
        GateDefinition("G9", "Dashboard / Observability", "LOCAL",
                       ("localhost_binding", "auth_enabled",
                        "valid_token", "invalid_token_rejected",
                        "unauthenticated_rejected", "readonly_routes",
                        "no_mutation_route", "recovery"),
                       (Prerequisite("G8", S,
                                     "runtime observability only; security "
                                     "independently testable"),)),
        GateDefinition("G10", "Production Isolation", "STRUCTURAL",
                       ("research_no_production", "paper_no_live_executor",
                        "public_data_no_orders",
                        "sandbox_no_production_selection",
                        "browser_no_mutation", "safety_invariants")),
        GateDefinition("G11", "Secret Safety", "STRUCTURAL",
                       ("stdout", "stderr", "logs", "reports",
                        "json_artifacts", "exceptions", "snapshots",
                        "git_diff", "generated_files")),
        GateDefinition("G12", "Determinism", "STRUCTURAL",
                       ("repeat_identical", "ordering_stable",
                        "classification_stable")),
        GateDefinition("G13", "Research / OOS Validation", "RESEARCH",
                       ("discovery_period", "oos_periods",
                        "temporal_ordering", "candidate_provenance",
                        "baseline", "per_period_results", "sample_counts",
                        "trade_counts", "economic_deltas", "status_per_period",
                        "survival_statistics", "consistency",
                        "multiple_testing", "robustness", "limitations")),
        GateDefinition("G14", "Artifact Validity", "STRUCTURAL",
                       ("schema_valid", "immutable",
                        "deterministic_identity",
                        "canonical_serialization", "no_credential_fields",
                        "no_secret_values", "environment_identified",
                        "venue_identified", "provenance_identified",
                        "status_consistent", "classification_consistent",
                        "production_ready_false")),
    )


DEFINITIONS = {d.gate_id: d for d in _definitions()}

DOMAINS = (
    ("REPOSITORY", ("G0",)),
    ("CONFIGURATION", ("G1",)),
    ("SANDBOX_EXTERNAL", ("G2", "G3", "G4", "G5", "G6", "G7")),
    ("LOCAL_PAPER", ("G8",)),
    ("OBSERVABILITY", ("G9",)),
    ("PRODUCTION_ISOLATION", ("G10",)),
    ("SECRET_SAFETY", ("G11",)),
    ("DETERMINISM", ("G12",)),
    ("RESEARCH_OOS", ("G13",)),
    ("ARTIFACT_VALIDITY", ("G14",)),
)


@dataclasses.dataclass(frozen=True)
class GateResult:
    gate_id: str
    status: str
    execution_state: str
    prerequisites: tuple = ()
    satisfied_prerequisites: tuple = ()
    missing_prerequisites: tuple = ()
    required_evidence: tuple = ()
    observed_evidence: tuple = ()
    missing_evidence: tuple = ()
    blocking_reasons: tuple = ()
    limitations: tuple = ()

    def __post_init__(self):
        if self.gate_id not in GATE_IDS:
            raise GateError("unknown gate %r" % self.gate_id)
        if self.status not in GATE_STATUS:
            raise GateError("gate %s: unknown status %r"
                            % (self.gate_id, self.status))
        if self.execution_state not in EXECUTION_STATE:
            raise GateError("gate %s: unknown execution_state %r"
                            % (self.gate_id, self.status))
        for field in ("prerequisites", "satisfied_prerequisites",
                      "missing_prerequisites", "required_evidence",
                      "observed_evidence", "missing_evidence",
                      "blocking_reasons", "limitations"):
            object.__setattr__(self, field,
                               _str_tuple(getattr(self, field), field))
        for item in self.missing_prerequisites:
            if item not in GATE_IDS:
                raise GateError("gate %s: unknown missing prerequisite %r"
                                % (self.gate_id, item))
        # Internal consistency (no conflation of dimensions).
        if self.status == "VERIFIED" and (
                self.missing_evidence or self.blocking_reasons):
            raise GateError(
                "gate %s: VERIFIED forbids missing evidence and "
                "blocking reasons" % self.gate_id)
        if self.status == "VERIFIED" and self.missing_prerequisites:
            raise GateError(
                "gate %s: VERIFIED forbids missing prerequisites"
                % self.gate_id)
        if (self.execution_state == "BLOCKED_BY_PREREQUISITE"
                and not self.missing_prerequisites):
            raise GateError(
                "gate %s: BLOCKED_BY_PREREQUISITE requires named "
                "missing prerequisites" % self.gate_id)
        if (self.execution_state == "NOT_ATTEMPTED"
                and self.status == "VERIFIED"):
            raise GateError(
                "gate %s: NOT_ATTEMPTED can never be VERIFIED"
                % self.gate_id)
        if (self.execution_state == "EXECUTED"
                and self.status in ("VERIFIED", "PARTIAL")
                and self.missing_prerequisites):
            raise GateError(
                "gate %s: EXECUTED %s forbids missing prerequisites"
                % (self.gate_id, self.status))

    def to_dict(self):
        return {
            "gate_id": self.gate_id,
            "status": self.status,
            "execution_state": self.execution_state,
            "prerequisites": list(self.prerequisites),
            "satisfied_prerequisites": list(self.satisfied_prerequisites),
            "missing_prerequisites": list(self.missing_prerequisites),
            "required_evidence": list(self.required_evidence),
            "observed_evidence": list(self.observed_evidence),
            "missing_evidence": list(self.missing_evidence),
            "blocking_reasons": list(self.blocking_reasons),
            "limitations": list(self.limitations),
        }


def lifecycle_attempt_allowed(results):
    """True only when G2, G3, and G4 are all VERIFIED.

    The G6 hard triple: no sandbox order-lifecycle operation may be
    attempted merely to prove a gate is blocked. Anything missing
    means ``BLOCKED_BY_PREREQUISITE`` with no attempt.
    """
    try:
        return all(results[g].status == "VERIFIED"
                   for g in ("G2", "G3", "G4"))
    except (KeyError, AttributeError):
        return False


def _domain_status(gate_ids, results):
    states = [results[g].status for g in gate_ids]
    if all(s == "VERIFIED" for s in states):
        return "VERIFIED"
    if all(s == "NOT_ATTEMPTED" for s in states):
        return "NOT_ATTEMPTED"
    if any(s == "BLOCKED" for s in states):
        # A domain with any hard block is BLOCKED unless every
        # non-blocked member is merely unattempted... keep the
        # conservative rule: any BLOCKED blocks the domain.
        return "BLOCKED"
    return "PARTIAL"


def external_final(results):
    """Aggregate G2-G7 into SANDBOX_EXTERNAL_EVIDENCE_* (no inference)."""
    states = [results[g].status for g in
              ("G2", "G3", "G4", "G5", "G6", "G7")]
    if all(s == "VERIFIED" for s in states):
        return "SANDBOX_EXTERNAL_EVIDENCE_VERIFIED"
    if states[0] == "VERIFIED":
        return "SANDBOX_EXTERNAL_EVIDENCE_PARTIAL"
    return "SANDBOX_EXTERNAL_EVIDENCE_BLOCKED"


def validate_matrix(results):
    """Reject cross-gate inference and inconsistent combinations."""
    for gate_id in GATE_IDS:
        if gate_id not in results:
            raise GateError("matrix missing gate %s" % gate_id)
    g2 = results["G2"].status
    # Authenticated-claim gates cannot pass without G2 VERIFIED.
    for gate_id in ("G3", "G6"):
        if results[gate_id].status in ("VERIFIED", "PARTIAL"):
            if g2 != "VERIFIED":
                raise GateError(
                    "gate %s %s without G2 VERIFIED is a forbidden "
                    "cross-gate inference" % (gate_id,
                                              results[gate_id].status))
    # Contract-authenticated claims cannot pass without G2 VERIFIED
    # when the result depended on authenticated access.
    g4 = results["G4"]
    if (g4.status in ("VERIFIED", "PARTIAL")
            and "authenticated_source" in g4.observed_evidence
            and g2 != "VERIFIED"):
        raise GateError("G4 authenticated claim without G2 VERIFIED")
    # Economics claims requiring contract identity need G4 VERIFIED.
    g5 = results["G5"]
    if (g5.status in ("VERIFIED", "PARTIAL")
            and "contract_identity_required" in g5.observed_evidence
            and results["G4"].status != "VERIFIED"):
        raise GateError("G5 contract-dependent claim without G4 VERIFIED")
    # Lifecycle claims need the full external triple.
    if results["G6"].status in ("VERIFIED", "PARTIAL"):
        for need in ("G2", "G3", "G4"):
            if results[need].status != "VERIFIED":
                raise GateError(
                    "G6 %s without %s VERIFIED"
                    % (results["G6"].status, need))
    # Reconciliation VERIFIED forbids mismatched domains.
    g7 = results["G7"]
    if g7.status == "VERIFIED" and any(
            token in g7.observed_evidence
            for token in ("account=MISMATCH", "contract=MISMATCH",
                          "economics=MISMATCH", "lifecycle=MISMATCH")):
        raise GateError("G7 VERIFIED with a MISMATCH domain")
    final = external_final(results)
    if final not in EXTERNAL_FINAL:
        raise GateError("invalid external aggregate %r" % final)
    return final


@dataclasses.dataclass(frozen=True)
class GateMatrix:
    schema_version: str
    matrix_type: str
    matrix_id: str
    identity_algorithm: str
    results: tuple
    domain_summaries: tuple
    external_classification: str
    is_production_ready: bool = False

    def __post_init__(self):
        if self.schema_version != MATRIX_SCHEMA_VERSION:
            raise GateError("schema_version must be %r"
                            % MATRIX_SCHEMA_VERSION)
        if self.matrix_type != MATRIX_TYPE:
            raise GateError("matrix_type must be %r" % MATRIX_TYPE)
        if self.identity_algorithm != MATRIX_IDENTITY_ALGORITHM:
            raise GateError("identity_algorithm must be %r"
                            % MATRIX_IDENTITY_ALGORITHM)
        ordered = tuple(self.results)
        object.__setattr__(self, "results", ordered)
        by_id = {}
        for item in ordered:
            if not isinstance(item, GateResult):
                raise GateError("results must be GateResult")
            if item.gate_id in by_id:
                raise GateError("duplicate gate %s" % item.gate_id)
            by_id[item.gate_id] = item
        if set(by_id) != set(GATE_IDS) or len(by_id) != len(GATE_IDS):
            raise GateError("matrix must cover exactly G0-G14")
        if tuple(r.gate_id for r in ordered) != GATE_IDS:
            raise GateError("matrix results must be ordered G0-G14")
        domains = tuple(self.domain_summaries)
        object.__setattr__(self, "domain_summaries", domains)
        expected_domains = tuple(name for name, _ in DOMAINS)
        if tuple(d["domain"] for d in domains) != expected_domains:
            raise GateError("domain summaries must follow DOMAINS order")
        for entry in domains:
            if entry["status"] not in GATE_STATUS + ("PARTIAL",):
                raise GateError("bad domain status %r"
                                % entry["status"])
        external = validate_matrix(by_id)
        if self.external_classification != external:
            raise GateError(
                "external_classification %r does not match derived %r"
                % (self.external_classification, external))
        if self.is_production_ready is not False:
            raise GateError("matrix is_production_ready must be False")
        expected = content_hash(self._identity_payload())
        if self.matrix_id != expected:
            raise GateError("matrix_id mismatch (expected %s)" % expected)

    @staticmethod
    def _identity_payload_for(results, domain_summaries,
                              external_classification):
        # Identity covers verdicts only: statuses, execution states,
        # prerequisite sets, missing/blocking items, domain verdicts,
        # and the aggregate. Volatile observation values (counts,
        # timestamps) live in observed_evidence/limitations text and
        # are excluded so identical verdicts stay identical.
        payload_results = []
        for item in results:
            payload_results.append({
                "gate_id": item.gate_id,
                "status": item.status,
                "execution_state": item.execution_state,
                "prerequisites": list(item.prerequisites),
                "satisfied_prerequisites":
                    list(item.satisfied_prerequisites),
                "missing_prerequisites":
                    list(item.missing_prerequisites),
                "required_evidence": list(item.required_evidence),
                "missing_evidence": list(item.missing_evidence),
                "blocking_reasons": list(item.blocking_reasons),
            })
        return {
            "schema_version": MATRIX_SCHEMA_VERSION,
            "matrix_type": MATRIX_TYPE,
            "results": payload_results,
            "domain_summaries": [
                {"domain": d["domain"], "status": d["status"]}
                for d in domain_summaries
            ],
            "external_classification": external_classification,
        }

    def _identity_payload(self):
        return self._identity_payload_for(
            self.results, self.domain_summaries,
            self.external_classification)

    @classmethod
    def create(cls, results, notes=()):
        ordered = tuple(results)
        by_id = {r.gate_id: r for r in ordered}
        domains = tuple(
            {"domain": name,
             "status": _domain_status(gates, by_id),
             "notes": list(notes.get(name, ())
                           if isinstance(notes, dict) else [])}
            for name, gates in DOMAINS
        )
        external = external_final(by_id)
        matrix_id = content_hash(cls._identity_payload_for(
            ordered, domains, external))
        return cls(
            schema_version=MATRIX_SCHEMA_VERSION,
            matrix_type=MATRIX_TYPE,
            matrix_id=matrix_id,
            identity_algorithm=MATRIX_IDENTITY_ALGORITHM,
            results=ordered,
            domain_summaries=domains,
            external_classification=external,
            is_production_ready=False,
        )

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "matrix_type": self.matrix_type,
            "matrix_id": self.matrix_id,
            "identity_algorithm": self.identity_algorithm,
            "results": [r.to_dict() for r in self.results],
            "domain_summaries": [
                {"domain": d["domain"], "status": d["status"],
                 "notes": list(d["notes"])}
                for d in self.domain_summaries
            ],
            "external_classification": self.external_classification,
            "is_production_ready": False,
        }
