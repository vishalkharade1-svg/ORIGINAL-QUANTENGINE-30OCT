"""
====================================================================

QuantEngine

Research Recommendation & Evidence Readback (Phase 9N) -- types

Frozen, deterministic containers for the 9N readback layer.

Every finding carries its full evidence chain so a human (or a future
interpreter) can trace:

    recommendation -> OOS result -> hypothesis -> origin ->
    (optional 9L / 9K readback) -> underlying claim and parameters.

The recommendation is ALWAYS a research directive (INVESTIGATE_FURTHER);
it is never an order to change a strategy or to deploy. Unfavorable and
inconclusive evidence is retained in the same chain -- a review never
hides a rejection.
====================================================================
"""

from dataclasses import dataclass, field

from core.research.recommendation import constants as _c
from core.research.regime.regime_types import short_id


@dataclass(frozen=True)
class OosReadback:
    """The OOS portion of the evidence chain (drawn verbatim from the
    frozen 9M HypothesisOosResult)."""

    oos_report_id: str = ""
    final_status: str = ""
    periods_tested: int = 0
    periods_available: int = 0
    periods_survived: int = 0
    periods_rejected: int = 0
    periods_inconclusive: int = 0
    survival_ratio: object = None
    sign_consistent_periods: int = 0
    economic_consistent: bool = False
    familywise_passed: bool = False
    robustness_level: str = "LOW"
    walk_forward_passed: bool = False
    per_period: tuple = field(default_factory=tuple)

    def to_dict(self):
        return {
            "oos_report_id": self.oos_report_id,
            "final_status": self.final_status,
            "periods_tested": self.periods_tested,
            "periods_available": self.periods_available,
            "periods_survived": self.periods_survived,
            "periods_rejected": self.periods_rejected,
            "periods_inconclusive": self.periods_inconclusive,
            "survival_ratio": self.survival_ratio,
            "sign_consistent_periods": self.sign_consistent_periods,
            "economic_consistent": self.economic_consistent,
            "familywise_passed": self.familywise_passed,
            "robustness_level": self.robustness_level,
            "walk_forward_passed": self.walk_forward_passed,
            "per_period": list(self.per_period),
        }


@dataclass(frozen=True)
class HypothesisReadback:
    """The hypothesis / claim portion of the evidence chain."""

    hypothesis_id: str = ""
    origin: str = "9L"
    statement: str = ""
    symbol: str = ""
    direction: str = ""
    regime_dim: object = None
    regime_label: object = None
    is_conditional: bool = False
    seven_e: bool = False
    params: dict = field(default_factory=dict)
    expected_outcome: str = ""

    def to_dict(self):
        return {
            "hypothesis_id": self.hypothesis_id,
            "origin": self.origin,
            "statement": self.statement,
            "symbol": self.symbol,
            "direction": self.direction,
            "regime_dim": self.regime_dim,
            "regime_label": self.regime_label,
            "is_conditional": self.is_conditional,
            "seven_e": self.seven_e,
            "params": {
                k: (list(v) if isinstance(v, (tuple, list)) else v)
                for k, v in sorted(self.params.items())
            },
            "expected_outcome": self.expected_outcome,
        }


@dataclass(frozen=True)
class AncillaryReadback:
    """Optional compressed 9L / 9K readback (recovery / entry /
    calibration / walk-forward / finding status) that contextualizes the
    hypothesis chain without re-deriving any research."""

    recovery_status: str = "UNAVAILABLE"
    entry_status: str = "UNAVAILABLE"
    calibration_status: str = "UNAVAILABLE"
    walk_forward_survived: object = None
    regime_finding_status: str = "UNAVAILABLE"
    provenance_notes: tuple = field(default_factory=tuple)

    def to_dict(self):
        return {
            "recovery_status": self.recovery_status,
            "entry_status": self.entry_status,
            "calibration_status": self.calibration_status,
            "walk_forward_survived": self.walk_forward_survived,
            "regime_finding_status": self.regime_finding_status,
            "provenance_notes": list(self.provenance_notes),
        }


@dataclass(frozen=True)
class ReadbackAnswers:
    """The five narrative answers a 9N review supplies (deterministic,
    drawn from closed narrative rosters -- never free prose)."""

    what_discovered: str = ""
    why_it_worked: tuple = field(default_factory=tuple)
    where_it_worked: tuple = field(default_factory=tuple)
    where_it_failed: tuple = field(default_factory=tuple)
    how_robust: str = "LOW"

    def to_dict(self):
        return {
            "what_discovered": self.what_discovered,
            "why_it_worked": list(self.why_it_worked),
            "where_it_worked": list(self.where_it_worked),
            "where_it_failed": list(self.where_it_failed),
            "how_robust": self.how_robust,
        }


