"""
====================================================

QuantEngine

Institutional Displacement Scanner

Version 2.0

====================================================
"""

from core.common.base_engine import BaseEngine

from core.displacement.displacement import Displacement
from core.displacement.displacement_registry import DisplacementRegistry
from core.displacement.displacement_score import DisplacementScore
from core.common.logging_config import get_logger

log = get_logger(__name__)


class DisplacementScanner(BaseEngine):

    priority = 300

    dependencies = [
        "IndicatorEngine",
    ]

    enabled = True

    # ------------------------------------------------------------
    # Number of prior bars used to define the "liquidity" extreme
    # a displacement candle must sweep. This window only ever
    # looks at bars strictly before the current index, so it is
    # safe to use inside a chronological backtest (no look-ahead).
    # ------------------------------------------------------------

    LIQUIDITY_LOOKBACK = 20

    def __init__(self):

        super().__init__()

        self.registry = DisplacementRegistry()
        self.scorer = DisplacementScore()

        # Incremental window memo (STATUS 90, approved semantics
        # change). volume_ratio and liquidity_sweep are the only two
        # fields that read a LOOKBACK window of prior bars. For an
        # absolute bar the lookback window is a fixed set of bars, so
        # both values are stable once the bar can be evaluated (i >=
        # LOOKBACK). The memo is keyed by absolute index and gated on
        # bar identity so relocating the engine onto different data
        # recomputes instead of reusing stale values.
        self._window_cache = {}

    # ==================================================

    def analyze(self, context):

        self.registry.clear()

        bars = list(context.candles)

        if len(bars) < 2:

            context.displacement = self.registry
            return

        # Causal ATR: historical bar N must use ATR at N, not latest.
        # Prefer per-bar series aligned with bars window; fallback to
        # latest only when series unavailable (e.g. scripted harness).
        atr_series = None
        atr_latest = None

        if context.indicators:
            try:
                atr_series = context.indicators.get("ATR_14")
            except Exception:
                atr_series = None
            try:
                atr_latest = context.indicators.latest("ATR_14")
            except Exception:
                atr_latest = None

        # If we have a series, require it to be list-like aligned with bars.
        # If not, fall back to latest (real-time path) but log the fallback.
        use_series = (
            atr_series is not None
            and isinstance(atr_series, (list, tuple))
            and len(atr_series) == len(bars)
        )

        if not use_series and (atr_latest is None or atr_latest <= 0):
            context.displacement = self.registry
            return

        if use_series:
            # If all ATR values are None (warmup), no displacement can be scored
            if not any(v is not None and v > 0 for v in atr_series):
                context.displacement = self.registry
                return

        # ----------------------------------------------
        # Trend (for trend_alignment)
        # ----------------------------------------------
        # context.trend reflects the *current* trend state for
        # this run, not a per-historical-bar trend. That matches
        # how ATR is already used above (a single current value
        # applied across the historical scan) and is a known,
        # documented limitation rather than a silent one: a full
        # bar-by-bar historical trend requires TrendEngine to be
        # re-run per index, which is a larger architectural change
        # (see Phase 6 in the audit) and out of scope here.
        # ----------------------------------------------

        trend_direction = None

        if context.trend is not None:

            trend_direction = getattr(context.trend, "direction", None)

        # ----------------------------------------------
        # Relative Volume
        # ----------------------------------------------

        volume_ma = None

        volumes = []

        if hasattr(bars[0], "volume"):

            for c in bars:

                volumes.append(c.volume)

        # ----------------------------------------------

        consecutive = 0

        start_index = context.replay_index - len(bars)

        for i, candle in enumerate(bars):

            candle_range = candle.high - candle.low

            if candle_range <= 0:

                continue

            body = abs(candle.close - candle.open)

            body_ratio = body / candle_range

            if use_series:
                atr_at_bar = atr_series[i]
                if atr_at_bar is None or atr_at_bar <= 0:
                    atr_multiple = 0.0
                else:
                    atr_multiple = candle_range / atr_at_bar
            else:
                atr_multiple = candle_range / atr_latest

            # ------------------------------------------
            # Relative Volume (incremental)
            # ------------------------------------------
            # The lookback window [i-20, i) is a fixed set of bars
            # for a given absolute bar, and bars only ever move to
            # smaller relative positions as the trailing window
            # slides, so each absolute bar is evaluated at most once.

            cached = self._window_cache.get(start_index + i)

            if cached is not None and cached[0] is candle:

                # Use cached values only while the lookback window is
                # still fully inside the trailing deque (i >= 20).
                # Once the bar slides to i < 20 the original scan
                # zeroes both fields (its window is partially dropped),
                # so the cache must reproduce that here too.
                if i >= self.LIQUIDITY_LOOKBACK:

                    volume_ratio, liquidity_sweep = cached[1]

                else:

                    volume_ratio = 0.0
                    liquidity_sweep = False

            else:

                volume_ratio = 0.0

                if volumes and i >= 20:

                    avg = sum(volumes[i-20:i]) / 20

                    if avg > 0:

                        volume_ratio = candle.volume / avg

                # ------------------------------------------
                # Liquidity Sweep (incremental)
                # ------------------------------------------

                liquidity_sweep = False

                if i >= self.LIQUIDITY_LOOKBACK:

                    window = bars[i - self.LIQUIDITY_LOOKBACK:i]

                    if candle.close >= candle.open:

                        prior_low = min(b.low for b in window)

                        if candle.low < prior_low and candle.close > prior_low:

                            liquidity_sweep = True

                    else:

                        prior_high = max(b.high for b in window)

                        if candle.high > prior_high and candle.close < prior_high:

                            liquidity_sweep = True

                self._window_cache[start_index + i] = (
                    candle,
                    (volume_ratio, liquidity_sweep),
                )

            # ------------------------------------------
            # Close Position
            # ------------------------------------------

            if candle.close >= candle.open:

                close_position = (
                    candle.close - candle.low
                ) / candle_range

            else:

                close_position = (
                    candle.high - candle.close
                ) / candle_range

            # ------------------------------------------
            # Structure
            # ------------------------------------------

            broke_previous_high = False
            broke_previous_low = False

            if i > 0:

                prev = bars[i-1]

                if candle.high > prev.high:

                    broke_previous_high = True

                if candle.low < prev.low:

                    broke_previous_low = True

            # ------------------------------------------
            # Consecutive Impulse
            # ------------------------------------------

            if body_ratio >= 0.70:

                consecutive += 1

            else:

                consecutive = 0

            # ------------------------------------------

            direction = (

                "BULLISH"

                if candle.close >= candle.open

                else "BEARISH"

            )

            # ------------------------------------------
            # Trend Alignment
            # ------------------------------------------

            trend_alignment = (

                trend_direction is not None

                and direction == trend_direction

            )

            displacement = Displacement(

                index=i,

                timestamp=candle.timestamp,

                timeframe=context.market.timeframe,

                direction=direction,

                open=candle.open,

                high=candle.high,

                low=candle.low,

                close=candle.close,

                body=body,

                candle_range=candle_range,

                atr_multiple=atr_multiple,

                body_ratio=body_ratio,

                volume_ratio=volume_ratio,

            )

            displacement.close_position = close_position

            displacement.broke_previous_high = broke_previous_high

            displacement.broke_previous_low = broke_previous_low

            displacement.consecutive_impulse = consecutive

            displacement.liquidity_sweep = liquidity_sweep

            displacement.trend_alignment = trend_alignment

            self.scorer.calculate(displacement)

            self.registry.add(displacement)

        # -------------------------------------------------
        # Debug
        # -------------------------------------------------

        strong = self.registry.strong()

        log.debug(
            "Displacement scan: total=%d strong=%d",
            self.registry.count(),
            len(strong),
        )

        for d in strong[-5:]:

            log.debug(
                "[%d] %-8s Score=%5.1f Grade=%-8s ATR=%.2f Body=%.2f",
                d.index,
                d.direction,
                d.score,
                d.grade,
                d.atr_multiple,
                d.body_ratio,
            )

        context.displacement = self.registry

    # ==================================================

    def reset(self):

        self.registry.clear()

        self._window_cache.clear()