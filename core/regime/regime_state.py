"""
====================================================

Institutional Regime State

====================================================
"""

from dataclasses import dataclass, field

from core.common.base_state import BaseState


@dataclass(slots=True)
class RegimeState(BaseState):

    # -------------------------------------------------
    # Final Classification
    # -------------------------------------------------

    regime: str = "UNKNOWN"

    grade: str = "F"

    score: float = 0.0

    confidence: float = 0.0

    institutional_score: float = 0.0
    
    # -------------------------------------------------
    # Institutional Scores
    # -------------------------------------------------

    trend_score: float = 0.0

    structure_score: float = 0.0

    momentum_score: float = 0.0

    volatility_score: float = 0.0

    liquidity_score: float = 0.0

    displacement_score: float = 0.0

    fvg_score: float = 0.0

    order_block_score: float = 0.0

    breaker_score: float = 0.0

    mitigation_score: float = 0.0

    # -------------------------------------------------
    # Diagnostics
    # -------------------------------------------------

    trend: str = ""

    momentum: str = ""

    volatility: str = ""

    liquidity: str = ""

    displacement: str = ""

    notes: list[str] = field(default_factory=list)