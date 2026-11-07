"""
====================================================

QuantEngine

Research Journal -- setup record (Phase 9A)

Frozen factual snapshot of a discovered setup (SetupCandidate
facts). Records the canonical identity, frozen economics, the
eligibility / structural decision, and -- critically -- ALL
applicable rejection reasons verbatim (never a generic
"REJECTED").

OBSERVED FACTS ONLY. Optional fields remain optional (None / "")
when the source system did not provide them; nothing is
fabricated.
====================================================
"""

from dataclasses import dataclass, field

from core.research.journal.research_enums import (
    Provenance,
    SetupLifecycle,
)


@dataclass
class SetupRecord:
    """Factual record of a discovered / eligible / rejected setup."""

    provenance: str = Provenance.BACKTEST.value
    exchange: str = ""
    instrument_id: str = ""
    timeframe: str = ""
    direction: str = ""
    strategy: str = ""
    setup_id: str = ""
    structural_id: str = ""
    economic_fingerprint: str = ""
    canonical_id: str = ""

    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward: float = 0.0
    atr: float = 0.0
    entry_distance: float = 0.0
    entry_distance_atr: float = 0.0
    observed_price: float = 0.0
    score: float = 0.0
    confidence: float = 0.0
    entry_mode: str = ""

    lifecycle: str = SetupLifecycle.DISCOVERED.value
    structurally_valid: bool = True
    trade_eligible: bool = True
    entry_rejection_reason: str = ""
    # ALL applicable rejection reasons, preserved verbatim.
    rejection_reasons: list = field(default_factory=list)
    zone_diagnostics: list = field(default_factory=list)
    zone_freshness: str = ""
    zone_age_bars: int = 0
    is_economic_duplicate: bool = False

    bar: int = 0
    timestamp: object = None

    @property
    def rejected(self):
        return self.lifecycle == SetupLifecycle.REJECTED.value

    @property
    def eligible(self):
        return self.lifecycle in (
            SetupLifecycle.ACCEPTED.value,
            SetupLifecycle.ORDER_CREATED.value,
            SetupLifecycle.PENDING.value,
            SetupLifecycle.FILLED.value,
            SetupLifecycle.CLOSED.value,
        )

    def to_dict(self):
        return {
            "provenance": str(self.provenance),
            "exchange": self.exchange,
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strategy": self.strategy,
            "setup_id": self.setup_id,
            "structural_id": self.structural_id,
            "economic_fingerprint": self.economic_fingerprint,
            "canonical_id": self.canonical_id,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward": self.risk_reward,
            "atr": self.atr,
            "entry_distance": self.entry_distance,
            "entry_distance_atr": self.entry_distance_atr,
            "observed_price": self.observed_price,
            "score": self.score,
            "confidence": self.confidence,
            "entry_mode": self.entry_mode,
            "lifecycle": self.lifecycle,
            "structurally_valid": self.structurally_valid,
            "trade_eligible": self.trade_eligible,
            "entry_rejection_reason": self.entry_rejection_reason,
            "rejection_reasons": list(self.rejection_reasons),
            "zone_diagnostics": list(self.zone_diagnostics),
            "zone_freshness": self.zone_freshness,
            "zone_age_bars": self.zone_age_bars,
            "is_economic_duplicate": self.is_economic_duplicate,
            "bar": self.bar,
            "timestamp": self.timestamp,
        }
