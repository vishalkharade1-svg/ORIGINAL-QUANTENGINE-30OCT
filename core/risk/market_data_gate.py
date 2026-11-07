"""Pure fail-closed data-quality precondition for future risk decisions."""

from __future__ import annotations

from dataclasses import dataclass

from data.delta.capabilities import assess_capabilities
from data.delta.market_state_store import AuthoritativeMarketState


@dataclass(frozen=True, slots=True)
class MarketDataGateDecision:
    allowed: bool
    reason: str


def evaluate_market_data(state: AuthoritativeMarketState | None, *, require_volume: bool = True) -> MarketDataGateDecision:
    """Never authorize a trade from missing or known-insufficient market state."""
    if state is None or state.data_quality is None:
        return MarketDataGateDecision(False, "MARKET_DATA_UNAVAILABLE")
    quality = state.data_quality
    if quality.stale is True:
        return MarketDataGateDecision(False, "MARKET_DATA_STALE")
    if quality.gap_status != "CONTINUOUS":
        return MarketDataGateDecision(False, "MARKET_DATA_GAP_OR_UNKNOWN")
    if require_volume and assess_capabilities(state).volume_analysis.status != "AVAILABLE":
        return MarketDataGateDecision(False, "MARKET_DATA_VOLUME_UNAVAILABLE")
    return MarketDataGateDecision(True, "MARKET_DATA_ACCEPTED")
