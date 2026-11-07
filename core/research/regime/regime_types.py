"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- core types

Immutable evidence containers for the regime layer. Everything the
regime engine emits is RESEARCH evidence about *under which market
conditions* a candidate configuration works or fails; nothing here
decides what gets traded and no container is allowed to carry an
auto-deploy directive.

Closed vocabularies (never invented, always data-gated):

   trend_vs_range       TREND / RANGE
   direction_structure  BULLISH / BEARISH / NEUTRAL   (market bias)
   volatility_regime    HIGH / NORMAL / LOW
   atr_regime           EXPANSION / NEUTRAL / CONTRACTION
   displacement         STRONG / NORMAL / ABSENT
   liquidity            SWEEPED / NORMAL
   wyckoff              ACCUMULATION / MARKUP / DISTRIBUTION /
                        MARKDOWN / TRANSITION
   fvg                  PRESENT / ABSENT
   order_block          PRESENT / ABSENT

A dimension is UNAVAILABLE (None) whenever the bounded decision-time
window is too short or lacks the required evidence -- it is never
fabricated into a fake label.

Finding statuses:
   CONDITIONAL         within-cell edge is material and the dimension
                       splits the population (data behind the claim)
   CONDITIONAL_WEAK    a small but positive within-cell edge exists
                       (reported honestly, never over-claimed)
   INCONCLUSIVE        cell population below the minimum-sample gate
   NOT_SUPPORTED       no positive within-cell edge observed

Identity rules: deterministic sha1 fingerprints of intrinsic content
only -- no UUIDs, no timestamps, no lookahead.

