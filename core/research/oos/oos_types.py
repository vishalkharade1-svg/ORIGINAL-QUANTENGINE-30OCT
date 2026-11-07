"""
====================================================================

QuantEngine

Multi-Period Out-of-Sample Validation (Phase 9M) -- evidence types

Frozen, deterministic containers for the 9M OOS validation layer.

A HypothesisRecord is a CONSUMED discovery from the frozen 9J/9K/9L
research layer -- 9M never invents a second discovery system. Every
period verdict and every finding-level status is retained (VALIDATED,
PROMISING, INCONCLUSIVE, REJECTED, UNAVAILABLE periods and the full
BLOCKED -> VALIDATED_RESEARCH_ONLY ladder). Unfavorable results are
never hidden.

All containers are frozen and serializable to stable JSON (dicts with
deterministic ordering only).
====================================================================
"""

import math
from dataclasses import dataclass, field

from core.research.oos import constants as _c
from core.research.regime.regime_types import (
    short_id,
    stable_json,
)

UNAVAILABLE = None


# ------------------------------------------------------------------
# Consumed hypothesis
# ------------------------------------------------------------------


@dataclass(frozen=True)
class HypothesisRecord:
    """One research discovery re-validated against unseen OOS periods.

    Fields mirror the frozen discovery surface (9J DiscoveryHypothesis /
    9K ConditionalFinding / 9L EntrySelection/RecoveryFinding):
      - params:  the exact candidate configuration replayed through the
                 frozen 9C counterfactual machinery (a CounterfactualConfig
                 parameter dict, including entry_model).
      - regime_dim / regime_label: optional conditioning (e.g.
                 trend_vs_range / TREND). A conditional claim is never
                 evaluated as a universal claim.
      - seven_e_no_go: preserves the frozen 7E directional NO-GO
                 boundary (BLOCKED, never resurrected).
      - walk_forward_passed: 9K walk-forward evidence the discovery
                 already earned; 9M is repeated independent OOS
                 confirmation on top, never a replacement for 9K.
    """

    hypothesis_id: str = ""
    origin: str = "9L"
    statement: str = ""
    symbol: str = ""
    direction: str = ""
    regime_dim: object = None
    regime_label: object = None
    params: dict = field(default_factory=dict)
    seven_e_no_go: bool = False
    walk_forward_passed: bool = False
    walk_forward_note: str = ""
    expected_outcome: str = ""
    evidence: tuple = field(default_factory=tuple)

    # -------------------------------------------------

    def __post_init__(self):
        evidence = self.evidence
        if not isinstance(evidence, (tuple, list)):
            raise ValueError("evidence must be a tuple/list of provenance tokens")
        evidence = tuple(evidence)
        if any(not isinstance(item, str) or not item for item in evidence):
            raise ValueError("evidence provenance tokens must be non-empty strings")
        object.__setattr__(self, "evidence", evidence)
        if self.origin not in _c.ORIGINS:
            raise ValueError(
                "unsupported discovery origin %r; supported=%s"
                % (self.origin, _c.ORIGINS)
            )
        if self.direction and self.direction not in _c.DIRECTIONS:
            raise ValueError(
                "unsupported direction %r; supported=%s"
                % (self.direction, _c.DIRECTIONS)
            )
        if self.seven_e_no_go and self.hypothesis_id:
            pass  # a 7E hypothesis keeps a stable id; it is BLOCKED
        if not self.hypothesis_id:
            object.__setattr__(
                self, "hypothesis_id",
                short_id(
                    "M",
                    self.origin,
                    self.statement,
                    self.symbol,
                    self.direction,
                    self.regime_dim,
                    self.regime_label,
                    {k: list(v) if isinstance(v, (tuple, list))
                     else v for k, v in sorted(self.params.items())},
                    self.seven_e_no_go,
                ),
            )

    def is_conditional(self):
        return bool(self.regime_dim)

    def to_dict(self):
        return {
            "hypothesis_id": self.hypothesis_id,
            "origin": self.origin,
            "statement": self.statement,
            "symbol": self.symbol,
            "direction": self.direction,
            "regime_dim": self.regime_dim,
            "regime_label": self.regime_label,
            "params": {k: v for k, v in sorted(self.params.items())},
            "seven_e_no_go": self.seven_e_no_go,
            "walk_forward_passed": self.walk_forward_passed,
            "walk_forward_note": self.walk_forward_note,
            "expected_outcome": self.expected_outcome,
            "evidence": list(self.evidence),
        }


# ------------------------------------------------------------------
# Period boundaries
# ------------------------------------------------------------------


@dataclass(frozen=True)
class PeriodBoundary:
    """A half-open [start, stop) index slice of the time-ordered
    opportunity population."""

    region: str          # "DISCOVERY" | "OOS"
    label: str           # "DISCOVERY" | "OOS-1" ..
    period_index: int    # -1 for discovery, 0-based for OOS periods
    start: int
    stop: int
    n: int
    sample_sufficient: bool

    def to_dict(self):
        return {
            "region": self.region,
            "label": self.label,
            "period_index": self.period_index,
            "start": self.start,
            "stop": self.stop,
            "n": self.n,
            "sample_sufficient": self.sample_sufficient,
        }


# ------------------------------------------------------------------
# Per-period evidence
# ------------------------------------------------------------------