@dataclass(frozen=True)
class RecommendationFinding:
    """One 9N review verdict on one consumed discovery, carrying its
    full evidence chain and an always-conservative directive."""

    recommendation_id: str = ""
    recommendation_status: str = _c.RECOMMENDATION_STATUSES[1]
    directive: str = _c.RECOMMENDATION_DIRECTIVE
    directive_text: str = _c.RECOMMENDATION_DIRECTIVE_TEXT
    rank: int = 0
    reasons: tuple = field(default_factory=tuple)
    limitations: tuple = field(default_factory=tuple)
    oos: OosReadback = field(default_factory=OosReadback)
    hypothesis: HypothesisReadback = field(default_factory=HypothesisReadback)
    ancillary: AncillaryReadback = field(default_factory=AncillaryReadback)
    answers: ReadbackAnswers = field(default_factory=ReadbackAnswers)

    def __post_init__(self):
        if self.recommendation_status not in _c.RECOMMENDATION_STATUSES:
            raise ValueError(
                "unsupported recommendation status %r; supported=%s"
                % (self.recommendation_status,
                   _c.RECOMMENDATION_STATUSES)
            )
        if self.directive != _c.RECOMMENDATION_DIRECTIVE:
            raise ValueError(
                "9N recommendations must carry the locked directive %r"
                % (_c.RECOMMENDATION_DIRECTIVE,)
            )
        if not self.recommendation_id:
            object.__setattr__(
                self, "recommendation_id",
                short_id(
                    "N",
                    self.recommendation_status,
                    self.hypothesis.hypothesis_id or "",
                    self.oos.oos_report_id or "",
                    self.oos.final_status or "",
                    {k: (list(v) if isinstance(v, (tuple, list)) else v)
                     for k, v in sorted(self.hypothesis.params.items())},
                ),
            )
        object.__setattr__(self, "rank", _c._RANK[self.recommendation_status])

    def to_dict(self):
        return {
            "recommendation_id": self.recommendation_id,
            "recommendation_status": self.recommendation_status,
            "directive": self.directive,
            "directive_text": self.directive_text,
            "rank": self.rank,
            "reasons": list(self.reasons),
            "limitations": list(self.limitations),
            "oos": self.oos.to_dict(),
            "hypothesis": self.hypothesis.to_dict(),
            "ancillary": self.ancillary.to_dict(),
            "answers": self.answers.to_dict(),
        }


