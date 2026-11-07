"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- core types

Immutable evidence containers produced by the discovery pipeline:

   * OpportunityGap        -- one discovered reason the pipeline lost
                               economic value (a gap to investigate).
   * DiscoveryHypothesis   -- a deterministic, evidence-gated research
                               question + a validated candidate change
                               using the supported 9B/9C axes ONLY.
   * DiscoveryExperiment   -- one executed counterfactual experiment
                               with full metrics / comparison / recovery
                               / robustness / economic / OOS / gate
                               facts (ALL retained, none hidden).
   * EconomicAssessment    -- the capture-vs-risk economic trade-off of
                               an experiment against its baseline.
   * DiscoveryFinding      -- the statused research conclusion surfaced
                               to the report. is_production_directive is
                               permanently False (enforced by __post_init__).

Identity rules: deterministic sha1 fingerprints of intrinsic content
only -- no UUIDs, no timestamps, no provider state, no lookahead.

Boundaries: these are RESEARCH facts. Nothing here mutates a ledger,
places an order, or touches a production strategy/risk state, and no
container is allowed to carry an auto-deploy directive.
====================================================
"""

import hashlib
import json
from dataclasses import dataclass, field


def _norm(value):
    """Deterministic normalization for id derivation / hashing."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple, set)):
        return [_norm(x) for x in value]
    return str(value)