@dataclass(frozen=True)
class OosPeriodEvidence:
    """Re-evaluation of one hypothesis on ONE unseen OOS period.

    The candidate config is genuinely replayed by the frozen 9C
    counterfactual machinery on that period's opportunities; the
    comparison is ALWAYS against the frozen production baseline
    (BREAKOUT_CONTINUATION), never against the discovery data.
    MAE increase is reported as a trade-off, not auto-rejection.
    """

    period: str
    n_opportunities: int
    n_baseline_settled: int
    n_baseline_missed: int
    n_candidate_filled: int
    n_trades: int
    n_wins: int
    n_losses: int
    n_recovered: int
    win_rate: object = None
    expectancy: object = None
    baseline_expectancy: object = None
    expectancy_delta: object = None
    capture_gain: object = None
    loss_rate_delta: object = None
    max_drawdown_delta: object = None
    recovery_gain: object = None
    mae_tradeoff: bool = False
    loss_expansion: bool = False
    economic_acceptable: bool = False
    sample_sufficient: bool = False
    status: str = _c.PERIOD_STATUSES[-1]
    reasons: tuple = field(default_factory=tuple)

    def to_dict(self):
        return {
            "period": self.period,
            "n_opportunities": self.n_opportunities,
            "n_baseline_settled": self.n_baseline_settled,
            "n_baseline_missed": self.n_baseline_missed,
            "n_candidate_filled": self.n_candidate_filled,
            "n_trades": self.n_trades,
            "n_wins": self.n_wins,
            "n_losses": self.n_losses,
            "n_recovered": self.n_recovered,
            "win_rate": self.win_rate,
            "expectancy": self.expectancy,
            "baseline_expectancy": self.baseline_expectancy,
            "expectancy_delta": self.expectancy_delta,
            "capture_gain": self.capture_gain,
            "loss_rate_delta": self.loss_rate_delta,
            "max_drawdown_delta": self.max_drawdown_delta,
            "recovery_gain": self.recovery_gain,
            "mae_tradeoff": self.mae_tradeoff,
            "loss_expansion": self.loss_expansion,
            "economic_acceptable": self.economic_acceptable,
            "sample_sufficient": self.sample_sufficient,
            "status": self.status,
            "reasons": list(self.reasons),
        }


# ------------------------------------------------------------------
# Finding-level aggregation
# ------------------------------------------------------------------


@dataclass(frozen=True)
class HypothesisOosResult:
    """Multi-period survival of one hypothesis across the OOS periods."""

    hypothesis_id: str = ""
    origin: str = "9L"
    statement: str = ""
    symbol: str = ""
    direction: str = ""
    regime_dim: object = None
    regime_label: object = None
    seven_e: bool = False
    status: str = _c.OOS_STATUSES[1]
    reasons: tuple = field(default_factory=tuple)
    periods_tested: int = 0
    periods_available: int = 0
    periods_survived: int = 0
    periods_rejected: int = 0
    periods_inconclusive: int = 0
    periods_unavailable: int = 0
    survival_ratio: object = None
    sign_consistent_periods: int = 0
    economic_consistent: bool = False
    per_period: tuple = field(default_factory=tuple)
    economic_statistics: dict = field(default_factory=dict)
    regime: dict = field(default_factory=dict)
    symbols: dict = field(default_factory=dict)
    directions: dict = field(default_factory=dict)
    walk_forward_passed: bool = False
    walk_forward_note: str = ""
    survives_familywise: bool = False
    robustness: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "hypothesis_id": self.hypothesis_id,
            "origin": self.origin,
            "statement": self.statement,
            "symbol": self.symbol,
            "direction": self.direction,
            "regime_dim": self.regime_dim,
            "regime_label": self.regime_label,
            "seven_e": self.seven_e,
            "status": self.status,
            "reasons": list(self.reasons),
            "periods_tested": self.periods_tested,
            "periods_available": self.periods_available,
            "periods_survived": self.periods_survived,
            "periods_rejected": self.periods_rejected,
            "periods_inconclusive": self.periods_inconclusive,
            "periods_unavailable": self.periods_unavailable,
            "survival_ratio": self.survival_ratio,
            "sign_consistent_periods": self.sign_consistent_periods,
            "economic_consistent": self.economic_consistent,
            "per_period": [p.to_dict() for p in self.per_period],
            "economic_statistics": dict(self.economic_statistics),
            "regime": {k: (dict(v) if isinstance(v, dict) else v)
                       for k, v in sorted(self.regime.items())},
            "symbols": {k: (dict(v) if isinstance(v, dict) else v)
                        for k, v in sorted(self.symbols.items())},
            "directions": {k: (dict(v) if isinstance(v, dict) else v)
                           for k, v in sorted(self.directions.items())},
            "walk_forward_passed": self.walk_forward_passed,
            "walk_forward_note": self.walk_forward_note,
            "survives_familywise": self.survives_familywise,
            "robustness": dict(self.robustness),
        }


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _std(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    if n % 2:
        return xs[n // 2]
    return (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def economic_statistics(deltas):
    """Mean / median / dispersion / worst / best over settled economic
    deltas -- variance is never hidden behind an aggregate."""
    deltas = [float(d) for d in deltas if d is not None]
    return {
        "n": len(deltas),
        "mean": _mean(deltas),
        "median": _median(deltas),
        "std": _std(deltas),
        "worst": min(deltas) if deltas else None,
        "best": max(deltas) if deltas else None,
    }


def survival_ratio(survived, available):
    if not available:
        return None
    return survived / available


def stable_json_round(value, ndigits=6):
    return round(float(value), ndigits)