Boundaries: these are RESEARCH facts. They never place an order and
never emit an auto-deploy directive.
====================================================
"""

import hashlib
import json
from dataclasses import dataclass, field

UNAVAILABLE = None

# ------------------------------------------------------------------
# Closed vocabularies
# ------------------------------------------------------------------
TREND = "TREND"
RANGE = "RANGE"

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"

HIGH = "HIGH"
NORMAL = "NORMAL"
LOW = "LOW"

EXPANSION = "EXPANSION"
CONTRACTION = "CONTRACTION"

STRONG = "STRONG"
ABSENT = "ABSENT"

SWEEPED = "SWEEPED"

PRESENT = "PRESENT"

ACCUMULATION = "ACCUMULATION"
MARKUP = "MARKUP"
DISTRIBUTION = "DISTRIBUTION"
MARKDOWN = "MARKDOWN"
TRANSITION = "TRANSITION"

TREND_VS_RANGE = (TREND, RANGE)
DIRECTION_STRUCTURE = (BULLISH, BEARISH, NEUTRAL)
VOLATILITY_REGIME = (HIGH, NORMAL, LOW)
ATR_REGIME = (EXPANSION, NEUTRAL, CONTRACTION)
DISPLACEMENT_TYPES = (STRONG, NORMAL, ABSENT)
LIQUIDITY_TYPES = (SWEEPED, NORMAL)
WYCKOFF_TYPES = (ACCUMULATION, MARKUP, DISTRIBUTION, MARKDOWN, TRANSITION)
BOOLEAN_REGIME = (PRESENT, ABSENT)

REGIME_DIMENSIONS = (
    "trend_vs_range",
    "direction_structure",
    "volatility_regime",
    "atr_regime",
    "displacement",
    "liquidity",
    "wyckoff",
    "fvg",
    "order_block",
)

# Dimensions the conditional engine segments on (primary structure).
PRIMARY_REGIME_DIMENSIONS = (
    "trend_vs_range",
    "direction_structure",
    "volatility_regime",
    "atr_regime",
    "displacement",
)

# ------------------------------------------------------------------
# Deterministic id helpers
# ------------------------------------------------------------------

def stable_json(value):
    def _norm(v):
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        if isinstance(v, dict):
            return {str(k): _norm(val) for k, val in sorted(v.items())}
        if isinstance(v, (list, tuple, set)):
            return [_norm(x) for x in v]
        return str(v)

    return json.dumps(
        _norm(value), sort_keys=True, separators=(",", ":"), default=str
    )


def short_id(prefix, *parts):
    digest = hashlib.sha1(stable_json(parts).encode("utf-8")).hexdigest()
    return "%s%s" % (prefix, digest[:10])


# ------------------------------------------------------------------
# Market regime
# ------------------------------------------------------------------

@dataclass(frozen=True)
class MarketRegime:
    """Decision-time regime labels for one opportunity's window.

    Each dimension is one of the closed vocabularies above, or
    UNAVAILABLE (None) when the bounded window cannot support it.
    """

    trend_vs_range: object = UNAVAILABLE
    direction_structure: object = UNAVAILABLE
    volatility_regime: object = UNAVAILABLE
    atr_regime: object = UNAVAILABLE
    displacement: object = UNAVAILABLE
    liquidity: object = UNAVAILABLE
    wyckoff: object = UNAVAILABLE
    fvg: object = UNAVAILABLE
    order_block: object = UNAVAILABLE

    def available(self):
        """{dimension: label} for every data-gated available dim."""
        return {
            dim: getattr(self, dim)
            for dim in REGIME_DIMENSIONS
            if getattr(self, dim) is not UNAVAILABLE
        }

    def available_keys(self):
        return tuple(sorted(self.available().keys()))

    def to_dict(self):
        d = {}
        for dim in REGIME_DIMENSIONS:
            value = getattr(self, dim)
            if value is not UNAVAILABLE:
                d[dim] = value
        return d


# ------------------------------------------------------------------
# Regime observation
# ------------------------------------------------------------------

@dataclass(frozen=True)
class RegimeObservation:
    """One opportunity segmented by its decision-time regime.

    result is the OBSERVED baseline outcome: 'WIN' | 'LOSS' | ''.
    r is the realised R (None when unsettled). regime holds only the
    available dimension labels (honest, data-gated).
    """

    observation_id: str
    decision_bar: object = None
    category: str = ""
    result: str = ""
    r: object = None
    direction: str = ""
    symbol: str = ""
    timeframe: str = ""
    regime: dict = field(default_factory=dict)
    source: str = "JOURNAL"

    def in_regime(self, dimension, label):
        return self.regime.get(dimension) == label

    def to_dict(self):
        return {
            "observation_id": self.observation_id,
            "decision_bar": self.decision_bar,
            "category": self.category,
            "result": self.result,
            "r": self.r,
            "direction": self.direction,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "regime": dict(self.regime),
            "source": self.source,
        }


# ------------------------------------------------------------------
# Conditional cell
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ConditionalCell:
    """One (candidate config x regime dimension x label) cell:
    the candidate's expectancy and recovery INSIDE that cell compared
    with the frozen baseline inside the same cell."""

    dimension: str
    label: object
    config_id: str
    config_params: dict
    n: int
    wins: int
    win_rate: object
    expectancy: object
    baseline_expectancy: object
    delta_expectancy: object
    recovered: int
    min_n_gate: int

    def to_dict(self):
        return {
            "dimension": self.dimension,
            "label": self.label,
            "config_id": self.config_id,
            "config_params": dict(self.config_params),
            "n": self.n,
            "wins": self.wins,
            "win_rate": self.win_rate,
            "expectancy": self.expectancy,
            "baseline_expectancy": self.baseline_expectancy,
            "delta_expectancy": self.delta_expectancy,
            "recovered": self.recovered,
            "min_n_gate": self.min_n_gate,
        }


# ------------------------------------------------------------------
# Conditional finding
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ConditionalFinding:
    """The conditional claim: a candidate config works/fails inside a
    specific regime cell. RESEARCH evidence only."""

    dimension: str
    label: object
    config_id: str
    config_params: dict
    within_expectancy: object
    global_expectancy: object
    delta: object
    cell_n: int
    status: str
    split_breadth: object
    min_sample_note: str
    statement: str
    evidence: tuple = ()
    finding_id: str = ""
    is_production_directive: bool = False

    def __post_init__(self):
        if self.is_production_directive:
            raise ValueError(
                "regime findings are NEVER production directives"
            )
        if not self.finding_id:
            object.__setattr__(self, "finding_id", short_id(
                "K",
                "conditional",
                self.dimension,
                str(self.label),
                self.config_id,
                self.status,
            ))

    def to_dict(self):
        return {
            "finding_id": self.finding_id,
            "dimension": self.dimension,
            "label": self.label,
            "config_id": self.config_id,
            "config_params": dict(self.config_params),
            "within_expectancy": self.within_expectancy,
            "global_expectancy": self.global_expectancy,
            "delta": self.delta,
            "cell_n": self.cell_n,
            "status": self.status,
            "split_breadth": self.split_breadth,
            "min_sample_note": self.min_sample_note,
            "statement": self.statement,
            "evidence": list(self.evidence),
            "is_production_directive": self.is_production_directive,
        }


# ------------------------------------------------------------------
# Feature split
# ------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureSplit:
    """Association of one observed 9F feature value with the outcome
    (win rate / avg R) -- association evidence only, never causation."""

    feature: str
    value: object
    n: int
    win_rate: object
    avg_r: object
    overall_win_rate: object
    effect_h: object
    min_n_gate: int

    def to_dict(self):
        return {
            "feature": self.feature,
            "value": self.value,
            "n": self.n,
            "win_rate": self.win_rate,
            "avg_r": self.avg_r,
            "overall_win_rate": self.overall_win_rate,
            "effect_h": self.effect_h,
            "min_n_gate": self.min_n_gate,
        }


# ------------------------------------------------------------------
# Walk-forward window + summary
# ------------------------------------------------------------------

@dataclass(frozen=True)
class WalkForwardWindow:
    window_index: int
    dimension: str
    label: object
    config_id: str
    train_n: int
    train_expectancy: object
    validation_n: int
    validation_expectancy: object
    validation_delta: object
    survived: bool
    note: str

    def to_dict(self):
        return {
            "window_index": self.window_index,
            "dimension": self.dimension,
            "label": self.label,
            "config_id": self.config_id,
            "train_n": self.train_n,
            "train_expectancy": self.train_expectancy,
            "validation_n": self.validation_n,
            "validation_expectancy": self.validation_expectancy,
            "validation_delta": self.validation_delta,
            "survived": self.survived,
            "note": self.note,
        }


@dataclass(frozen=True)
class WalkForwardSummary:
    survived: bool
    windows: tuple = ()
    no_shuffle: bool = True
    chronological: bool = True

    @property
    def validation_n(self):
        return sum(w.validation_n for w in self.windows)

    def to_dict(self):
        return {
            "survived": self.survived,
            "no_shuffle": self.no_shuffle,
            "chronological": self.chronological,
            "validation_n": self.validation_n,
            "windows": [w.to_dict() for w in self.windows],
        }