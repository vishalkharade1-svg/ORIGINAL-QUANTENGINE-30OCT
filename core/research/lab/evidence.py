"""
====================================================

QuantEngine

Research Lab -- evidence snapshot (Phase 9B)

An immutable record of exactly what the engine KNEW at decision
time. It is the future input for the Confluence Engine (9C) and
the AI/ML research layers (11/12). It is deliberately an
extensible container: only facts that actually exist in
QuantEngine are ever populated -- nothing is invented.

Wyckoff is NOT implemented in this project, so the Wyckoff field
is reserved (None) and populated only by a future layer that
actually computes it.
====================================================
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvidenceSnapshot:
    """Immutable evidence available at the historical decision
    point. All fields default to None; only real facts are set."""

    canonical_id: str = ""
    exchange: str = ""
    instrument_id: str = ""
    timeframe: str = ""
    direction: str = ""
    strategy: str = ""
    setup_id: str = ""

    decision_bar: int = 0
    decision_timestamp: object = None

    # available-at-decision facts (from the opportunity record)
    atr: float = None
    entry: float = None
    entry_distance: float = None
    entry_distance_atr: float = None
    observed_price: float = None
    score: float = None
    confidence: float = None
    zone_freshness: str = None
    zone_age_bars: int = None

    # structural / confluence groups -- extensible, None when unknown
    market_structure: dict = field(default_factory=dict)
    liquidity: dict = field(default_factory=dict)
    orderflow: dict = field(default_factory=dict)
    zones: dict = field(default_factory=dict)
    indicators: dict = field(default_factory=dict)
    volatility: dict = field(default_factory=dict)
    regime: dict = field(default_factory=dict)

    # Wyckoff is not implemented; reserved for a future layer.
    wyckoff: object = None

    def to_dict(self):
        return {
            "canonical_id": self.canonical_id,
            "exchange": self.exchange,
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strategy": self.strategy,
            "setup_id": self.setup_id,
            "decision_bar": self.decision_bar,
            "decision_timestamp": self.decision_timestamp,
            "atr": self.atr,
            "entry": self.entry,
            "entry_distance": self.entry_distance,
            "entry_distance_atr": self.entry_distance_atr,
            "observed_price": self.observed_price,
            "score": self.score,
            "confidence": self.confidence,
            "zone_freshness": self.zone_freshness,
            "zone_age_bars": self.zone_age_bars,
            "market_structure": self.market_structure,
            "liquidity": self.liquidity,
            "orderflow": self.orderflow,
            "zones": self.zones,
            "indicators": self.indicators,
            "volatility": self.volatility,
            "regime": self.regime,
            "wyckoff": self.wyckoff,
        }


def evidence_from_opportunity(record, decision_timestamp=None):
    """Build an EvidenceSnapshot from the REAL, available facts in
    an OpportunityRecord. Never invents values. Casts strings to
    numbers only when the source truly carried them."""
    setup = record.setup or {}
    direction = record.direction or ""

    def num(key):
        v = setup.get(key)
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return v

    return EvidenceSnapshot(
        canonical_id=record.canonical_id,
        exchange=record.exchange,
        instrument_id=record.instrument_id,
        timeframe=record.timeframe,
        direction=direction,
        strategy=record.strategy,
        setup_id=record.setup_id,
        atr=num("atr"),
        entry=num("entry"),
        entry_distance=num("entry_distance"),
        entry_distance_atr=num("entry_distance_atr"),
        observed_price=num("observed_price"),
        score=num("score"),
        confidence=num("confidence"),
        zone_freshness=setup.get("zone_freshness"),
        zone_age_bars=num("zone_age_bars"),
        decision_timestamp=decision_timestamp,
    )
