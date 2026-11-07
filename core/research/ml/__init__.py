"""
====================================================

QuantEngine

ML / Statistical Research (Phase 9G)

DISCOVERS statistical relationships; it does NOT decide what gets
traded. Consumes the 9F decision-time FeatureEvidenceReport (causal
FeatureSnapshots + 9C/9D outcomes) and produces deterministic,
chronologically-split statistical / simple-ML / feature-interaction
research plus FIRST-CLASS Opportunity Recovery research.

   * temporal_split / walk_forward  -- chronological TRAIN|VALIDATION|
     OOS with NO temporal leakage and NO random shuffling; the 9F
     decision-time rule (features only from candles < decision_bar)
     is inherited and respected.
   * StatisticalBaseline / conditional_statistics / effect sizes --
     9G.1 descriptive association statistics (pure math / numpy).
   * SimpleModel (numpy logistic / decision tree; optional sklearn
     logistic / tree / forest) + targets ENTRY_REACHED / WIN /
     POSITIVE_R / EXPECTED_R / RECOVERY_SUCCESS -- 9G.2.
   * interaction_analysis -- 9G.3 feature-combination ASSOCIATION
     tables (e.g. Wyckoff + FVG + OB + Fibonacci + volatility +
     liquidity_sweep).
   * MlAnalyzer -> MlResearchReport -- the immutable orchestrator.

Dependency isolation (contract): the engine installs / compiles /
tests / runs WITHOUT sklearn. All statistical and numpy modes are
always available; every sklearn call is guarded and degrades to
ML_BACKEND_UNAVAILABLE gracefully. No production module ever imports
this package; there is no auto-promotion; everything is ASSOCIATION,
never causation, never a trade directive.
====================================================
"""

from core.research.ml.split import (
    temporal_split,
    walk_forward,
    TemporalSplit,
    WalkForward,
)
from core.research.ml.statistics import (
    StatisticalBaseline,
    conditional_statistics,
    effect_size_d,
    effect_size_h,
)
from core.research.ml.models import (
    encode_target,
    SimpleModel,
    NumpyLogisticRegression,
    NumpyDecisionTree,
    auc,
    ml_backend_available,
    ml_backend_status,
    ML_BACKEND_UNAVAILABLE,
)
from core.research.ml.interaction import interaction_analysis
from core.research.ml.analyzer import (
    MlAnalyzer,
    MlResearchReport,
    TARGETS,
)

__all__ = [
    "temporal_split",
    "walk_forward",
    "TemporalSplit",
    "WalkForward",
    "StatisticalBaseline",
    "conditional_statistics",
    "effect_size_d",
    "effect_size_h",
    "encode_target",
    "SimpleModel",
    "NumpyLogisticRegression",
    "NumpyDecisionTree",
    "auc",
    "ml_backend_available",
    "ml_backend_status",
    "ML_BACKEND_UNAVAILABLE",
    "interaction_analysis",
    "MlAnalyzer",
    "MlResearchReport",
    "TARGETS",
]