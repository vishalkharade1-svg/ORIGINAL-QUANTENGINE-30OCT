"""
====================================================

QuantEngine

Research Intelligence -- recommendation model (Phase 9E)

The immutable, evidence-backed research recommendation. It is a
structured research hypothesis -- explicitly NOT a production
change. A recommendation references the exact experiment(s) it was
derived from, carries the precise candidate configuration
provenance, and never overstates its evidence (status / robustness /
sample-size gate the claim).

`recommendation_id` is a deterministic hash of the category +
candidate experiment ids + parameters-changed fingerprint, so the
same evidence reproduces the same id (NO random UUIDs).

Designed to be consumed by 9F / a future AI interpreter and by
human review; the deterministic facts remain authoritative.
====================================================
"""

from dataclasses import dataclass, field
import hashlib
import json


def _jsonable(value):
    """"__ Future: prevent cross-contamination of numpy-ish values. """
    return value


def recommendation_id_for(category, candidate_ids, parameters_changed):
    """Deterministic id over the evidence fingerprint."""
    payload = json.dumps(
        {
            "category": category,
            "candidate_ids": sorted(candidate_ids),
            "parameters_changed": _params_key(parameters_changed),
        },
        sort_keys=True,
        default=list,
    ).encode("utf-8")
    return "rec-" + hashlib.sha1(payload).hexdigest()[:12]


def _params_key(parameters_changed):
    if isinstance(parameters_changed, dict):
        return {str(k): str(v) for k, v in sorted(parameters_changed.items())}
    if isinstance(parameters_changed, (list, tuple)):
        return [str(p) for p in parameters_changed]
    return str(parameters_changed)


@dataclass(frozen=True)
class Recommendation:
    """One immutable research recommendation."""

    recommendation_id: str = ""
    category: str = ""
    status: str = ""
    title: str = ""
    hypothesis: str = ""
    evidence_strength: str = ""

    affected_opportunity_categories: tuple = field(default_factory=tuple)
    affected_directions: tuple = field(default_factory=tuple)
    affected_symbols: tuple = field(default_factory=tuple)

    baseline_experiment_id: str = ""
    candidate_experiment_ids: tuple = field(default_factory=tuple)
    parameters_changed: dict = field(default_factory=dict)

    baseline_metrics: dict = field(default_factory=dict)
    candidate_metrics: dict = field(default_factory=dict)

    incremental_fills: float = 0.0
    recovered_opportunities: int = 0
    recovered_wins: int = 0
    recovered_losses: int = 0
    recovered_unsettled: int = 0
    recovered_R: float = 0.0
    recovered_pnl: float = 0.0
    incremental_R: float = 0.0

    expectancy_delta: float = 0.0
    win_rate_delta: float = 0.0
    profit_factor_delta: float = 0.0
    mae_delta: float = 0.0
    mfe_delta: float = 0.0

    robustness_status: str = ""
    sample_size: int = 0
    warnings: tuple = field(default_factory=tuple)
    recommendation_status: str = ""

    # -------------------------------------------------

    def to_dict(self):
        return {
            "recommendation_id": self.recommendation_id,
            "category": self.category,
            "status": self.status,
            "title": self.title,
            "hypothesis": self.hypothesis,
            "evidence_strength": self.evidence_strength,
            "affected_opportunity_categories": list(
                self.affected_opportunity_categories
            ),
            "affected_directions": list(self.affected_directions),
            "affected_symbols": list(self.affected_symbols),
            "baseline_experiment_id": self.baseline_experiment_id,
            "candidate_experiment_ids": list(self.candidate_experiment_ids),
            "parameters_changed": self.parameters_changed,
            "baseline_metrics": self.baseline_metrics,
            "candidate_metrics": self.candidate_metrics,
            "incremental_fills": self.incremental_fills,
            "recovered_opportunities": self.recovered_opportunities,
            "recovered_wins": self.recovered_wins,
            "recovered_losses": self.recovered_losses,
            "recovered_unsettled": self.recovered_unsettled,
            "recovered_R": self.recovered_R,
            "recovered_pnl": self.recovered_pnl,
            "incremental_R": self.incremental_R,
            "expectancy_delta": self.expectancy_delta,
            "win_rate_delta": self.win_rate_delta,
            "profit_factor_delta": self.profit_factor_delta,
            "mae_delta": self.mae_delta,
            "mfe_delta": self.mfe_delta,
            "robustness_status": self.robustness_status,
            "sample_size": self.sample_size,
            "warnings": list(self.warnings),
            "recommendation_status": self.recommendation_status,
        }