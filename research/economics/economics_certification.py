"""Fail-closed gate for venue-economics OOS certification.

A certificate is only admissible when every required economics domain has
real evidence. A point-in-time order-book snapshot is deliberately not enough
to certify historical spread/slippage across an OOS period.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class EconomicsCertification:
    status: str
    reasons: tuple[str, ...]
    fee_evidence_sha256: str | None = None
    funding_evidence_sha256: str | None = None
    market_friction_evidence_sha256: str | None = None

    @property
    def certifiable(self) -> bool:
        return self.status == "CERTIFIABLE"


def assess(*, fee_artifact=None, funding_artifact=None,
           market_friction_artifact=None, realized_fill_artifact=None) -> EconomicsCertification:
    reasons = []
    fee_sha = getattr(fee_artifact, "evidence_sha256", None)
    funding_sha = getattr(funding_artifact, "funding_evidence_sha256", None)
    friction_sha = getattr(market_friction_artifact, "evidence_sha256", None)

    if fee_artifact is None or getattr(fee_artifact, "provenance_status", "UNKNOWN") != "REAL":
        reasons.append("real venue fee evidence is missing")
    if funding_artifact is None or getattr(funding_artifact, "provenance_status", "UNKNOWN") != "REAL":
        reasons.append("real venue funding evidence is missing")
    if realized_fill_artifact is None or getattr(realized_fill_artifact, "provenance_status", "UNKNOWN") != "REAL":
        reasons.append("realized fill/slippage evidence is missing")
    if market_friction_artifact is None:
        reasons.append("historical market-friction evidence is missing")
    elif getattr(market_friction_artifact, "provenance_status", "UNKNOWN") != "REAL":
        reasons.append("historical market-friction evidence is not genuine venue evidence")
    elif getattr(market_friction_artifact, "has_realized_fill_evidence", False):
        # This is useful evidence, but it does not replace a separately
        # authenticated fill/commission record required by the certification gate.
        reasons.append("time-aligned friction artifact contains fills but is not a realized venue-fill ledger")

    # A single order-book snapshot can document spread but cannot establish
    # OOS execution costs. Keep this distinction explicit in the gate.
    if market_friction_artifact is not None and not realized_fill_artifact:
        reasons.append("market-state spread evidence is not realized slippage evidence")

    return EconomicsCertification(
        status="CERTIFIABLE" if not reasons else "BLOCKED",
        reasons=tuple(reasons), fee_evidence_sha256=fee_sha,
        funding_evidence_sha256=funding_sha, market_friction_evidence_sha256=friction_sha,
    )
