"""Fail-closed Phase-10 certification model for operator evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiveReadinessEvidence:
    credentials_rotated_and_history_remediated: bool = False
    public_data_contract_verified: bool = False
    contract_and_cost_semantics_verified: bool = False
    sandbox_order_lifecycle_verified: bool = False
    reconciliation_restart_drill_verified: bool = False
    paper_soak_with_realistic_costs_verified: bool = False
    independent_monitoring_and_rollback_verified: bool = False


@dataclass(frozen=True, slots=True)
class LiveReadinessDecision:
    ready: bool
    status: str
    missing: tuple[str, ...]


_REQUIREMENTS = (
    ("credentials_rotated_and_history_remediated", "CREDENTIAL_ROTATION_AND_HISTORY_REMEDIATION"),
    ("public_data_contract_verified", "PUBLIC_DATA_CONTRACT"),
    ("contract_and_cost_semantics_verified", "CONTRACT_AND_COST_SEMANTICS"),
    ("sandbox_order_lifecycle_verified", "SANDBOX_ORDER_LIFECYCLE"),
    ("reconciliation_restart_drill_verified", "RECONCILIATION_RESTART_DRILL"),
    ("paper_soak_with_realistic_costs_verified", "PAPER_SOAK_REALISTIC_COSTS"),
    ("independent_monitoring_and_rollback_verified", "MONITORING_AND_ROLLBACK"),
)


def assess_live_readiness(evidence: LiveReadinessEvidence) -> LiveReadinessDecision:
    """Return ready only when every operator-verifiable fact is explicit.

    This does not arm execution, contact an exchange, or mint a safety token.
    """
    missing = tuple(label for field, label in _REQUIREMENTS if not getattr(evidence, field))
    return LiveReadinessDecision(
        ready=not missing,
        status="READY_FOR_CANARY_REVIEW" if not missing else "NOT_LIVE_READY",
        missing=missing,
    )
