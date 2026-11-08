"""Runtime-facing, paper-only production hardening controls for Stages 12–15.

These adapters make evidence usable by paper operations without granting live
execution authority. They never read secrets, call a venue, or submit orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from core.risk.costs import CostSpec

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ZERO_HASH = "0" * 64
_SENSITIVE_KEY = re.compile(
    r"(api.?key|api.?secret|password|passwd|access.?token|refresh.?token|"
    r"private.?key|authorization|cookie|credential.?value)",
    re.IGNORECASE,
)


def _parse_utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s is required" % label)
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("%s must include a UTC offset" % label)
    return parsed.astimezone(timezone.utc)


def _finite_nonnegative(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("%s must be finite and non-negative" % name)
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("%s must be finite and non-negative" % name)
    if not math.isfinite(result) or result < 0:
        raise ValueError("%s must be finite and non-negative" % name)
    return result


@dataclass(frozen=True)
class CostProfileActivationEvidence:
    profile_id: str
    version: str
    venue: str
    instrument: str
    per_trade: float
    rate: float
    slippage_bps: float
    source_ref: str
    observed_at_utc: str
    valid_until_utc: str
    independent_review_ref: str
    venue_verified: bool = False
    venue_verification_ref: str = ""
    zero_cost_provenance_ref: str = ""


@dataclass(frozen=True)
class CostProfileActivation:
    stage: int
    status: str
    cost_spec: CostSpec | None
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def activate_cost_profile(
    evidence: CostProfileActivationEvidence,
    *,
    expected_venue: str,
    expected_instrument: str,
    evaluated_at_utc: str,
) -> CostProfileActivation:
    """Build a scoped CostSpec; unverified profiles remain simulation-only.

    A non-empty CostSpec.venue_source is minted only when the caller supplies
    an explicit venue-verification reference. That reference is still an
    external attestation, not something this pure function independently
    authenticates. Missing/expired/mismatched inputs block with no fallback.
    """
    reasons: list[str] = []
    for label, value in (
        ("profile_id", evidence.profile_id),
        ("version", evidence.version),
        ("venue", evidence.venue),
        ("instrument", evidence.instrument),
        ("source_ref", evidence.source_ref),
        ("independent_review_ref", evidence.independent_review_ref),
    ):
        if not isinstance(value, str) or not value.strip():
            reasons.append("%s is required" % label)
    if evidence.venue != expected_venue:
        reasons.append("venue scope mismatch")
    if evidence.instrument != expected_instrument:
        reasons.append("instrument scope mismatch")
    if evidence.venue_verified is not True and evidence.venue_verified is not False:
        reasons.append("venue_verified must be a boolean")
    if not isinstance(evidence.venue_verification_ref, str):
        reasons.append("venue_verification_ref must be a string")
    elif evidence.venue_verified is True and not evidence.venue_verification_ref.strip():
        reasons.append("venue verification reference is required")
    elif evidence.venue_verified is False and evidence.venue_verification_ref.strip():
        reasons.append("verification reference supplied while venue_verified is false")
    if not isinstance(evidence.zero_cost_provenance_ref, str):
        reasons.append("zero_cost_provenance_ref must be a string")
    try:
        per_trade = _finite_nonnegative("per_trade", evidence.per_trade)
        rate = _finite_nonnegative("rate", evidence.rate)
        slippage_bps = _finite_nonnegative("slippage_bps", evidence.slippage_bps)
        if (per_trade == 0 or rate == 0 or slippage_bps == 0) and not (
            isinstance(evidence.zero_cost_provenance_ref, str)
            and evidence.zero_cost_provenance_ref.strip()
        ):
            reasons.append("explicit provenance is required for every zero cost component")
        observed = _parse_utc(evidence.observed_at_utc, "observed_at_utc")
        valid_until = _parse_utc(evidence.valid_until_utc, "valid_until_utc")
        evaluated = _parse_utc(evaluated_at_utc, "evaluated_at_utc")
        if valid_until <= observed:
            reasons.append("profile validity window is empty or inverted")
        if evaluated < observed:
            reasons.append("profile observation is in the future")
        if evaluated >= valid_until:
            reasons.append("cost profile is expired")
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))
        per_trade = rate = slippage_bps = 0.0
    if reasons:
        return CostProfileActivation(12, "BLOCKED", None, tuple(reasons))
    source = evidence.venue_verification_ref if evidence.venue_verified else ""
    spec = CostSpec(
        per_trade=per_trade,
        rate=rate,
        slippage_bps=slippage_bps,
        known=True,
        venue_source=source,
    )
    status = "VENUE_VERIFIED_COST_PROFILE" if source else "PAPER_SIMULATION_ONLY"
    note = (
        "venue verification reference is operator-supplied and requires external validation"
        if source else
        "profile is scoped and current but not venue-verified; use only for paper simulation"
    )
    return CostProfileActivation(12, status, spec, (note,))


@dataclass(frozen=True)
class DeploymentControlEvidence:
    release_assessment_stage: int
    release_assessment_status: str
    release_assessment_live_arming_permitted: bool
    independent_review_ref: str
    strategy_digest: str
    deployment_digest: str
    rollback_artifact_ref: str
    paper_dry_run_ref: str
    kill_switch_tested: bool


@dataclass(frozen=True)
class DeploymentControlAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def evaluate_paper_deployment(evidence: DeploymentControlEvidence) -> DeploymentControlAssessment:
    reasons: list[str] = []
    if evidence.release_assessment_stage != 11:
        reasons.append("Stage 11 assessment identity mismatch")
    if evidence.release_assessment_status != "READY_FOR_INDEPENDENT_RELEASE_REVIEW":
        reasons.append("Stage 11 is not ready for independent review")
    if evidence.release_assessment_live_arming_permitted is not False:
        reasons.append("Stage 11 must explicitly deny live arming")
    for label, value in (
        ("independent review reference", evidence.independent_review_ref),
        ("strategy digest", evidence.strategy_digest),
        ("deployment digest", evidence.deployment_digest),
        ("rollback artifact reference", evidence.rollback_artifact_ref),
        ("paper dry-run reference", evidence.paper_dry_run_ref),
    ):
        if not isinstance(value, str) or not value.strip():
            reasons.append("%s is missing" % label)
    if not isinstance(evidence.strategy_digest, str) or not _SHA256.fullmatch(evidence.strategy_digest):
        reasons.append("strategy digest must be a lowercase SHA-256")
    if not isinstance(evidence.deployment_digest, str) or not _SHA256.fullmatch(evidence.deployment_digest):
        reasons.append("deployment digest must be a lowercase SHA-256")
    if evidence.strategy_digest != evidence.deployment_digest:
        reasons.append("deployment digest differs from reviewed strategy digest")
    if evidence.kill_switch_tested is not True:
        reasons.append("kill switch has not passed its paper drill")
    if reasons:
        return DeploymentControlAssessment(13, "BLOCKED", tuple(reasons))
    return DeploymentControlAssessment(
        13,
        "PAPER_DEPLOYMENT_READY",
        ("paper-only deployment controls are complete; this is not live authorization",),
    )


@dataclass(frozen=True)
class AuditChainAssessment:
    valid: bool
    records_verified: int
    head_sha256: str
    reasons: tuple[str, ...]


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reject_sensitive_keys(value: Any, path: str = "attributes") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _SENSITIVE_KEY.search(str(key)):
                raise ValueError("sensitive field name is prohibited: %s.%s" % (path, key))
            _reject_sensitive_keys(child, "%s.%s" % (path, key))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, "%s[%d]" % (path, index))


def make_audit_record(
    *,
    sequence: int,
    previous_sha256: str,
    occurred_at_utc: str,
    event_type: str,
    attributes: Mapping[str, Any],
) -> dict[str, Any]:
    """Create one deterministic hash-linked audit record (no persistence)."""
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("sequence must be a positive integer")
    expected_previous = _ZERO_HASH if sequence == 1 else previous_sha256
    if not isinstance(expected_previous, str) or not _SHA256.fullmatch(expected_previous):
        raise ValueError("previous_sha256 must be a lowercase SHA-256")
    if sequence == 1 and previous_sha256 != _ZERO_HASH:
        raise ValueError("first record must use the zero hash")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event_type is required")
    if not isinstance(attributes, Mapping):
        raise ValueError("attributes must be a mapping")
    _parse_utc(occurred_at_utc, "occurred_at_utc")
    _reject_sensitive_keys(attributes)
    safe_attributes = json.loads(_canonical_bytes(attributes).decode("utf-8"))
    body = {
        "sequence": sequence,
        "previous_sha256": previous_sha256,
        "occurred_at_utc": occurred_at_utc,
        "event_type": event_type.strip(),
        "attributes": safe_attributes,
    }
    digest = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    return {**body, "sha256": digest}


def verify_audit_chain(records: Iterable[Mapping[str, Any]]) -> AuditChainAssessment:
    """Verify contiguous sequence, previous-hash links, and every record digest."""
    previous = _ZERO_HASH
    verified = 0
    reasons: list[str] = []
    for expected_sequence, record in enumerate(records, start=1):
        try:
            if record.get("sequence") != expected_sequence:
                raise ValueError("sequence discontinuity at record %d" % expected_sequence)
            if record.get("previous_sha256") != previous:
                raise ValueError("previous-hash mismatch at record %d" % expected_sequence)
            supplied = record.get("sha256")
            body = {key: record[key] for key in (
                "sequence", "previous_sha256", "occurred_at_utc", "event_type", "attributes"
            )}
            _parse_utc(body["occurred_at_utc"], "occurred_at_utc")
            _reject_sensitive_keys(body["attributes"])
            actual = hashlib.sha256(_canonical_bytes(body)).hexdigest()
            if supplied != actual:
                raise ValueError("record digest mismatch at record %d" % expected_sequence)
            previous = actual
            verified += 1
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append(str(exc))
            break
    return AuditChainAssessment(not reasons, verified, previous, tuple(reasons))


@dataclass(frozen=True)
class PaperCanaryEvidence:
    canary_id: str
    started_at_utc: str
    ended_at_utc: str
    evaluated_at_utc: str
    minimum_samples: int
    observed_samples: int
    max_latency_ms: float
    latency_budget_ms: float
    data_gap_count: int
    exchange_write_count: int
    rejected_order_count: int
    max_rejected_orders: int
    realized_loss: float
    loss_budget: float
    kill_switch_tested: bool
    rollback_artifact_ref: str


@dataclass(frozen=True)
class PaperCanaryAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def evaluate_paper_canary(evidence: PaperCanaryEvidence) -> PaperCanaryAssessment:
    """Evaluate a bounded paper canary; any exchange write forces rollback."""
    holds: list[str] = []
    breaches: list[str] = []
    if not isinstance(evidence.canary_id, str) or not evidence.canary_id.strip():
        holds.append("canary_id is required")
    try:
        started = _parse_utc(evidence.started_at_utc, "started_at_utc")
        ended = _parse_utc(evidence.ended_at_utc, "ended_at_utc")
        evaluated = _parse_utc(evidence.evaluated_at_utc, "evaluated_at_utc")
        if ended <= started:
            holds.append("canary time window must be positive")
        if evaluated < ended:
            holds.append("canary cannot be evaluated before it ends")
    except (TypeError, ValueError) as exc:
        holds.append(str(exc))
    count_values = (
        ("minimum_samples", evidence.minimum_samples),
        ("observed_samples", evidence.observed_samples),
        ("data_gap_count", evidence.data_gap_count),
        ("exchange_write_count", evidence.exchange_write_count),
        ("rejected_order_count", evidence.rejected_order_count),
        ("max_rejected_orders", evidence.max_rejected_orders),
    )
    counts_valid = True
    for name, value in count_values:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            holds.append("%s must be a non-negative integer" % name)
            counts_valid = False
    try:
        latency = _finite_nonnegative("max_latency_ms", evidence.max_latency_ms)
        latency_budget = _finite_nonnegative("latency_budget_ms", evidence.latency_budget_ms)
        loss = _finite_nonnegative("realized_loss", evidence.realized_loss)
        loss_budget = _finite_nonnegative("loss_budget", evidence.loss_budget)
        if latency_budget <= 0:
            holds.append("latency_budget_ms must be positive")
    except ValueError as exc:
        holds.append(str(exc))
        latency = latency_budget = loss = loss_budget = 0.0
    if not isinstance(evidence.rollback_artifact_ref, str) or not evidence.rollback_artifact_ref.strip():
        holds.append("rollback artifact reference is required")
    if evidence.kill_switch_tested is not True:
        holds.append("kill switch paper drill is not attested")
    if counts_valid:
        if evidence.observed_samples < evidence.minimum_samples:
            holds.append("minimum paper sample count not reached")
        if evidence.exchange_write_count > 0:
            breaches.append("exchange write detected; immediate rollback required")
        if evidence.data_gap_count > 0:
            breaches.append("market-data gap detected")
    if latency_budget > 0 and latency > latency_budget:
        breaches.append("latency budget exceeded")
    if counts_valid and evidence.rejected_order_count > evidence.max_rejected_orders:
        breaches.append("paper order rejection budget exceeded")
    if loss > loss_budget:
        breaches.append("paper loss budget exceeded")
    if breaches:
        return PaperCanaryAssessment(15, "ROLLBACK_REQUIRED", tuple(breaches + holds))
    if holds:
        return PaperCanaryAssessment(15, "HOLD", tuple(holds))
    return PaperCanaryAssessment(
        15,
        "PAPER_CANARY_PASS",
        ("bounded paper canary passed; live execution remains disabled",),
    )


# ---------------------------------------------------------------------------
# Production hardening Stages 16–19: evidence, Testnet drill, monitoring, gate.
# All evaluators are pure/offline and never authorize live execution.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceArtifactDescriptor:
    artifact_id: str
    sha256: str
    source_ref: str


@dataclass(frozen=True)
class EvidencePackageEvidence:
    package_id: str
    scope: str
    issuer_ref: str
    independent_reviewer_ref: str
    source_commit: str
    reviewed_at_utc: str
    valid_until_utc: str
    required_artifact_ids: tuple[str, ...]
    artifacts: tuple[EvidenceArtifactDescriptor, ...]


@dataclass(frozen=True)
class EvidencePackageAssessment:
    stage: int
    status: str
    artifact_count: int
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def evaluate_evidence_package(
    evidence: EvidencePackageEvidence, *, expected_scope: str, evaluated_at_utc: str
) -> EvidencePackageAssessment:
    """Validate a complete, scoped evidence index without claiming authenticity."""
    reasons: list[str] = []
    for label, value in (
        ("package_id", evidence.package_id), ("scope", evidence.scope),
        ("issuer_ref", evidence.issuer_ref),
        ("independent_reviewer_ref", evidence.independent_reviewer_ref),
        ("source_commit", evidence.source_commit),
    ):
        if not isinstance(value, str) or not value.strip():
            reasons.append("%s is required" % label)
    if evidence.scope != expected_scope:
        reasons.append("evidence package scope mismatch")
    if evidence.issuer_ref == evidence.independent_reviewer_ref:
        reasons.append("issuer and independent reviewer must be distinct")
    if not isinstance(evidence.source_commit, str) or not _SHA256.fullmatch(evidence.source_commit):
        reasons.append("source_commit must be a lowercase SHA-256")
    try:
        reviewed = _parse_utc(evidence.reviewed_at_utc, "reviewed_at_utc")
        expires = _parse_utc(evidence.valid_until_utc, "valid_until_utc")
        evaluated = _parse_utc(evaluated_at_utc, "evaluated_at_utc")
        if expires <= reviewed:
            reasons.append("evidence validity window is empty or inverted")
        if evaluated < reviewed:
            reasons.append("evidence review timestamp is in the future")
        if evaluated >= expires:
            reasons.append("evidence package is expired")
    except (TypeError, ValueError) as exc:
        reasons.append(str(exc))
    required = evidence.required_artifact_ids
    artifacts = evidence.artifacts
    if not isinstance(required, tuple) or not required or any(
        not isinstance(item, str) or not item.strip() for item in required
    ):
        reasons.append("required_artifact_ids must be a non-empty tuple of identifiers")
        required = ()
    if len(set(required)) != len(required):
        reasons.append("required artifact identifiers contain duplicates")
    seen: set[str] = set()
    if not isinstance(artifacts, tuple):
        reasons.append("artifacts must be a tuple")
        artifacts = ()
    for artifact in artifacts:
        if not isinstance(artifact, EvidenceArtifactDescriptor):
            reasons.append("artifact descriptor has an invalid type")
            continue
        if not artifact.artifact_id or artifact.artifact_id in seen:
            reasons.append("artifact identifiers must be non-empty and unique")
        seen.add(artifact.artifact_id)
        if not isinstance(artifact.sha256, str) or not _SHA256.fullmatch(artifact.sha256):
            reasons.append("artifact %s has an invalid SHA-256" % artifact.artifact_id)
        if not isinstance(artifact.source_ref, str) or not artifact.source_ref.strip():
            reasons.append("artifact %s is missing its source reference" % artifact.artifact_id)
    if set(required) - seen:
        reasons.append("required evidence artifacts are missing")
    if reasons:
        return EvidencePackageAssessment(16, "BLOCKED", len(artifacts), tuple(reasons))
    return EvidencePackageAssessment(
        16, "EVIDENCE_INDEX_COMPLETE_UNAUTHENTICATED", len(artifacts),
        ("artifact hashes are declarations; retrieve and independently authenticate source artifacts",),
    )


@dataclass(frozen=True)
class TestnetDrillEvidence:
    drill_id: str
    environment: str
    started_at_utc: str
    ended_at_utc: str
    evaluated_at_utc: str
    stage16_status: str
    read_only_probe_ref: str
    market_data_stream_ref: str
    write_guard_test_ref: str
    reconciliation_ref: str
    restart_recovery_ref: str
    observed_samples: int
    minimum_samples: int
    exchange_write_count: int
    unresolved_reconciliation_count: int
    restart_recovery_passed: bool


@dataclass(frozen=True)
class TestnetDrillAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def evaluate_testnet_drill(evidence: TestnetDrillEvidence) -> TestnetDrillAssessment:
    """Assess operator-supplied Testnet drill evidence; does not contact a venue."""
    holds: list[str] = []
    breaches: list[str] = []
    if evidence.environment != "DELTA_INDIA_TESTNET":
        holds.append("environment must be explicitly DELTA_INDIA_TESTNET")
    if evidence.stage16_status != "EVIDENCE_INDEX_COMPLETE_UNAUTHENTICATED":
        holds.append("Stage 16 evidence index is not complete")
    for label, value in (
        ("drill_id", evidence.drill_id),
        ("read-only probe reference", evidence.read_only_probe_ref),
        ("market-data stream reference", evidence.market_data_stream_ref),
        ("write-guard test reference", evidence.write_guard_test_ref),
        ("reconciliation reference", evidence.reconciliation_ref),
        ("restart-recovery reference", evidence.restart_recovery_ref),
    ):
        if not isinstance(value, str) or not value.strip():
            holds.append("%s is required" % label)
    try:
        started = _parse_utc(evidence.started_at_utc, "started_at_utc")
        ended = _parse_utc(evidence.ended_at_utc, "ended_at_utc")
        evaluated = _parse_utc(evidence.evaluated_at_utc, "evaluated_at_utc")
        if ended <= started:
            holds.append("Testnet drill window must be positive")
        if evaluated < ended:
            holds.append("drill cannot be evaluated before it ends")
    except (TypeError, ValueError) as exc:
        holds.append(str(exc))
    for label, value in (
        ("observed_samples", evidence.observed_samples),
        ("minimum_samples", evidence.minimum_samples),
        ("exchange_write_count", evidence.exchange_write_count),
        ("unresolved_reconciliation_count", evidence.unresolved_reconciliation_count),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            holds.append("%s must be a non-negative integer" % label)
    if isinstance(evidence.observed_samples, int) and isinstance(evidence.minimum_samples, int):
        if evidence.observed_samples < evidence.minimum_samples:
            holds.append("minimum Testnet observation sample count not reached")
    if evidence.exchange_write_count != 0:
        breaches.append("exchange write observed; Testnet drill failed closed")
    if evidence.unresolved_reconciliation_count != 0:
        breaches.append("unresolved reconciliation remains")
    if evidence.restart_recovery_passed is not True:
        holds.append("restart recovery drill did not pass")
    if breaches:
        return TestnetDrillAssessment(17, "DRILL_FAILED", tuple(breaches + holds))
    if holds:
        return TestnetDrillAssessment(17, "HOLD", tuple(holds))
    return TestnetDrillAssessment(
        17, "TESTNET_DRILL_EVIDENCE_COMPLETE_UNVERIFIED",
        ("operator-supplied drill evidence requires independent venue-side validation",),
    )


@dataclass(frozen=True)
class OperationalMonitorEvidence:
    observed_at_utc: str
    evaluated_at_utc: str
    max_age_seconds: int
    data_age_seconds: int
    latency_ms: float
    latency_budget_ms: float
    clock_skew_ms: float
    clock_skew_budget_ms: float
    data_gap_count: int
    position_mismatch_count: int
    unresolved_order_count: int
    audit_chain_valid: bool
    kill_switch_tested: bool


@dataclass(frozen=True)
class OperationalMonitorAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def evaluate_operational_monitor(
    evidence: OperationalMonitorEvidence,
) -> OperationalMonitorAssessment:
    """Evaluate a monitor snapshot. Breaches halt paper operations; no live authority."""
    holds: list[str] = []
    breaches: list[str] = []
    try:
        observed = _parse_utc(evidence.observed_at_utc, "observed_at_utc")
        evaluated = _parse_utc(evidence.evaluated_at_utc, "evaluated_at_utc")
        if evaluated < observed:
            holds.append("monitor observation is in the future")
    except (TypeError, ValueError) as exc:
        holds.append(str(exc))
    for label, value in (
        ("max_age_seconds", evidence.max_age_seconds),
        ("data_age_seconds", evidence.data_age_seconds),
        ("data_gap_count", evidence.data_gap_count),
        ("position_mismatch_count", evidence.position_mismatch_count),
        ("unresolved_order_count", evidence.unresolved_order_count),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            holds.append("%s must be a non-negative integer" % label)
    try:
        latency = _finite_nonnegative("latency_ms", evidence.latency_ms)
        latency_budget = _finite_nonnegative("latency_budget_ms", evidence.latency_budget_ms)
        skew = _finite_nonnegative("clock_skew_ms", evidence.clock_skew_ms)
        skew_budget = _finite_nonnegative("clock_skew_budget_ms", evidence.clock_skew_budget_ms)
        if latency_budget <= 0 or skew_budget <= 0:
            holds.append("latency and clock-skew budgets must be positive")
    except ValueError as exc:
        holds.append(str(exc))
        latency = latency_budget = skew = skew_budget = 0.0
    if isinstance(evidence.data_age_seconds, int) and isinstance(evidence.max_age_seconds, int):
        if evidence.data_age_seconds > evidence.max_age_seconds:
            breaches.append("market data is stale")
    if isinstance(evidence.data_gap_count, int) and evidence.data_gap_count > 0:
        breaches.append("market-data gap detected")
    if isinstance(evidence.position_mismatch_count, int) and evidence.position_mismatch_count > 0:
        breaches.append("position reconciliation mismatch detected")
    if isinstance(evidence.unresolved_order_count, int) and evidence.unresolved_order_count > 0:
        breaches.append("unresolved order detected")
    if latency_budget > 0 and latency > latency_budget:
        breaches.append("latency budget exceeded")
    if skew_budget > 0 and skew > skew_budget:
        breaches.append("clock-skew budget exceeded")
    if evidence.audit_chain_valid is not True:
        breaches.append("audit chain is invalid")
    if evidence.kill_switch_tested is not True:
        holds.append("kill switch test is not attested")
    if breaches:
        return OperationalMonitorAssessment(18, "HALT_PAPER_OPERATIONS", tuple(breaches + holds))
    if holds:
        return OperationalMonitorAssessment(18, "HOLD", tuple(holds))
    return OperationalMonitorAssessment(
        18, "PAPER_MONITORING_HEALTHY",
        ("monitor snapshot passed configured paper-operation limits",),
    )


@dataclass(frozen=True)
class ControlledReviewEvidence:
    stage16_status: str
    stage17_status: str
    stage18_status: str
    stage4_lineage_verified: bool
    full_regression_passed: bool
    oos_certification_ref: str
    independent_oos_review_ref: str
    rr_policy_reconciled: bool
    owner_approval_ref: str
    strategy_digest: str
    deployment_digest: str


@dataclass(frozen=True)
class ControlledReviewAssessment:
    stage: int
    status: str
    reasons: tuple[str, ...]
    live_arming_permitted: bool = False


def evaluate_controlled_review(evidence: ControlledReviewEvidence) -> ControlledReviewAssessment:
    """Final evidence gate; strongest state is review-only, never live authorization."""
    reasons: list[str] = []
    expected = (
        ("Stage 16", evidence.stage16_status, "EVIDENCE_INDEX_COMPLETE_UNAUTHENTICATED"),
        ("Stage 17", evidence.stage17_status, "TESTNET_DRILL_EVIDENCE_COMPLETE_UNVERIFIED"),
        ("Stage 18", evidence.stage18_status, "PAPER_MONITORING_HEALTHY"),
    )
    for label, actual, required in expected:
        if actual != required:
            reasons.append("%s prerequisite is not satisfied" % label)
    for label, value in (
        ("Stage 4 Git lineage verification", evidence.stage4_lineage_verified),
        ("full regression", evidence.full_regression_passed),
        ("RR policy reconciliation", evidence.rr_policy_reconciled),
    ):
        if value is not True:
            reasons.append("%s is not verified" % label)
    for label, value in (
        ("OOS certification reference", evidence.oos_certification_ref),
        ("independent OOS review reference", evidence.independent_oos_review_ref),
        ("owner approval reference", evidence.owner_approval_ref),
    ):
        if not isinstance(value, str) or not value.strip():
            reasons.append("%s is missing" % label)
    if evidence.oos_certification_ref == evidence.independent_oos_review_ref:
        reasons.append("OOS certification and independent review must be distinct")
    for label, value in (
        ("strategy_digest", evidence.strategy_digest),
        ("deployment_digest", evidence.deployment_digest),
    ):
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            reasons.append("%s must be a lowercase SHA-256" % label)
    if evidence.strategy_digest != evidence.deployment_digest:
        reasons.append("strategy and deployment digests differ")
    if reasons:
        return ControlledReviewAssessment(19, "HOLD", tuple(reasons))
    return ControlledReviewAssessment(
        19, "READY_FOR_CONTROLLED_TESTNET_REVIEW",
        ("independent review only; no deployment, exchange write, or live arming is authorized",),
    )