@dataclass(frozen=True)
class Recommendation:
    """A flattened, human-facing 9N recommendation: WHAT to investigate
    next. It is NOT an instruction to change production.

    Carries deterministic references into the research stack (candidate
    / hypothesis / OOS report / evidence ids / baseline / regime / symbol
    / direction) plus ordered canonical metrics and limitations. The
    status is one of the closed 9N vocabulary; rejected / inconclusive
    recommendations are preserved, never dropped.
    """

    recommendation_id: str = ""
    status: str = _c.RECOMMENDATION_STATUSES[1]
    title: str = ""
    rationale: str = ""
    candidate_id: object = None
    hypothesis_id: object = None
    oos_report_id: object = None
    evidence_ids: tuple = field(default_factory=tuple)
    baseline_reference: object = None
    regime: object = None
    symbol: object = None
    direction: object = None
    metrics: tuple = field(default_factory=tuple)
    limitations: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if self.status not in _c.RECOMMENDATION_STATUSES:
            raise ValueError(
                "unsupported recommendation status %r; supported=%s"
                % (self.status, _c.RECOMMENDATION_STATUSES)
            )
        if not self.recommendation_id:
            object.__setattr__(
                self, "recommendation_id",
                short_id(
                    "N",
                    self.status,
                    self.candidate_id,
                    self.hypothesis_id,
                    self.oos_report_id,
                    self.baseline_reference,
                    self.regime,
                    self.symbol,
                    self.direction,
                    sorted(list(self.evidence_ids)),
                    _canonical_metrics(self.metrics),
                ),
            )

    def to_dict(self):
        return {
            "recommendation_id": self.recommendation_id,
            "status": self.status,
            "title": self.title,
            "rationale": self.rationale,
            "candidate_id": self.candidate_id,
            "hypothesis_id": self.hypothesis_id,
            "oos_report_id": self.oos_report_id,
            "evidence_ids": sorted(list(self.evidence_ids)),
            "baseline_reference": self.baseline_reference,
            "regime": self.regime,
            "symbol": self.symbol,
            "direction": self.direction,
            "metrics": list(self.metrics),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class EvidenceSummary:
    """Deterministic aggregate count of the reviewed evidence."""

    n_recommendations: int = 0
    n_findings: int = 0
    by_status: dict = field(default_factory=dict)
    n_7e_blocked: int = 0
    n_no_evidence: int = 0
    n_inconclusive: int = 0
    n_rejected: int = 0
    n_requires_more: int = 0
    n_conditional: int = 0
    n_promising: int = 0
    n_robust: int = 0

    def to_dict(self):
        return {
            "n_recommendations": self.n_recommendations,
            "n_findings": self.n_findings,
            "by_status": dict(self.by_status),
            "n_7e_blocked": self.n_7e_blocked,
            "n_no_evidence": self.n_no_evidence,
            "n_inconclusive": self.n_inconclusive,
            "n_rejected": self.n_rejected,
            "n_requires_more": self.n_requires_more,
            "n_conditional": self.n_conditional,
            "n_promising": self.n_promising,
            "n_robust": self.n_robust,
        }


@dataclass(frozen=True)
class RecommendationStatistics:
    """Deterministic aggregates that answer the evidence-chain questions
    (periods / trades / economic deltas / scoping) across the reviewed
    recommendations."""

    n_recommendations: int = 0
    n_with_oos: int = 0
    n_familywise_passed: int = 0
    n_walk_forward_passed: int = 0
    n_regime_scoped: int = 0
    n_symbol_scoped: int = 0
    n_direction_scoped: int = 0
    total_periods_tested: int = 0
    total_periods_survived: int = 0
    total_periods_rejected: int = 0
    economic_deltas: tuple = field(default_factory=tuple)

    def to_dict(self):
        return {
            "n_recommendations": self.n_recommendations,
            "n_with_oos": self.n_with_oos,
            "n_familywise_passed": self.n_familywise_passed,
            "n_walk_forward_passed": self.n_walk_forward_passed,
            "n_regime_scoped": self.n_regime_scoped,
            "n_symbol_scoped": self.n_symbol_scoped,
            "n_direction_scoped": self.n_direction_scoped,
            "total_periods_tested": self.total_periods_tested,
            "total_periods_survived": self.total_periods_survived,
            "total_periods_rejected": self.total_periods_rejected,
            "economic_deltas": list(self.economic_deltas),
        }


def _canonical_metrics(metrics):
    """Deterministic canonical form of ordered metric rows.
    Each row is either a (name, value) pair or a dict; keys are sorted
    and values normalized for stable hashing."""
    out = []
    for m in (metrics or ()):
        if isinstance(m, dict):
            out.append(tuple((str(k), _norm(v))
                             for k, v in sorted(m.items())))
        elif isinstance(m, (tuple, list)) and len(m) == 2:
            out.append((str(m[0]), _norm(m[1])))
        else:
            out.append(_norm(m))
    return tuple(out)


def _norm(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (tuple, list)):
        return tuple(_norm(x) for x in v)
    if isinstance(v, dict):
        return tuple((str(k), _norm(x)) for k, x in sorted(v.items()))
    if isinstance(v, float):
        return round(v, 6)
    return v


@dataclass(frozen=True)
class ReviewOverview:
    """Aggregate overview of the 9N review."""

    n_findings: int = 0
    by_status: dict = field(default_factory=dict)
    n_blocked: int = 0
    n_rejected: int = 0
    n_inconclusive_no_evidence: int = 0
    n_requires_more: int = 0
    n_conditional: int = 0
    n_promising: int = 0
    n_robust: int = 0

    def to_dict(self):
        return {
            "n_findings": self.n_findings,
            "by_status": dict(self.by_status),
            "n_blocked": self.n_blocked,
            "n_rejected": self.n_rejected,
            "n_inconclusive_no_evidence": self.n_inconclusive_no_evidence,
            "n_requires_more": self.n_requires_more,
            "n_conditional": self.n_conditional,
            "n_promising": self.n_promising,
            "n_robust": self.n_robust,
        }
