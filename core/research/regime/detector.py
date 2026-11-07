"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- regime detector

Combines the pure decision-time indicators into one MarketRegime for
a given opportunity decision bar. Each dimension is computed over the
bounded window ENDING AT the decision bar (inclusive); a dimension
that cannot be supported by the window is UNAVAILABLE and simply
omitted from the regime's available labels (honest, never fabricated).

MarketRegime is consumed by the segmenter and the conditional engine;
it carries no production state and makes no trade decision.
====================================================
"""

from core.research.regime.regime_types import (
    MarketRegime,
    REGIME_DIMENSIONS,
    PRIMARY_REGIME_DIMENSIONS,
    UNAVAILABLE,
)
from core.research.regime import indicators


def detect_regime(candles, decision_bar, lookback=40, atr_period=14,
                  stop_level=None, direction=""):
    """MarketRegime at `decision_bar` (window ends there, inclusive)."""
    points = indicators._window(candles, decision_bar, lookback)
    if not points:
        return MarketRegime()
    return MarketRegime(
        trend_vs_range=indicators.trend_vs_range(
            points, atr_period=atr_period),
        direction_structure=indicators.direction_structure(points),
        volatility_regime=indicators.volatility_regime(
            points, period=atr_period),
        atr_regime=indicators.atr_regime(points, atr_period=atr_period),
        displacement=indicators.displacement_strength(
            points, direction),
        liquidity=indicators.liquidity(
            points, direction, stop_level),
        wyckoff=indicators.wyckoff_phase(points),
        fvg=indicators.fvg(points, direction),
        order_block=indicators.order_block(points),
    )


def regime_dimensions():
    """Closed ordered list of regime dimensions (primary last: the
    conditional engine segments on these)."""
    return REGIME_DIMENSIONS


def primary_regime_dimensions():
    """Closed ordered tuple the conditional engine segments on."""
    return PRIMARY_REGIME_DIMENSIONS


def _dimension_labels():
    """The closed label vocabulary for every regime dimension."""
    return {
        "trend_vs_range": ("TREND", "RANGE"),
        "direction_structure": ("BULLISH", "BEARISH", "NEUTRAL"),
        "volatility_regime": ("HIGH", "NORMAL", "LOW"),
        "atr_regime": ("EXPANSION", "NEUTRAL", "CONTRACTION"),
        "displacement": ("STRONG", "NORMAL", "ABSENT"),
        "liquidity": ("SWEEPED", "NORMAL"),
        "wyckoff": ("ACCUMULATION", "MARKUP", "DISTRIBUTION",
                    "MARKDOWN", "TRANSITION"),
        "fvg": ("PRESENT", "ABSENT"),
        "order_block": ("PRESENT", "ABSENT"),
    }


def dimension_vocabulary():
    """{dimension: closed label tuple} -- deterministic, never invented."""
    return _dimension_labels()


def validate_dimension(dimension):
    if dimension not in REGIME_DIMENSIONS:
        raise ValueError(
            "unsupported regime dimension %r; supported: %s"
            % (dimension, ", ".join(REGIME_DIMENSIONS))
        )
    return dimension