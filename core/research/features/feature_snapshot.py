"""
====================================================

QuantEngine

Feature Evidence -- feature snapshot (Phase 9F)

An immutable, decision-time snapshot of the canonical confluence /
technical features for ONE opportunity, recorded at its exact
decision bar. It preserves:

   * the opportunity identity (opportunity_id / canonical_id)
   * direction / instrument / timeframe
   * the decision bar + the causal window size used
   * the opportunity's own decision-time levels (entry / stop /
     target / atr)
   * the deterministic feature map (name -> value or UNAVAILABLE)

Values that cannot be derived from decision-time data are recorded
as None (UNAVAILABLE) -- NEVER fabricated. The snapshot is a pure
read-only record for the 9F dependency analysis and the 9G dataset.
====================================================
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FeatureSnapshot:
    opportunity_id: str = ""
    instrument_id: str = ""
    direction: str = ""
    timeframe: str = ""
    decision_bar: int = 0
    window_size: int = 0

    entry: object = None
    stop: object = None
    target: object = None
    atr: object = None

    features: dict = field(default_factory=dict)

    # -------------------------------------------------

    def has(self, name):
        return self.features.get(name) is not None

    def available_feature_count(self):
        return sum(1 for v in self.features.values() if v is not None)

    def to_dict(self):
        return {
            "opportunity_id": self.opportunity_id,
            "instrument_id": self.instrument_id,
            "direction": self.direction,
            "timeframe": self.timeframe,
            "decision_bar": self.decision_bar,
            "window_size": self.window_size,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "atr": self.atr,
            "features": dict(self.features),
        }