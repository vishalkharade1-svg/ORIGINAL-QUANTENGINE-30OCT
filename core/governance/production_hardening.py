"""Evidence-only production hardening gates for QuantEngine Stages 8–11.

These pure evaluators do not access credentials, exchange APIs, files, or
execution sinks. They classify operator-supplied evidence without claiming
that external attestations are independently true. No result from this module
can arm live execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class GateAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def _utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s is required" % label)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("%s must include a UTC offset" % label)
    return parsed.astimezone(timezone.utc)


def _missing(values: Iterable[tuple[str, object]]) -> list[str]:
    return [name for name, value in values
            if value is None or (isinstance(value, str) and not value.strip())]


# ---------------------------------------------------------------------------
# Stage 8 — credential incident closure evidence (never handles secret bytes)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CredentialIncidentEvidence:
    old_key_revoked: bool
    provider_revocation_ref: str
    account_activity_reviewed: bool
    account_review_ref: str
    replacement_key_ref: str
    replacement_is_testnet_only: bool
    replacement_is_least_privilege: bool
    secret_store_ref: str
    secret_scan_passed: bool
    independent_review_ref: str
    attested_at_utc: str


def evaluate_credential_incident(evidence: CredentialIncidentEvidence) -> GateAssessment:
    reasons: list[str] = []
    required_refs = (
        ("provider revocation evidence", evidence.provider_revocation_ref),
        ("account activity review evidence", evidence.account_review_ref),
        ("replacement key reference", evidence.replacement_key_ref),
        ("secret-store reference", evidence.secret_store_ref),
        ("independent review reference", evidence.independent_review_ref),
    )
    reasons.extend("%s missing" % name for name in _missing(required_refs))
    for attr, label in (
        (evidence.old_key_revoked, "old credential revocation not attested"),
        (evidence.account_activity_reviewed, "account activity review not attested"),
        (evidence.replacement_is_testnet_only, "replacement credential is not attested Testnet-only"),
        (evidence.replacement_is_least_privilege, "least-privilege scope not attested"),
        (evidence.secret_scan_passed, "secret scan has not passed"),
    ):
        if attr is not True:
            reasons.append(label)
    try:
        _utc(evidence.attested_at_utc, "attested_at_utc")
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))
    status = "INCOMPLETE" if reasons else "ATTESTATION_COMPLETE_UNVERIFIED"
    if not reasons:
        reasons.append(
            "operator evidence is structurally complete but provider revocation, "
            "account review, and replacement-key scope require independent verification"
        )
    return GateAssessment(8, status, tuple(reasons))


# ---------------------------------------------------------------------------
# Stage 9 — venue cost evidence (not a production CostSpec until integrated)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VenueCostEvidence:
    profile_id: str
    version: str
    venue: str
    instruments: tuple[str, ...]
    per_trade: float
    rate: float
    slippage_bps: float
    source_ref: str
    observed_at_utc: str
    funding_model_ref: str
    funding_model_integrated: bool
    independent_review_ref: str


def evaluate_venue_cost_evidence(evidence: VenueCostEvidence) -> GateAssessment:
    reasons: list[str] = []
    refs = (
        ("profile_id", evidence.profile_id),
        ("version", evidence.version),
        ("venue", evidence.venue),
        ("source reference", evidence.source_ref),
        ("funding model reference", evidence.funding_model_ref),
        ("independent review reference", evidence.independent_review_ref),
    )
    reasons.extend("%s missing" % name for name in _missing(refs))
    if (not evidence.instruments
            or any(not isinstance(x, str) or not x.strip() for x in evidence.instruments)):
        reasons.append("instrument coverage missing")
    elif len(set(evidence.instruments)) != len(evidence.instruments):
        reasons.append("instrument coverage contains duplicates")
    for name, value in (("per_trade", evidence.per_trade),
                        ("rate", evidence.rate),
                        ("slippage_bps", evidence.slippage_bps)):
        try:
            if isinstance(value, bool):
                raise ValueError
            number = float(value)
            if number < 0 or number != number or number in (float("inf"), float("-inf")):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            reasons.append("%s must be finite and non-negative" % name)
    if evidence.funding_model_integrated is not True:
        reasons.append("funding economics are not integrated into the accounting path")
    try:
        _utc(evidence.observed_at_utc, "observed_at_utc")
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))
    status = "INCOMPLETE" if reasons else "COST_EVIDENCE_COMPLETE_UNVERIFIED"
    if not reasons:
        reasons.append(
            "cost inputs and references are complete; independent venue-source "
            "validation and production accounting integration are still required"
        )
    return GateAssessment(9, status, tuple(reasons))


# ---------------------------------------------------------------------------
# Stage 10 — restart recovery decision (paper-only even when clean)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RestartRecoveryEvidence:
    journal_sha256: str
    schema_version: str
    checkpoint_at_utc: str
    evaluated_at_utc: str
    exchange_snapshot_ref: str
    exchange_snapshot_at_utc: str
    query_complete: bool
    pagination_complete: bool
    balances_complete: bool
    positions_complete: bool
    open_orders_complete: bool
    fills_complete: bool
    local_exchange_identity_match: bool
    state_digest_match: bool
    unresolved_order_count: int
    anomalies: tuple[str, ...] = ()
    kill_switch_active: bool = True
    max_snapshot_age_seconds: int = 60


def evaluate_restart_recovery(evidence: RestartRecoveryEvidence) -> GateAssessment:
    reasons: list[str] = []
    if not _SHA256.fullmatch(str(evidence.journal_sha256 or "")):
        reasons.append("journal digest must be a lowercase SHA-256")
    if not str(evidence.schema_version or "").strip():
        reasons.append("journal schema version missing")
    if not str(evidence.exchange_snapshot_ref or "").strip():
        reasons.append("authoritative exchange snapshot reference missing")
    try:
        evaluated = _utc(evidence.evaluated_at_utc, "evaluated_at_utc")
        checkpoint = _utc(evidence.checkpoint_at_utc, "checkpoint_at_utc")
        exchange = _utc(evidence.exchange_snapshot_at_utc, "exchange_snapshot_at_utc")
        if checkpoint > evaluated:
            reasons.append("journal checkpoint is in the future")
        age = (evaluated - exchange).total_seconds()
        if age < 0:
            reasons.append("exchange snapshot timestamp is in the future")
        elif age > evidence.max_snapshot_age_seconds:
            reasons.append("exchange snapshot is stale")
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))
    checks = (
        (evidence.query_complete, "exchange query is incomplete"),
        (evidence.pagination_complete, "exchange pagination is incomplete"),
        (evidence.balances_complete, "balance snapshot is incomplete"),
        (evidence.positions_complete, "position snapshot is incomplete"),
        (evidence.open_orders_complete, "open-order snapshot is incomplete"),
        (evidence.fills_complete, "fill snapshot is incomplete"),
        (evidence.local_exchange_identity_match, "local/exchange account identity mismatch"),
        (evidence.state_digest_match, "journal/state digest mismatch"),
    )
    reasons.extend(message for passed, message in checks if passed is not True)
    if (not isinstance(evidence.unresolved_order_count, int)
            or isinstance(evidence.unresolved_order_count, bool)
            or evidence.unresolved_order_count != 0):
        reasons.append("unresolved order count must be integer zero")
    if (not isinstance(evidence.max_snapshot_age_seconds, int)
            or isinstance(evidence.max_snapshot_age_seconds, bool)
            or evidence.max_snapshot_age_seconds <= 0):
        reasons.append("maximum snapshot age must be a positive integer")
    if evidence.anomalies:
        reasons.extend("reconciliation anomaly: %s" % item for item in evidence.anomalies)
    if evidence.kill_switch_active is not True:
        reasons.append("kill switch must remain active during recovery")
    if reasons:
        return GateAssessment(10, "BLOCKED", tuple(reasons))
    return GateAssessment(
        10,
        "PAPER_RECOVERY_ONLY",
        ("recovery evidence is internally complete; manual review is still required; "
         "automatic restart and live execution remain disabled",),
    )


# ---------------------------------------------------------------------------
# Stage 11 — aggregate release review (never mints a live authorization token)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReleaseEvidence:
    credential_assessment: GateAssessment
    cost_assessment: GateAssessment
    recovery_assessment: GateAssessment
    rr_policy_reconciled: bool
    source_lineage_verified: bool
    full_regression_green: bool
    oos_certificate_ref: str
    independent_oos_review_ref: str
    frozen_strategy_digest: str
    evaluated_strategy_digest: str
    edge_established_by_oos: bool
    operator_release_approval_ref: str


def evaluate_release_gate(evidence: ReleaseEvidence) -> GateAssessment:
    reasons: list[str] = []
    expected = ((8, evidence.credential_assessment),
                (9, evidence.cost_assessment),
                (10, evidence.recovery_assessment))
    for stage, assessment in expected:
        if assessment.stage != stage:
            reasons.append("stage %d assessment identity mismatch" % stage)
        if assessment.status not in ("ATTESTATION_COMPLETE_UNVERIFIED",
                                     "COST_EVIDENCE_COMPLETE_UNVERIFIED",
                                     "PAPER_RECOVERY_ONLY"):
            reasons.append("stage %d evidence is not complete" % stage)
    for passed, message in (
        (evidence.rr_policy_reconciled, "runtime/research RR policy not reconciled"),
        (evidence.source_lineage_verified, "source lineage not verified"),
        (evidence.full_regression_green, "full regression suite is not green"),
        (evidence.edge_established_by_oos, "strategy edge is not established by OOS evidence"),
    ):
        if not passed:
            reasons.append(message)
    for name, value in (
        ("OOS certificate reference", evidence.oos_certificate_ref),
        ("independent OOS review reference", evidence.independent_oos_review_ref),
        ("frozen strategy digest", evidence.frozen_strategy_digest),
        ("evaluated strategy digest", evidence.evaluated_strategy_digest),
        ("operator release approval reference", evidence.operator_release_approval_ref),
    ):
        if not isinstance(value, str) or not value.strip():
            reasons.append("%s missing" % name)
    if (evidence.frozen_strategy_digest and evidence.evaluated_strategy_digest
            and evidence.frozen_strategy_digest != evidence.evaluated_strategy_digest):
        reasons.append("evaluated strategy digest differs from frozen strategy digest")
    if reasons:
        status = "HOLD"
    else:
        status = "READY_FOR_INDEPENDENT_RELEASE_REVIEW"
        reasons.append(
            "all supplied evidence fields are complete; this evaluator cannot verify "
            "external attestations or authorize live execution"
        )
    return GateAssessment(11, status, tuple(reasons), live_arming_permitted=False)
