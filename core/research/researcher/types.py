"""
====================================================

QuantEngine

Autonomous AI Researcher -- shared types (Phase 9H)

The evidence-carrying data model for the autonomous research
scientist. Everything here is pure, frozen data: it records WHAT
the deterministic machinery (9B-9G) observed, WHAT hypothesis was
asked, WHAT experiments were actually run, and WHAT was concluded,
together with the concrete evidence each conclusion cites.

The research scientist NEVER declares anything production-ready and
never issues trading directives. Every recommendation carries
`is_production_directive=False` and the standing limitation banner.

Judgement vocabulary (9H):
   OBSERVATION          a fact observed, not a claim
   HYPOTHESIS           a falsifiable question, not a finding
   VALIDATED            counterfactual evidence is positive, OOS
                        passed and the robustness gate is clear --
                        still research-only, never production
   REJECTED             counterfactual evidence is negative (kept,
                        never silently discarded)
   INSUFFICIENT_EVIDENCE  withheld judgement (never guessed)
   BLOCKED              an experiment could not be meaningfully run

Determinism: ids are sha1-derived from the intrinsic content, never
random UUIDs or timestamps.
====================================================
"""

from dataclasses import dataclass, field

OBSERVATION = "OBSERVATION"
HYPOTHESIS = "HYPOTHESIS"
VALIDATED = "VALIDATED"
REJECTED = "REJECTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
BLOCKED = "BLOCKED"

RESEARCH_STATUSES = (
    OBSERVATION,
    HYPOTHESIS,
    VALIDATED,
    REJECTED,
    INSUFFICIENT_EVIDENCE,
    BLOCKED,
)

PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"

STANDING_LIMITATION = (
    "Autonomous research output is NOT a production-ready declaration. "
    "Nothing produced by the 9H researcher is ever auto-promoted, and no "
    "order / position / risk / portfolio action may be taken from it. "
    "The deterministic research machinery (9B-9G) remains the sole source "
    "of numerical truth."
)


@dataclass(frozen=True)
class EvidenceContext:
    """Deterministic read-only snapshot of the supplied opportunity
    population (the OBSERVE step of the autonomous loop)."""

    records: int = 0
    filled: int = 0
    population: dict = field(default_factory=dict)
    rejected_by_reason: dict = field(default_factory=dict)
    expectancy: object = None
    avg_R: object = None
    win_rate: object = None
    notes: tuple = field(default_factory=tuple)

    @property
    def vacuous(self):
        return self.records <= 0

    @property
    def has_fills(self):
        return self.filled > 0


@dataclass(frozen=True)
class Hypothesis:
    """One falsifiable research question with its designed experiment.

    question:      the QUESTION asked of the data
    statement:     the falsifiable HYPOTHESIS
    why:           which observed evidence motivated it (the WHY)
    dataset:       description of the dataset it runs over
    features:      9F-style feature names it cares about
    overrides:     the supported parameter grid (validated against the
                   9B/9C vocabulary); None values allowed (expiry)
    outcome_bars:  explicit trade-outcome horizon for the grid
    baseline_id:   the baseline measured against
    """

    hypothesis_id: str
    kind: str
    question: str
    statement: str
    why: str = ""
    dataset: str = ""
    features: tuple = field(default_factory=tuple)
    overrides: dict = field(default_factory=dict)
    outcome_bars: object = None
    baseline_id: str = "baseline"

    def to_dict(self):
        return {
            "hypothesis_id": self.hypothesis_id,
            "kind": self.kind,
            "question": self.question,
            "statement": self.statement,
            "why": self.why,
            "dataset": self.dataset,
            "features": list(self.features),
            "overrides": {
                k: list(v) for k, v in sorted(self.overrides.items())
            },
            "outcome_bars": self.outcome_bars,
            "baseline_id": self.baseline_id,
        }


@dataclass(frozen=True)
class ExperimentResult:
    """The full counterfactual + statistical + OOS evidence for ONE
    executed configuration. Fails and insufficiencies are RETAINED."""

    experiment_id: str
    config: object
    filled: int = 0
    settled: int = 0
    metrics: dict = field(default_factory=dict)
    comparison: dict = field(default_factory=dict)
    robustness: tuple = field(default_factory=tuple)
    categories: dict = field(default_factory=dict)
    evidence_strength: str = ""
    recommendation_status: str = ""
    robustness_status: str = ""
    statistical: dict = field(default_factory=dict)
    oos: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "config": getattr(self.config, "to_dict", lambda: {})()
            if self.config is not None else {},
            "filled": self.filled,
            "settled": self.settled,
            "metrics": dict(self.metrics),
            "comparison": dict(self.comparison),
            "robustness": list(self.robustness),
            "categories": dict(self.categories),
            "evidence_strength": self.evidence_strength,
            "recommendation_status": self.recommendation_status,
            "robustness_status": self.robustness_status,
            "statistical": dict(self.statistical),
            "oos": dict(self.oos),
            "features": dict(self.features),
        }


