"""
====================================================

Institutional Trend State

====================================================
"""

from dataclasses import dataclass

from core.common.base_state import BaseState


@dataclass(slots=True)
class TrendState(BaseState):

    # -------------------------------------------------
    # Trend
    # -------------------------------------------------

    direction: str = "WARMUP"

    regime: str = "WARMUP"

    # -------------------------------------------------
    # Scoring
    # -------------------------------------------------

    strength: float = 0.0

    confidence: float = 0.0

    score: float = 0.0

    # -------------------------------------------------
    # EMA Alignment
    # -------------------------------------------------

    ema_alignment: bool = False

    price_above_ema20: bool = False

    price_above_ema50: bool = False

    price_above_ema200: bool = False

    price_below_ema20: bool = False

    price_below_ema50: bool = False

    price_below_ema200: bool = False

    # -------------------------------------------------
    # Momentum
    # -------------------------------------------------

    momentum: bool = False

    adx_confirmed: bool = False