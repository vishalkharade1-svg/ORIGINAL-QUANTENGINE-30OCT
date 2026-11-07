"""
====================================================

QuantEngine

Breakout Asymmetry Research -- package init

PHASE 7 -- BULLISH VS BEARISH BREAKOUT ASYMMETRY RESEARCH

Completely SEVERED from the frozen production path
(PHASE 1-6E). Nothing in this package is imported by any
engine, the Backtester, the BrokerEngine, or the runtime.
It is a self-contained, offline research harness whose ONLY
input is a dataset of causal breakout records (the
CausalValidator's CausalValidationState objects), and whose
only output is evidence -- never a strategy change.

The seven asymmetry-origin hypotheses are decomposed
(7A-7E) so that "the bearish side is stronger" is traced to
WHERE it originates before ANY threshold is touched:

    7A  Causal dataset decomposition -- identical feature
        families extracted for bullish and bearish breakouts
        (displacement, ATR-normalized displacement, breakout
        distance, order-block width, FVG presence, structure
        type, liquidity event, prior swing geometry, volume,
        orderflow, candle body/wick, distance-from-market,
        setup age, time-since-structural-event, entry-stop,
        entry-target). NO thresholds are changed.

    7B  Outcome decomposition -- for each direction, the
        triggered population is split into Immediate/Max
        favorable excursion, Max adverse excursion, Stop hit,
        Target hit, Unsettled, Expired; distributions are
        compared, not just aggregate profit factor.

    7C  Where the asymmetry originates -- the G-classes:
        A market / B structure-generation / C setup-selection
        / D breakout-trigger / E stop-target geometry /
        F execution / G data-sample imbalance.

    7D  Counterfactual -- the SAME eligible setup population
        re-run under IDENTICAL execution assumptions for both
        directions, isolating setup-origin vs execution-origin
        asymmetry.

    7E  Only after evidence: an explicit directional policy
        (BREAKOUT_CONTINUATION + BULLISH / BEARISH branch),
        proposed as a research artifact, never applied here.

Because both directions in the source causal dataset already
walk the SAME causal filter (NEXT_BAR_OPEN trigger at close,
entry at next-bar open, CONSERVATIVE intrabar), any surviving
difference is setup-origin (B/C/D/E) rather than execution
(F) -- 7D makes that isolation explicit and verifies it.

Research discipline: the 5,000-bar sample is used to FORM a
hypothesis, never to tune thresholds. A proposed change always
goes Research -> Hypothesis -> Isolated research path ->
Unit tests -> Out-of-sample validation -> Comparison vs frozen
baseline -> only then production integration.
====================================================
"""

from core.research.breakout_asymmetry.features import (
    FeatureExtractor,
    extract_features,
)
from core.research.breakout_asymmetry.outcomes import (
    OutcomeClassifier,
    OutcomeProfile,
    classify_outcomes,
    compare_directions,
)
from core.research.breakout_asymmetry.origins import (
    AsymmetryOrigin,
    OriginDecomposition,
    decompose_origins,
)
from core.research.breakout_asymmetry.counterfactual import (
    CounterfactualStudy,
    counterfactual_study,
)
from core.research.breakout_asymmetry.report import (
    AsymmetryReport,
    build_report,
    load_dataset,
)

__all__ = [
    "AsymmetryOrigin",
    "AsymmetryReport",
    "CounterfactualStudy",
    "FeatureExtractor",
    "OriginDecomposition",
    "OutcomeClassifier",
    "OutcomeProfile",
    "build_report",
    "classify_outcomes",
    "compare_directions",
    "counterfactual_study",
    "decompose_origins",
    "extract_features",
    "load_dataset",
]