"""
====================================================

QuantEngine

Research Intelligence -- evidence package (Phase 9E)

A deterministic, structured bundle that ties ONE experiment
(candidate) recommendation to the evidence that produced it:
exact experiment id + config provenance, baseline vs candidate
metrics, the like-for-like comparison, the recovery report, the
9D robustness findings, and the sample size.

`evidence_strength` is a deterministic, non-statistical grade
driven by the settled sample size (insufficient / small / limited
/ moderate / strong). It NEVER claims statistical significance.

The evidence package is immutable in spirit: it is constructed
once from validated inputs and only read thereafter.
====================================================
"""

from dataclasses import dataclass, field

from core.research.intelligence.recommendation_types import (
    EVIDENCE_INSUFFICIENT_SAMPLE,
    EVIDENCE_SMALL_SAMPLE,
    EVIDENCE_LIMITED,
    EVIDENCE_MODERATE,
    EVIDENCE_STRONG,
)

_MIN_INSUFFICIENT = 3
_MIN_SMALL = 10
_MIN_LIMITED = 30
_MIN_MODERATE = 80


def evidence_strength_for(sample_size):
    """Deterministic non-statistical evidence grade by settled count."""
    if sample_size < _MIN_INSUFFICIENT:
        return EVIDENCE_INSUFFICIENT_SAMPLE
    if sample_size < _MIN_SMALL:
        return EVIDENCE_SMALL_SAMPLE
    if sample_size < _MIN_LIMITED:
        return EVIDENCE_LIMITED
    if sample_size < _MIN_MODERATE:
        return EVIDENCE_MODERATE
    return EVIDENCE_STRONG


@dataclass(frozen=True)
class EvidencePackage:
    """One candidate's full, traceable evidence."""

    experiment_id: str
    config: dict
    baseline_metrics: dict
    candidate_metrics: dict
    comparison: dict
    recovery: dict
    robustness: list
    sample_size: int
    baseline_id: str = "baseline"

    @property
    def evidence_strength(self):
        return evidence_strength_for(self.sample_size)

    # -------------------------------------------------

    def to_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "config": self.config,
            "baseline_id": self.baseline_id,
            "baseline_metrics": self.baseline_metrics,
            "candidate_metrics": self.candidate_metrics,
            "comparison": self.comparison,
            "recovery": self.recovery,
            "robustness": list(self.robustness),
            "sample_size": self.sample_size,
            "evidence_strength": self.evidence_strength,
        }