@dataclass(frozen=True)
class ResearchRecommendation:
    """A ranked research recommendation. Distinguishes what was
    OBSERVED, what remains a HYPOTHESIS, and what has been VALIDATED
    only against research evidence. Never a production directive."""

    recommendation_id: str
    hypothesis_id: str
    kind: str
    score: float
    status: str = INSUFFICIENT_EVIDENCE
    question: str = ""
    statement: str = ""
    why: str = ""
    evidence: tuple = field(default_factory=tuple)
    next_step: str = ""
    is_production_directive: bool = False

    def to_dict(self):
        return {
            "recommendation_id": self.recommendation_id,
            "hypothesis_id": self.hypothesis_id,
            "kind": self.kind,
            "status": self.status,
            "score": self.score,
            "question": self.question,
            "statement": self.statement,
            "why": self.why,
            "evidence": list(self.evidence),
            "next_step": self.next_step,
            "is_production_directive": self.is_production_directive,
        }


@dataclass(frozen=True)
class InvestigationReport:
    """The complete 9H evidence chain for one autonomous investigation:

    QUESTION -> HYPOTHESIS -> WHY -> DATASET -> FEATURES -> EXPERIMENT
    -> BASELINE -> COUNTERFACTUAL RESULTS -> STATISTICAL RESULTS ->
    OOS RESULTS -> ROBUSTNESS -> CONCLUSION -> RECOMMENDATION"""

    phase: str = "9H"
    investigation_id: str = ""
    symbol: str = "UNKNOWN"
    baseline: dict = field(default_factory=dict)
    context: object = None
    hypotheses: tuple = field(default_factory=tuple)
    recommendations: tuple = field(default_factory=tuple)
    memory_nudge: str = ""
    provider: str = "null"
    provider_available: bool = True
    status: str = INSUFFICIENT_EVIDENCE
    production_ready: bool = False
    standing_limitations: tuple = field(default_factory=tuple)

    def to_dict(self):
        return {
            "phase": self.phase,
            "investigation_id": self.investigation_id,
            "symbol": self.symbol,
            "baseline": dict(self.baseline),
            "context": {
                "records": self.context.records if self.context else 0,
                "filled": self.context.filled if self.context else 0,
                "population": dict(self.context.population)
                if self.context else {},
                "rejected_by_reason": dict(self.context.rejected_by_reason)
                if self.context else {},
                "expectancy": self.context.expectancy if self.context else None,
                "win_rate": self.context.win_rate if self.context else None,
                "notes": list(self.context.notes) if self.context else [],
            },
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "recommendations": [
                r.to_dict() for r in self.recommendations
            ],
            "memory_nudge": self.memory_nudge,
            "provider": self.provider,
            "provider_available": self.provider_available,
            "status": self.status,
            "production_ready": self.production_ready,
            "standing_limitations": list(self.standing_limitations),
        }

    def render(self):
        """Deterministic human-readable evidence chain."""
        lines = [
            f"Phase 9H autonomous research -- investigation {self.investigation_id}",
            f"symbol={self.symbol} provider={self.provider} "
            f"available={self.provider_available} status={self.status}",
            f"production_ready={self.production_ready}",
            "evidence chain:",
        ]
        ctx = self.to_dict()["context"]
        lines.append(f"  DATASET records={ctx['records']} fills={ctx['filled']} "
                     f"baseline_expectancy={ctx['expectancy']}")
        for label in ("population", "rejected_by_reason"):
            if ctx[label]:
                lines.append(f"    {label}: {ctx[label]}")
        for h in self.hypotheses:
            lines.append(f"  HYPOTHESIS {h.hypothesis_id} [{h.kind}]")
            lines.append(f"    question: {h.question}")
            lines.append(f"    why: {h.why}")
            lines.append(f"    features: {', '.join(h.features) or '-'}")
            lines.append(f"    experiment grid: {h.to_dict()['overrides']}")
        for r in self.recommendations:
            lines.append(f"  RECOMMENDATION {r.recommendation_id} "
                         f"status={r.status} score={r.score:.4f}")
            lines.append(f"    statement: {r.statement or r.question}")
            lines.append(f"    evidence: {', '.join(str(e) for e in r.evidence) or '-'}")
            if r.next_step:
                lines.append(f"    next_step: {r.next_step}")
        lines.append(f"  memory_nudge: {self.memory_nudge or '-'}")
        for lim in self.standing_limitations:
            lines.append(f"  LIMITATION: {lim}")
        return "\n".join(lines)