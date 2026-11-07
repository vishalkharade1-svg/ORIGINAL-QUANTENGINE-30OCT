"""Paper-run evidence readiness: a report label, never a trading permission."""

from __future__ import annotations

from dataclasses import dataclass

from core.risk.costs import CostSpec, paper_cost_profile, paper_profile_name, paper_venue_realistic


@dataclass(frozen=True, slots=True)
class PaperReadiness:
    ready: bool
    status: str
    reason: str
    profile_name: str
    costs: CostSpec


def assess_paper_readiness(*, costs: CostSpec | None = None, profile_name: str | None = None, venue_realistic: bool | None = None) -> PaperReadiness:
    """Declare whether a paper result may be used as operational evidence.

    This does not authorize live orders and does not claim strategy profit. A
    configured nonzero cost alone is insufficient without an explicit
    provenance flag that says the profile was verified for the venue.
    """
    costs = costs if costs is not None else paper_cost_profile()
    profile_name = profile_name if profile_name is not None else paper_profile_name()
    venue_realistic = paper_venue_realistic() if venue_realistic is None else bool(venue_realistic)
    if not venue_realistic:
        return PaperReadiness(False, "NOT_EVIDENCE_READY", "venue-realistic cost profile is not verified", profile_name, costs)
    if costs.per_trade == 0 and costs.rate == 0 and costs.slippage_bps == 0:
        return PaperReadiness(False, "NOT_EVIDENCE_READY", "verified profile contains no modeled trading costs", profile_name, costs)
    return PaperReadiness(True, "READY", "venue-realistic costs declared", profile_name, costs)
