"""
====================================================

QuantEngine

Research Intelligence -- confluence analysis (Phase 9E)

Infrastructure for future feature / confluence EVIDENCE. It is
explicitly built to work correctly when NO confluence features are
available: in that case, analysis reports CONFLUENCE_DATA_UNAVAILABLE
rather than fabricating evidence.

Future producers (Wyckoff, footprint / order flow, Fibonacci,
volume, liquidity, market structure, FVG, order blocks, displacement,
smart-money concepts -- any validated QuantEngine feature) may supply
structured confluence records here. This phase does NOT make up any
feature values.

Confluence evidence consumed here must be OUTCOME-CAUSAL (produced
at decision time, never from future data) and are joined by
opportunity / experiment identity.
====================================================
"""

from dataclasses import dataclass, field
from collections.abc import Mapping

CONFLUENCE_DATA_UNAVAILABLE = "CONFLUENCE_DATA_UNAVAILABLE"


@dataclass(frozen=True)
class ConfluenceFeature:
    """One feature's deterministic, decision-time evidence.

    feature / value_or_category
      name        the feature (e.g. 'wyckoff_phase', 'displacement',
                  'order_block', 'fvg')
      value       a deterministic value or category (may be a scalar
                  or a nominal string)
      sample      number of opportunities observed with this value
      outcomes    a resolved outcome summary for that group
      experiment_id  the experiment the evidence belongs to
                  ('' = baseline observation)
    """

    name: str = ""
    value: object = None
    sample: int = 0
    outcomes: dict = field(default_factory=dict)
    experiment_id: str = ""


class ConfluenceAnalysis:
    """Deterministic container of confluence evidence.

    With ZERO supplied features the analysis is a first-class,
    complete result: it reports CONFLUENCE_DATA_UNAVAILABLE and no
    feature rows. It never synthesises feature values.
    """

    def __init__(self, features=None):
        self.features = tuple(features or ())

    # -------------------------------------------------

    @property
    def unavailable(self):
        return len(self.features) == 0

    def status(self):
        return CONFLUENCE_DATA_UNAVAILABLE if self.unavailable else "AVAILABLE"

    def by_name(self, name):
        return [
            f for f in self.features if f.name == name
        ]

    def to_dict(self):
        return {
            "status": self.status(),
            "feature_count": len(self.features),
            "features": [
                {
                    "name": f.name,
                    "value": f.value,
                    "sample": f.sample,
                    "outcomes": dict(f.outcomes),
                    "experiment_id": f.experiment_id,
                }
                for f in self.features
            ],
        }


def confluence_from_features(features):
    """Construct a ConfluenceAnalysis from an iterable of feature
    dicts or ConfluenceFeature objects (read-only, deterministic)."""
    if isinstance(features, Mapping):
        features = [
            ConfluenceFeature(name=k, value=v) for k, v in features.items()
        ]
    else:
        features = [
            f if isinstance(f, ConfluenceFeature)
            else ConfluenceFeature(**{k: v for k, v in f.items()})
            for f in features
        ]
    return ConfluenceAnalysis(features)