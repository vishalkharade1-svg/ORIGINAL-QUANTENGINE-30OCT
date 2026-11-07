"""
====================================================

Institutional Trend Engine

Pipeline Compatible

====================================================
"""

from core.common.base_engine import BaseEngine
from core.trend.trend_state import TrendState
from core.trend.trend_score import TrendScore
from core.common.logging_config import get_logger

log = get_logger(__name__)


class TrendEngine(BaseEngine):

    priority = 20

    dependencies = [
        "IndicatorEngine",
    ]

    enabled = True

    # -------------------------------------------------

    def __init__(self):

        super().__init__()

        self.scorer = TrendScore()

    # -------------------------------------------------

    def analyze(
        self,
        context,
    ):

        bars = list(context.candles)

        cache = context.indicators

        state = self._calculate(
            bars,
            cache,
        )

        context.trend = state

        return state

    # -------------------------------------------------

    def analyze_legacy(
        self,
        bars,
        cache,
    ):

        return self._calculate(
            bars,
            cache,
        )

    # -------------------------------------------------

    def _calculate(
        self,
        bars,
        cache,
    ):

        state = TrendState()

        # -------------------------------------------------
        # Validation
        #
        # WAITING_FOR_HISTORY / WARMUP is deliberately distinct
        # from RANGE: RANGE is a real market observation, while
        # these paths mean "we don't have an observation yet".
        # TrendState defaults to direction=regime="WARMUP" for
        # exactly this reason -- these branches are explicit for
        # clarity, not because the default would be wrong.
        # -------------------------------------------------

        if not bars:

            log.debug("No bars available yet (warmup).")
            state.direction = "WARMUP"
            state.regime = "WARMUP"
            return state

        if cache is None:

            log.debug("Indicator cache is None (warmup).")
            state.direction = "WARMUP"
            state.regime = "WARMUP"
            return state

        if not hasattr(cache, "latest"):

            log.warning("Invalid IndicatorCache passed to TrendEngine.")
            state.direction = "WARMUP"
            state.regime = "WARMUP"
            return state

        # -------------------------------------------------
        # Read Indicators
        # -------------------------------------------------

        price = bars[-1].close

        ema20 = cache.latest("EMA_20")
        ema50 = cache.latest("EMA_50")
        ema200 = cache.latest("EMA_200")

        atr = cache.latest("ATR_14")
        adx = cache.latest("ADX_14")
        rsi = cache.latest("RSI_14")

        log.debug(
            "price=%s ema20=%s ema50=%s ema200=%s atr=%s adx=%s rsi=%s",
            price, ema20, ema50, ema200, atr, adx, rsi,
        )

        # -------------------------------------------------
        # Wait until EMAs are available
        # -------------------------------------------------

        if None in (
            ema20,
            ema50,
            ema200,
        ):

            log.debug("Waiting for EMA history (warmup).")
            state.direction = "WARMUP"
            state.regime = "WARMUP"
            return state

        # -------------------------------------------------
        # Price Position
        # -------------------------------------------------

        state.price_above_ema20 = price > ema20
        state.price_above_ema50 = price > ema50
        state.price_above_ema200 = price > ema200

        state.price_below_ema20 = price < ema20
        state.price_below_ema50 = price < ema50
        state.price_below_ema200 = price < ema200

        # -------------------------------------------------
        # EMA Alignment
        # -------------------------------------------------

        bullish = ema20 > ema50 > ema200
        bearish = ema20 < ema50 < ema200

        state.ema_alignment = bullish or bearish

        log.debug("bullish_alignment=%s bearish_alignment=%s", bullish, bearish)

        if bullish:

            state.direction = "BULLISH"

        elif bearish:

            state.direction = "BEARISH"

        else:

            state.direction = "RANGE"

        # -------------------------------------------------
        # ADX Confirmation
        # -------------------------------------------------

        if adx is not None:

            state.adx_confirmed = adx >= 25

        else:

            state.adx_confirmed = False

        # -------------------------------------------------
        # RSI Momentum
        # -------------------------------------------------

        state.momentum = False

        if rsi is not None:

            if state.direction == "BULLISH":

                state.momentum = rsi >= 55

            elif state.direction == "BEARISH":

                state.momentum = rsi <= 45

        # -------------------------------------------------
        # Market Regime
        # -------------------------------------------------

        if state.direction == "RANGE":

            state.regime = "RANGE"

        elif state.adx_confirmed:

            state.regime = "TREND"

        else:

            state.regime = "WEAK_TREND"

        # -------------------------------------------------
        # Trend Score
        # -------------------------------------------------

        state.score = self.scorer.calculate(state)

        # Normalized strength/confidence so diagnostics and any
        # downstream confluence reads a meaningful 0..1 value
        # instead of a permanent 0.0.
        state.strength = state.score / 100.0

        state.confidence = state.score / 100.0

        log.debug(
            "direction=%s regime=%s score=%s ema_align=%s adx_confirmed=%s "
            "momentum=%s",
            state.direction, state.regime, state.score,
            state.ema_alignment, state.adx_confirmed, state.momentum,
        )

        return state