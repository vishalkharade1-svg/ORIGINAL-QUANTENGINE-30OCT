"""
====================================================

Trade Setup

====================================================
"""

from dataclasses import dataclass

from core.common.base_market_object import BaseMarketObject


@dataclass(slots=True)
class TradeSetup(BaseMarketObject):

    # -------------------------------------------------
    # Trade
    # -------------------------------------------------

    direction: str

    entry: float

    stop_loss: float

    take_profit: float

    # -------------------------------------------------
    # Quality
    # -------------------------------------------------

    risk_reward: float

    confidence: float

    score: float = 0.0

    exit_mode: str = "FIXED_TARGET"
    trailing_enabled: bool = False
    trailing_activation_r: float = 1.0
    trailing_distance_r: float = 0.5

    # Not derived from score. A value requires a separately validated,
    # provenance-pinned calibration model; None is the production default.
    calibrated_probability: float | None = None

    # -------------------------------------------------
    # Institutional Confluence
    # -------------------------------------------------

    trend: object = None

    regime: object = None

    order_block: object = None

    fvg: object = None

    liquidity: object = None

    breaker: object = None

    mitigation: object = None