def stable_json(value):
    """Deterministic serialization (sorted keys, consistent default)."""
    return json.dumps(
        _norm(value),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha1_digest(*parts):
    return hashlib.sha1(
        stable_json(parts).encode("utf-8")
    ).hexdigest()


def short_id(prefix, *parts):
    return "%s%s" % (prefix, sha1_digest(*parts)[:10])


# ==================================================================
# Opportunity gap
# ==================================================================
@dataclass(frozen=True)
class OpportunityGap:
    """One evidence-backed reason the pipeline lost economic value."""

    category: str
    count: int
    observation_ids: tuple = ()
    instruments: tuple = ()
    directions: tuple = ()
    reasons: tuple = ()
    expected_R: float = 0.0
    evidence: tuple = ()
    gap_id: str = ""

    def __post_init__(self):
        if not self.gap_id:
            object.__setattr__(self, "gap_id", short_id(
                "G",
                self.category,
                self.count,
                sorted(self.observation_ids),
                sorted(self.instruments),
                sorted(self.directions),
                sorted(self.reasons),
                self.expected_R,
            ))

    def to_dict(self):
        return {
            "gap_id": self.gap_id,
            "category": self.category,
            "count": self.count,
            "observation_ids": list(self.observation_ids),
            "instruments": list(self.instruments),
            "directions": list(self.directions),
            "reasons": list(self.reasons),
            "expected_R": self.expected_R,
            "evidence": list(self.evidence),
        }


# ==================================================================
# Discovery hypothesis
# ==================================================================
@dataclass(frozen=True)
class DiscoveryHypothesis:
    """A deterministic, evidence-gated candidate change.

    overrides: parameter ranges over the SUPPORTED 9B/9C axes only.
    direction: optional expected bias (LONG / SHORT), used by the
               directional-safety gate (never a promotion).
    seven_e_no_go: True when this hypothesis reproduces the 7E
                   directional-breakout surface; the gate then returns
                   BLOCKED (NO-GO preserved).
    """

    kind: str
    question: str
    statement: str
    why: str
    expected_outcome: str
    overrides: dict
    features: tuple = ()
    direction: str = ""
    symbol: str = "UNKNOWN"
    evidence: tuple = ()
    seven_e_no_go: bool = False
    hypothesis_id: str = ""
    injected: bool = False

    def __post_init__(self):
        if not self.hypothesis_id:
            object.__setattr__(self, "hypothesis_id", short_id(
                "H",
                self.kind,
                self.question,
                dict(self.overrides),
                sorted(self.features),
                str(self.direction),
                str(self.symbol),
            ))

    def to_dict(self):
        return {
            "hypothesis_id": self.hypothesis_id,
            "kind": self.kind,
            "question": self.question,
            "statement": self.statement,
            "why": self.why,
            "expected_outcome": self.expected_outcome,
            "overrides": dict(self.overrides),
            "features": list(self.features),
            "direction": self.direction,
            "symbol": self.symbol,
            "evidence": list(self.evidence),
            "seven_e_no_go": self.seven_e_no_go,
            "injected": self.injected,
        }


# ==================================================================
# Economic assessment
# ==================================================================
@dataclass(frozen=True)
class EconomicAssessment:
    """Capture-vs-risk trade-off of one experiment vs its baseline.

    Economic capture is the objective: capture GAIN (incremental fills)
    without worse expectancy / risk / MAE / loss rate / drawdown.
    """

    capture_gain: int
    incremental_R: float
    expectancy_delta: float
    risk_delta: float
    loss_rate_delta: float
    max_drawdown_delta: float
    loss_expansion: bool
    acceptable: bool
    verdict: str

    def to_dict(self):
        return {
            "capture_gain": self.capture_gain,
            "incremental_R": self.incremental_R,
            "expectancy_delta": self.expectancy_delta,
            "risk_delta": self.risk_delta,
            "loss_rate_delta": self.loss_rate_delta,
            "max_drawdown_delta": self.max_drawdown_delta,
            "loss_expansion": self.loss_expansion,
            "acceptable": self.acceptable,
            "verdict": self.verdict,
        }


# ==================================================================
# Discovery experiment
# ==================================================================
@dataclass(frozen=True)
class DiscoveryExperiment:
    """One executed counterfactual experiment (ALL are retained)."""

    experiment_id: str
    hypothesis_id: str
    params: dict
    metrics: dict
    comparison: dict
    recovery: dict
    robustness: tuple = ()
    statistical: dict = field(default_factory=dict)
    oos: dict = field(default_factory=dict)
    economic: dict = field(default_factory=dict)
    direction_evidence: dict = field(default_factory=dict)
    research_evidence: dict = field(default_factory=dict)
    population_note: str = ""
    status: str = ""
    reasons: tuple = ()
    score: float = 0.0
    evidence: tuple = ()

    def to_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "hypothesis_id": self.hypothesis_id,
            "params": dict(self.params),
            "metrics": dict(self.metrics),
            "comparison": dict(self.comparison),
            "recovery": dict(self.recovery),
            "robustness": list(self.robustness),
            "statistical": dict(self.statistical),
            "oos": dict(self.oos),
            "economic": dict(self.economic),
            "direction_evidence": dict(self.direction_evidence),
            "research_evidence": dict(self.research_evidence),
            "population_note": self.population_note,
            "status": self.status,
            "reasons": list(self.reasons),
            "score": self.score,
            "evidence": list(self.evidence),
        }


# ==================================================================
# Discovery finding
# ==================================================================
@dataclass(frozen=True)
class DiscoveryFinding:
    """A statused research conclusion (evidence, never a directive)."""

    hypothesis_id: str
    experiment_id: str
    status: str
    statement: str
    evidence: tuple = ()
    next_step: str = ""
    finding_id: str = ""
    is_production_directive: bool = False

    def __post_init__(self):
        if self.is_production_directive:
            raise ValueError(
                "discovery findings are NEVER production directives"
            )
        if not self.finding_id:
            object.__setattr__(self, "finding_id", short_id(
                "F",
                self.hypothesis_id,
                self.experiment_id,
                self.status,
            ))

    def to_dict(self):
        return {
            "finding_id": self.finding_id,
            "hypothesis_id": self.hypothesis_id,
            "experiment_id": self.experiment_id,
            "status": self.status,
            "statement": self.statement,
            "evidence": list(self.evidence),
            "next_step": self.next_step,
            "is_production_directive": self.is_production_directive,
        }