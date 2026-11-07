"""
====================================================

QuantEngine

Institutional Swing Metrics

====================================================
"""


class SwingMetrics:

    def __init__(

        self,

        atr_period=14,

    ):

        self.atr_period = atr_period

        # True-Range memo keyed by the CURRENT (high/low) bar's
        # timestamp. scan() re-scans the full trailing window every
        # candle and recomputes atr() for ~every confirmed swing, so
        # without this each TR (max of three range terms) was
        # recomputed ~period x per swing per candle. The window only
        # slides one bar per continuation, so each physical bar's TR
        # is computed ONCE on first encounter and re-used for its
        # entire ~1000-candle residency -- a strict continuation
        # STILL computes one new TR per candle, and the summed TRs
        # are visited in ascending-position order, so the result is
        # bit-identical to the classic per-call loop. Swings up to
        # 1000 bars back are all covered (max_candles window).
        self._tr_cache = {}

        # ATR-level memo keyed by the newest bar's timestamp in the
        # 14-bar window. Each swing lives at one physical bar; as the
        # window slides that bar moves to lower positions but its
        # ATR window is the same physical series, so one dict get per
        # swing replaces the TR-level 14 lookups + 13 adds otherwise
        # paid for every swing every candle.
        self._atr_cache = {}

    # =====================================================

    def calculate(

        self,

        bars,

        index,

    ):

        impulse = self.impulse(

            bars,

            index,

        )

        displacement = self.displacement(

            bars,

            index,

        )

        volume_ratio = self.volume_ratio(

            bars,

            index,

        )

        return {

            "impulse": impulse,

            "displacement": displacement,

            "volume_ratio": volume_ratio,

            "atr_score": min(

                20.0,

                impulse * 10.0,

            ),

            "volume_score": min(

                15.0,

                volume_ratio * 7.5,

            ),

            "liquidity_score": 0.0,

            "bos_score": 0.0,

            "htf_score": 0.0,

            "time_score": self.time_score(

                bars,

                index,

            ),

        }

    # =====================================================

    def _true_range(

        self,

        high,

        low,

        prev_close,

    ):

        return max(

            high - low,

            abs(high - prev_close),

            abs(low - prev_close),

        )

    # =====================================================

    def _tr_for_index(

        self,

        bars,

        index,

    ):

        if index == 0:

            return 0.0

        current = bars[index]

        cached = self._tr_cache.get(
            current.timestamp
        )

        if cached is not None:

            return cached

        previous = bars[index - 1]

        tr = self._true_range(

            current.high,

            current.low,

            previous.close,

        )

        self._tr_cache[current.timestamp] = tr

        return tr

    # =====================================================

    def atr(

        self,

        bars,

        index,
    ):

        if index < self.atr_period:

            return None

        current = bars[index]

        cached = self._atr_cache.get(
            current.timestamp
        )

        if cached is not None:

            return cached

        total = 0.0

        for i in range(

            index - self.atr_period + 1,

            index + 1,

        ):

            total += self._tr_for_index(

                bars,

                i,
            )

        atr = total / self.atr_period

        self._atr_cache[current.timestamp] = atr

        return atr

    # =====================================================

    def reset(self):

        self._tr_cache.clear()

        self._atr_cache.clear()

    # =====================================================

    def impulse(

        self,

        bars,

        index,

    ):

        atr = self.atr(

            bars,

            index,

        )

        if atr is None or atr == 0:

            return 0.0

        candle = bars[index]

        return (candle.high - candle.low) / atr

    # =====================================================

    def displacement(

        self,

        bars,

        index,

    ):

        candle = bars[index]

        body = abs(

            candle.close - candle.open

        )

        rng = candle.high - candle.low

        if rng == 0:

            return 0.0

        return body / rng

    # =====================================================

    def volume_ratio(

        self,

        bars,

        index,

        lookback=20,

    ):

        if not hasattr(

            bars[index],

            "volume",

        ):

            return 1.0

        start = max(

            0,

            index - lookback,

        )

        total = 0.0

        count = 0

        for i in range(

            start,

            index,

        ):

            total += bars[i].volume

            count += 1

        if count == 0:

            return 1.0

        avg = total / count

        if avg <= 0:

            return 1.0

        return bars[index].volume / avg

    # =====================================================

    def time_score(

        self,

        bars,

        index,

    ):

        # NO-LOOKAHEAD: never derive this from len(bars).
        # SwingEngine.scan() re-scans the full trailing window on
        # every candle, so a "recency" term built as `len(bars) -
        # index` grows purely because FUTURE bars exist. That made
        # the same swing's score decay candle by candle and could
        # flip its `institutional` flag retroactively long after
        # confirmation -- a lookahead violation.
        #
        # A swing's score is therefore a pure function of the bars
        # inside its confirmation window, identical on every candle
        # that contains that window. Recency/freshness belongs in
        # downstream decision-time ranking by timestamp, not in a
        # permanent score, so this returns a constant
        # confirmation-freshness credit.
        return 5.0