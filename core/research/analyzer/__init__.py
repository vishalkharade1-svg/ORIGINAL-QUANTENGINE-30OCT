"""
====================================================

QuantEngine

Research Analyzer (Phase 9D)

The ANALYZER layer (NOT an optimizer). It consumes the frozen
baseline OpportunityRecords (9A) and the deterministic
CounterfactualOutcome collections (9C) and produces, for every
explicitly supplied alternative configuration, the evidence
that answers:

    * what happened?                    (baseline metrics)
    * what could have happened?         (experiment metrics)
    * why was the opportunity missed?   (baseline categories + reasons)
    * which configuration recovered it? (recovery transitions)
    * how many trades / wins / losses would that add, and at what
      cost in R / PnL / MAE?            (incremental / delta facts)
    * does it hold across directions,
      instruments, timeframes?          (grouped / directional metrics)
    * is it robust or a small-sample
      artifact?                         (robustness warnings)

It produces reports only. It NEVER ranks configurations, NEVER
recommends promoting a configuration to production, NEVER performs
any optimization, and NEVER claims statistical significance.

REUSE (not duplication): 9B ParameterGrid / metrics / experiment-id
machinery; 9C CounterfactualConfig + CounterfactualRunner +
opportunity categories; 9A OpportunityRecord facts.

BOUNDARIES: read-only inputs; COUNTERFACTUAL provenance only; no
production / journal / ledger / portfolio mutation; no lookahead;
no AI / ML; no automatic parameter selection or deployment.
====================================================
"""

from core.research.analyzer.baseline import (
    BaselineOutcome,
    baseline_view,
)
from core.research.analyzer.experiment_metrics import (
    metrics_for,
    group_metrics,
    group_sizes,
)
from core.research.analyzer.opportunity_analysis import (
    category_distribution,
    rejected_by_reason,
    missed_continuation_counts,
)
from core.research.analyzer.recovery_analysis import (
    RecoveryReport,
    transition_for,
    result_quality_for,
    experiment_state,
)
from core.research.analyzer.comparison import (
    ExperimentComparison,
    compare_baseline,
    compare_experiments,
)
from core.research.analyzer.robustness import assess as robustness_assess
from core.research.analyzer.experiment_matrix import ExperimentMatrix
from core.research.analyzer.research_report import ResearchReport
from core.research.analyzer.research_analyzer import (
    ResearchAnalyzer,
    ExperimentAnalysis,
)

__all__ = [
    "BaselineOutcome",
    "baseline_view",
    "metrics_for",
    "group_metrics",
    "group_sizes",
    "category_distribution",
    "rejected_by_reason",
    "missed_continuation_counts",
    "RecoveryReport",
    "transition_for",
    "result_quality_for",
    "experiment_state",
    "ExperimentComparison",
    "compare_baseline",
    "compare_experiments",
    "robustness_assess",
    "ExperimentMatrix",
    "ResearchReport",
    "ResearchAnalyzer",
    "ExperimentAnalysis",
]