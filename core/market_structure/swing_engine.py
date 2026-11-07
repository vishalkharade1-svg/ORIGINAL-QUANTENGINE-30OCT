"""
====================================================

Institutional Swing Engine

====================================================
"""

from core.common.base_engine import BaseEngine

from core.market_structure.swing import Swing
from core.market_structure.swing_registry import SwingRegistry
from core.market_structure.swing_metrics import SwingMetrics
from core.scoring.swing_score_engine import SwingScoreEngine


class SwingEngine(BaseEngine):

    priority = 100

    dependencies = []

    enabled = True

    def __init__(
        self,
        timeframe="1m",
        left=3,
        right=3,
        minimum_score=70,
    ):

        super().__init__()

        self.timeframe = timeframe
        self.left = left
        self.right = right
        self.minimum_score = minimum_score

        self.registry = SwingRegistry()

        self.metrics = SwingMetrics()

        self.scorer = SwingScoreEngine()

        # Incremental fractal memo (STATUS 90, approved semantics
        # change). A bar at absolute index p qualifies as a swing
        # only if it is an extreme of the fixed bar window
        # [p-left, p+right]. Every reference bar in that window is
        # locked in the moment p becomes scannable (p >= left with a
        # full right window), so is_high/is_low for a given absolute
        # index can never change as the trailing window slides. The
        # scan therefore caches the fractal flags per absolute index
        # and only evaluates genuinely new window positions.
        #
        # Stage 1-3 hardening: the memo is BOUNDED (FIFO eviction of
        # the oldest absolute index). Eviction never changes signals:
        # a dropped entry is recomputed deterministically from the
        # same locked window if ever revisited (identical flags, only
        # recompute cost). Identity check below still guards against
        # cross-session stale reuse.
        self._fractal_cache = {}
        self._fractal_cache_order = []
        self.max_fractal_cache = 5000

    # ==================================================
    # Pipeline Entry
    # ==================================================

    def analyze(self, context):

        bars = list(context.candles)

        if len(bars) < (self.left + self.right + 1):
            return

        # Swing indices must be monotonically increasing across
        # the whole session, not relative to the trailing window.
        # context.candles is a deque(maxlen=1000), so a plain
        # positional index "rolls over" after 1000 bars and
        # distinct swings end up sharing index values -- which
        # makes BOSEngine's dedupe (`last_bull_break !=
        # swing.index`) wrongly suppress real breakouts.
        start_index = context.replay_index - len(bars)

        context.swings = self.scan(bars, start_index=start_index)

    # ==================================================
    # Standalone Scanner
    # ==================================================

    def scan(self, bars, start_index=0):

        self.registry.clear()

        previous = None

        total = len(bars)

        for i in range(
            self.left,
            total - self.right,
        ):

            current = bars[i]

            high = current.high
            low = current.low

            # ---------------- Fractal (incremental) ----------------
            # The fractal flags for an absolute bar depend only on the
            # fixed window [p-left, p+right], so they are computed once
            # per absolute index and reused as the trailing window
            # slides. Absolute index never collides between bars (it is
            # the session-wide position), so the memo is keyed by it.

            absolute_index = start_index + i

            cached = self._fractal_cache.get(absolute_index)

            # The cached fractal is only valid while the same bar
            # object still occupies this absolute slot. Bars are
            # hashable dataclass instances, so identity (not value)
            # is checked -- a relowner of the engine onto different
            # data (fresh session, another symbol) recomputes instead
            # of reusing stale flags.

            if cached is not None and cached[0] is current:

                is_high, is_low = cached[1]

            else:

                is_high = True
                is_low = True

                # ---------------- Left ----------------

                for j in range(
                    i - self.left,
                    i,
                ):

                    if bars[j].high >= high:
                        is_high = False

                    if bars[j].low <= low:
                        is_low = False

                # ---------------- Right ----------------

                for j in range(
                    i + 1,
                    i + self.right + 1,
                ):

                    if bars[j].high > high:
                        is_high = False

                    if bars[j].low < low:
                        is_low = False

                self._fractal_cache[absolute_index] = (current, (is_high, is_low))
                self._fractal_cache_order.append(absolute_index)
                while len(self._fractal_cache_order) > self.max_fractal_cache:
                    oldest = self._fractal_cache_order.pop(0)
                    self._fractal_cache.pop(oldest, None)

            if not is_high and not is_low:
                continue

            kind = "HIGH" if is_high else "LOW"

            price = high if is_high else low

            # ---------------- Duplicate Filtering ----------------

            if previous:

                if previous.kind == kind:

                    if kind == "HIGH":

                        if price <= previous.price:
                            continue

                        self.registry.remove(previous.id)

                    else:

                        if price >= previous.price:
                            continue

                        self.registry.remove(previous.id)

            # ---------------- Create Swing ----------------

            # Phase 12 confirmation semantics: this pivot
            # is evaluated only because bars up to
            # i + right exist, so the earliest bar that
            # could have confirmed it is index + right.
            # Stamped for downstream embargo; the rescan
            # already guarantees no emitted swing exceeds
            # the current bar's confirmation horizon.
            swing = Swing(

                index=start_index + i,

                timestamp=current.timestamp,

                timeframe=self.timeframe,

                price=price,

                high=high,

                low=low,

                kind=kind,

                confirmed=True,

                confirmed_bar=start_index + i + self.right,

            )

            metrics = self.metrics.calculate(
                bars,
                i,
            )

            swing.metadata = metrics

            self.scorer.score(swing)

            swing.institutional = (
                swing.score >= self.minimum_score
            )

            if swing.institutional:
                swing.add_tag("institutional")

            self.registry.add(swing)

            previous = swing

        return self.registry

    # ==================================================

    def latest(self):

        return self.registry.latest()

    def institutional(self):

        return self.registry.institutional()

    def majors(self):

        return self.registry.majors()

    def highs(self):

        return self.registry.highs()

    def lows(self):

        return self.registry.lows()

    # ==================================================

    def reset(self):

        self.registry.clear()

        self.metrics.reset()

        self._fractal_cache.clear()
        self._fractal_cache_order.clear()

    def cache_size(self):
        """Bounded memo size (Stage 1-3: never exceeds max)."""
        return len(self._fractal_cache)