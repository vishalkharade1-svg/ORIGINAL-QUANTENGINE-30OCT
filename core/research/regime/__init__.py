"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- public surface

Under-what-conditions research over the frozen 9A-9J layers:

   * regime_types        -- closed vocabularies + frozen evidence
                            containers (MarketRegime, RegimeObservation,
                            ConditionalCell / ConditionalFinding,
                            FeatureSplit, WalkForward*)
   * indicators/detector -- pure decision-time regime indicators and
                            the MarketRegime detector (window ends AT
                            the decision bar; UNAVAILABLE=data-gated)
   * segmenter           -- 9A records -> RegimeObservations (9C
                            category + regime labels)
   * conditional         -- candidate vs baseline inside every regime
                            cell + recoveries + feature splits
   * walkforward         -- chronological expanding-train validation
   * multiple_testing    -- conservative familywise guard
   * report/engine       -- OpportunityDiscoveryEngine -> frozen,
                            deterministic, research-only RegimeReport

Boundaries: imports ONLY core.research.* surfaces; no production
internals; no random/uuid/datetime; no lookahead; no auto-promotion.
====================================================
"""

from core.research.regime.regime_types import (
    MarketRegime,
    RegimeObservation,
    ConditionalCell,
    ConditionalFinding,
    FeatureSplit,
    WalkForwardWindow,
    WalkForwardSummary,
    REGIME_DIMENSIONS,
    PRIMARY_REGIME_DIMENSIONS,
    UNAVAILABLE,
    TREND,
    RANGE,
    BULLISH,
    BEARISH,
    NEUTRAL,
    HIGH,
    NORMAL,
    LOW,
    EXPANSION,
    CONTRACTION,
    STRONG,
    ABSENT,
    SWEEPED,
    PRESENT,
    ACCUMULATION,
    MARKUP,
    DISTRIBUTION,
    MARKDOWN,
    TRANSITION,
)
from core.research.regime.indicators import (
    trend_vs_range,
    direction_structure,
    volatility_regime,
    atr_regime,
    displacement_strength,
    liquidity,
    fvg,
    order_block,
    wyckoff_phase,
)
from core.research.regime.detector import (
    detect_regime,
    regime_dimensions,
    primary_regime_dimensions,
    dimension_vocabulary,
    validate_dimension,
)
from core.research.regime.segmenter import (
    segment_observations,
    decision_bar,
    in_cell,
    cell_labels,
    regime_coverage,
    by_category,
)
from core.research.regime.conditional import (
    conditional_discovery,
    feature_splits,
)
from core.research.regime.walkforward import (
    temporal_windows,
    validate_conditional,
)
from core.research.regime.multiple_testing import (
    sidak_alpha,
    required_min_n,
    multiple_testing_summary,
)
from core.research.regime.engine import OpportunityDiscoveryEngine
from core.research.regime.report import RegimeReport

__all__ = [
    "MarketRegime",
    "RegimeObservation",
    "ConditionalCell",
    "ConditionalFinding",
    "FeatureSplit",
    "WalkForwardWindow",
    "WalkForwardSummary",
    "REGIME_DIMENSIONS",
    "PRIMARY_REGIME_DIMENSIONS",
    "UNAVAILABLE",
    "TREND",
    "RANGE",
    "BULLISH",
    "BEARISH",
    "NEUTRAL",
    "HIGH",
    "NORMAL",
    "LOW",
    "EXPANSION",
    "CONTRACTION",
    "STRONG",
    "ABSENT",
    "SWEEPED",
    "PRESENT",
    "ACCUMULATION",
    "MARKUP",
    "DISTRIBUTION",
    "MARKDOWN",
    "TRANSITION",
    "trend_vs_range",
    "direction_structure",
    "volatility_regime",
    "atr_regime",
    "displacement_strength",
    "liquidity",
    "fvg",
    "order_block",
    "wyckoff_phase",
    "detect_regime",
    "regime_dimensions",
    "primary_regime_dimensions",
    "dimension_vocabulary",
    "validate_dimension",
    "segment_observations",
    "decision_bar",
    "in_cell",
    "cell_labels",
    "regime_coverage",
    "by_category",
    "conditional_discovery",
    "feature_splits",
    "temporal_windows",
    "validate_conditional",
    "sidak_alpha",
    "required_min_n",
    "multiple_testing_summary",
    "OpportunityDiscoveryEngine",
    "RegimeReport",
]