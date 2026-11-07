"""
====================================================

QuantEngine

Feature Evidence (Phase 9F)

Deterministic, decision-time causal feature extraction for every
opportunity. This layer:

   * records an immutable FeatureSnapshot per opportunity at its exact
     decision bar (a causal CausalWindow with NO lookahead),
   * derives canonical confluence / market-structure / technical
     features (Wyckoff, market structure, ATR regime, Bollinger, SMA
     slope, OBV, liquidity sweep, FVG, displacement, order block,
     Fibonacci) -- all optional and data-gated,
   * feeds the produced evidence into the FROZEN 9E ConfluenceAnalysis
     surface,
   * builds read-only dependency tables (feature value -> entry-reached,
     recovery, WIN/LOSS, R, MAE/MFE, direction, symbol).

Boundaries: research-only, deterministic, immutable inputs, no
lookahead, no production imports, no strategy changes, no auto-
promotion. Features whose underlying data is unavailable are reported
as unavailable (never fabricated); footprint / volume-profile producers
are present but return CONFLUENCE_DATA_UNAVAILABLE until order-flow
data exists. Phase 7E NO-GO stays frozen.
====================================================
"""

from core.research.features.causal_window import (
    CausalWindow,
    CandlePoint,
    extract_causal_window,
)
from core.research.features.feature_snapshot import FeatureSnapshot
from core.research.features.confluence_features import ALL_PRODUCERS
from core.research.features.dependency_analysis import (
    DependencyAnalysis,
    FeatureDependency,
    build_dependency,
)
from core.research.features.feature_analyzer import (
    FeatureAnalyzer,
    FeatureEvidenceReport,
)

import core.research.features.indicators as indicators

__all__ = [
    "CausalWindow",
    "CandlePoint",
    "extract_causal_window",
    "FeatureSnapshot",
    "ALL_PRODUCERS",
    "DependencyAnalysis",
    "FeatureDependency",
    "build_dependency",
    "FeatureAnalyzer",
    "FeatureEvidenceReport",
    "indicators",
]