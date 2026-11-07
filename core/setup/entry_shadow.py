"""
====================================================

QuantEngine

Entry Model Shadow Comparison

Phase 4H -- reachability under THREE entry models, measured on the
SAME per-setup post-creation window, to answer one question:

    Is QuantEngine's structural analysis bad -- or is it simply
    trying to trade a RETEST strategy in markets that frequently
    CONTINUE without providing the retest?

The three models measured are:

    LIMIT_RETEST            the EXECUTABLE baseline: a resting order
                            at the retest level E. Fill primitive: a
                            candle trades through E (low <= E <= high
                            for a bullish long). The walk reproduces
                            the live lifecycle exactly: the structural
                            stop breach is checked BEFORE the fill on
                            every candle (invalidation beats a
                            same-bar fill, the backtester's step-3
                            before-step-4 order).

    MARKET_CONFIRMATION     SHADOW: a retest is "confirmed" when a
                            candle reaches E AND closes beyond E in
                            the trade direction; the market order
                            enters at that candle's CLOSE (react at
                            close, no look-ahead). It can never fill a
                            stop-ward sweep whose close is on the
                            wrong side of the level.

    BREAKOUT_CONTINUATION   SHADOW: the OPPOSITE hypothesis. Enter
                            when a candle exceeds the entry level in
                            the trade direction and CLOSES beyond it
                            (bullish: high > E and close > E). This is
                            precisely "price continued without giving
                            the retest". Enters at the candle's close.

For every trade-eligible structural setup the shadow walks the same
window (created+1 .. created+ENTRY_TRACKING_WINDOW_BARS) and records,
per model: whether its entry was REACHED, how many bars that took,
the effective entry distance (points + ATR), the hypothetical SL/TP
outcome under the exact win/loss convention of TradeSimulator.update
(stop checked before target on every candle), MAE / MFE (max adverse
/adverse... favorable excursion AFTER the entry bar), and the
missed-continuation diagnostic.

It also measures the RELATIONSHIP the Phase 4G order count depends
on: entry distance in ATR vs the fixed MAX_WAIT_BARS order expiry.
The Phase 4G eligible orders averaged ~15 ATRs from their entries
against a 30-bar expiry; this phase buckets that distance/expiry
relationship so the two thresholds can be judged BEFORE either moves.

RE-ZERO LOOK-AHEAD: the shadow reacts to a candle only when that
candle is passed to advance() -- the same one-bar no-look-ahead rule
as the live EntryTracker. Everything it measures is future price
action relative to the creating candle, is DIAGNOSTIC ONLY (read by
reports, never by an engine), and self-gates on ENABLE_ENTRY_SHADOW.

DOMAIN: the TradeSetupBuilder calls observe() on every TRADE-ELIGIBLE
canonical candidate it builds (one record per structural_id on first
appearance), so the population is exactly the "trade-eligible
structural set" defined by Phase 4G's eligibility gate -- not merely
the subset that minted orders. The Backtester calls advance() every
candle after the expiry pass, next to the EntryTracker.

====================================================
"""

from dataclasses import dataclass, field
from statistics import mean, median

from config import risk_settings

from core.setup.entry_feasibility import (
    ENTRY_MODE_BREAKOUT_CONTINUATION,
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
)

# Comparison models, in report order. LIMIT_RETEST is the executable
# baseline; the others are measured, never executable, this phase.
_COMPARISON_MODELS = (
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
)

# The config's SHADOW_ENTRY_MODES fallback when the key is absent.
SHADOW_MODES = (
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
)

# ATR-distance buckets for the distance-vs-expiry relationship.
_ATR_BUCKETS = (
    ("0-1", 0.0, 1.0),
    ("1-2", 1.0, 2.0),
    ("2-5", 2.0, 5.0),
    ("5-10", 5.0, 10.0),
    ("10-15", 10.0, 15.0),
    ("15-30", 15.0, 30.0),
    ("30+", 30.0, None),
)


def _mean(values):
    """Mean with an explicit zero-observations guard."""

    values = [v for v in values if v is not None]

    if not values:

        return 0.0

    return round(float(mean(values)), 6)


def _safe_div(numer, denom):
    """Integer-safe division that never divides by zero.

    A `None` numerator is treated as 0.0 -- a model can trigger and
    then resolve on its very next bar before any favorable or adverse
    excursion logged (e.g. an immediate stop), leaving those
    measurements unset until settle.
    """

    if numer is None:

        numer = 0.0

    if not denom:

        return 0.0

    return float(numer) / float(denom)


def _is_bullish(direction):
    return (direction or "").upper() == "BULLISH"


# ==========================================================
# Hypothetical fill
# ==========================================================


@dataclass(slots=True)
class ShadowFill:
    """
    One entry model's hypothetical result on one setup.

    `triggered` distinguishes "the model's entry was reached inside
    the tracking window" from "the market never gave this model its
    signal". The shadow models enter at the CLOSE of the trigger
    candle (react at close); the LIMIT model's hypothetical entry is
    the retest level E. Excursions are measured from the first bar
    AFTER the trigger bar -- never the trigger bar's pre-close
    internals, which occurred before the entry.
    """

    triggered: bool = False

    entry_bar: int = None

    entry_price: float = 0.0

    # entry_bar - creation_bar (bars until the potential entry).
    bars_until_entry: int = None

    # |entry_price - creation_price| on the point and ATR axes.
    effective_distance: float = None

    effective_distance_atr: float = None

    # "" until settled: "WIN" / "LOSS" / "UNRESOLVED".
    resolved: str = ""

    sl_hit: bool = False

    tp_hit: bool = False

    bars_until_sl: int = None  # bars after the entry bar

    bars_until_tp: int = None

    # Max adverse / favorable excursion in points and ATR, measured
    # from the first full bar after the entry bar to the resolution
    # bar (or the window end), capped at the stop/target levels the
    # way a real order would resolve.
    mae: float = None

    mfe: float = None

    mae_atr: float = None

    mfe_atr: float = None

    # Entry never reached under this model yet price moved at least
    # MISSED_CONTINUATION_TARGET_FRACTION of the way from E to the
    # target in the trade direction.
    missed_continuation: bool = False


# ==========================================================
# One setup's shadow
# ==========================================================


@dataclass(slots=True)
class EntryShadowState:
    """
    One trade-eligible structural setup's three-model comparison,
    accumulated across advance() calls and settled at window end.
    """

    # ---------------- Identity ----------------

    setup_id: str = ""

    structural_id: str = ""

    economic_fingerprint: str = ""

    direction: str = ""

    # ---------------- Economics ----------------

    entry: float = 0.0

    stop_loss: float = 0.0

    take_profit: float = 0.0

    # ATR_14 at creation (0.0 when the harness carried none).
    atr: float = 0.0

    # ---------------- At-creation snapshot ----------------

    creation_bar: int = 0

    creation_price: float = 0.0

    # The BASELINE limit-entry distance in ATRs -- the quantity the
    # distance-vs-expiry relationship is built from. It is identical
    # for all three models (the setup's own distance).
    entry_distance_atr: float = 0.0

    classification: str = ""

    # ---------------- Order context ----------------

    # Populated from the real order registry when the canonical setup
    # actually minted an order (slot cap / cooldown can leave a
    # borderline case unminted -- the price-action study still applies
    # to every trade-eligible setup, using the horizon
    # created + 1 + MAX_WAIT_BARS when no order exists).
    order_id: str = ""

    order_created_bar: int = None

    order_expires_bar: int = None

    # ---------------- The three models ----------------

    limit: ShadowFill = field(default_factory=ShadowFill)

    market: ShadowFill = field(default_factory=ShadowFill)

    breakout: ShadowFill = field(default_factory=ShadowFill)

    # Shared idea-level events (the ONE structural stop every model
    # shares -- the same stop a real order invalidates on).
    idea_invalidated: bool = False

    idea_invalidated_bar: int = None

    # Shared post-creation window extremes (for the continuation and
    # missed-continuation math).
    min_low_after: float = None

    max_high_after: float = None

    # The LIMIT retest arrived inside the real order's eligible window
    # ([created+1, expires_at_bar]) -- the fill the Price Engine's 30
    # band would have captured.
    reached_within_expiry: bool = False

    _settled: bool = False


# ==========================================================
# The shadow
# ==========================================================


class EntryShadow:
    """
    Stateful session tracker mirroring the EntryTracker's lifecycle
    (observe / advance / report / reset) but for the comparison.

    observe() captures trade-eligible canonical setups; advance()
    walks them one candle; report() aggregates the three models plus
    the ATR-distance-vs-expiry relationship; reset() drops all state.
    """

    def __init__(
        self,
        window_bars=None,
        missed_target_fraction=None,
        max_wait_bars=None,
    ):
        self._states = {}

        self._window_bars = (
            window_bars
            if window_bars is not None
            else getattr(
                risk_settings, "ENTRY_TRACKING_WINDOW_BARS", 60
            )
        )

        self._missed_fraction = (
            missed_target_fraction
            if missed_target_fraction is not None
            else getattr(
                risk_settings, "MISSED_CONTINUATION_TARGET_FRACTION", 0.5
            )
        )

        self._max_wait_bars = (
            max_wait_bars
            if max_wait_bars is not None
            else getattr(risk_settings, "MAX_WAIT_BARS", 30)
        )

    # ----------------------------------------------------------

    @staticmethod
    def _enabled():
        """Self-gate: the whole tracker is a no-op unless enabled."""

        return bool(getattr(risk_settings, "ENABLE_ENTRY_SHADOW", True))

    # ----------------------------------------------------------

    @staticmethod
    def _shadow_mode_enabled(mode):
        """Whether a shadow model is measured this run (default: all)."""

        configured = (
            getattr(risk_settings, "SHADOW_ENTRY_MODES", None)
            or SHADOW_MODES
        )

        return mode in tuple(configured)

    # ----------------------------------------------------------

    def reset(self):
        self._states = {}

    # ----------------------------------------------------------

    def states(self):
        return list(self._states.values())

    # ----------------------------------------------------------

    def count(self):
        return len(self._states)

    # ==========================================================
    # Observe (builder call site)
    # ==========================================================

    def observe(self, setup, bar=0, order_registry=None):
        """
        Register one setup population first-appearance-per-structural_id
        (the same dedup rule as the ZoneEligibility log and the
        EntryTracker). Skips candidates that were not trade-eligible:
        the shadow studies the trade-eligible population only.
        """

        if not self._enabled():

            return

        if not bool(getattr(setup, "trade_eligible", True)):

            return

        sid = (
            getattr(setup, "structural_id", "")
            or getattr(setup, "setup_id", "")
            or ""
        )

        if not sid or sid in self._states:

            return

        ef = getattr(setup, "entry_feasibility", None)

        creation_bar = int(
            getattr(ef, "creation_bar", 0) or bar or 0
        )

        state = EntryShadowState(
            setup_id=getattr(setup, "setup_id", "") or sid,
            structural_id=sid,
            economic_fingerprint=getattr(
                setup, "economic_fingerprint", ""
            )
            or "",
            direction=getattr(setup, "direction", "") or "",
            entry=float(getattr(setup, "entry", 0.0) or 0.0),
            stop_loss=float(
                getattr(setup, "stop_loss", 0.0) or 0.0
            ),
            take_profit=float(
                getattr(setup, "take_profit", 0.0) or 0.0
            ),
            atr=float(getattr(ef, "atr", 0.0)
                      or float(getattr(setup, "atr", 0.0) or 0.0)),
            creation_bar=creation_bar,
            creation_price=float(
                getattr(ef, "creation_price", 0.0)
                or float(getattr(setup, "observed_price", 0.0) or 0.0)
            ),
            entry_distance_atr=float(
                getattr(ef, "entry_distance_atr", 0.0) or 0.0
            ),
            classification=(
                getattr(ef, "classification", "") or ""
            ),
        )

        self._states[sid] = state

        self._attach_order(state, order_registry)

    # ----------------------------------------------------------

    def _attach_order(self, state, order_registry):
        """Pick up the real order (if the setup minted one) once."""

        if order_registry is None:

            return

        order = getattr(order_registry, "get_by_setup_id", None)

        if order is None:

            return

        order = order(state.setup_id) or order(state.structural_id)

        if order is None:

            return

        state.order_id = getattr(order, "order_id", "") or ""

        state.order_created_bar = getattr(order, "created_bar", None)

        state.order_expires_bar = getattr(order, "expires_at_bar", None)

    # ==========================================================
    # Advance (backtester call site)
    # ==========================================================

    def advance(self, candle, bar=None, order_registry=None):
        """
        Walk every open shadow one candle. Same one-bar rule as the
        live EntryTracker: the creation candle contributes nothing.
        Non-terminated shadows settle once the tracking window closes.
        """

        if not self._enabled():

            return

        for state in self._states.values():

            if state._settled:

                continue

            age = int(bar or 0) - state.creation_bar

            if age < 1:

                continue

            if not state.order_id:

                self._attach_order(state, order_registry)

            self._roll(state, candle, int(bar or 0))

            if age >= self._window_bars:

                self._settle(state, int(bar or 0))

    # ----------------------------------------------------------

    def _roll(self, state, candle, bar):
        """
        One bar of the three-model walk. Resolution (stop before
        target, TradeSimulator's exact convention) runs before the
        idea-level invalidation check, which runs before new fills --
        mirroring the backtester's step-3-before-step-4 ordering.
        """

        low = getattr(candle, "low", None)

        high = getattr(candle, "high", None)

        close = getattr(candle, "close", None)

        if low is not None and high is not None:

            self._roll_extremes(state, low, high)

        bull = _is_bullish(state.direction)

        entry = state.entry

        stop = state.stop_loss

        target = state.take_profit

        # 1. Resolve already-FILLED models (SL before TP). Models
        # that never triggered have no position and are never
        # resolved -- an entry bar of None on a slimmed stop breach
        # would otherwise fabricate a hypothetical position.
        for model in self._filled(state):

            if not model.triggered or model.resolved:

                continue

            self._resolve_position(state, model, low, high, bull, bar)

        if state.idea_invalidated:

            return

        # 2. Structural invalidation -- before any same-bar fill.
        if low is not None and (low if bull else high) is not None:

            if (
                bull
                and low is not None
                and low <= stop
            ) or (
                not bull
                and high is not None
                and high >= stop
            ):

                state.idea_invalidated = True

                state.idea_invalidated_bar = bar

                return

        # 3. New fills for the bar (models independently triggered).
        if low is not None and entry and entry > 0:

            self._maybe_fill_limit(state, low, high, entry, bar)

        if close is not None:

            self._maybe_fill_market(
                state, low, high, close, entry, bull, bar
            )

            self._maybe_fill_breakout(
                state, low, high, close, entry, bull, bar
            )

        # 4. Post-entry excursions (bars strictly after the entry bar).
        self._update_excursions(state, candle, bull, bar)

    # ----------------------------------------------------------

    @staticmethod
    def _roll_extremes(state, low, high):
        if state.min_low_after is None:

            state.min_low_after = low

        else:

            state.min_low_after = min(state.min_low_after, low)

        if state.max_high_after is None:

            state.max_high_after = high

        else:

            state.max_high_after = max(state.max_high_after, high)

    # ----------------------------------------------------------

    @staticmethod
    def _filled(state):
        return (
            state.limit,
            state.market,
            state.breakout,
        )

    # ----------------------------------------------------------

    @staticmethod
    def _maybe_fill_limit(state, low, high, entry, bar):
        """The EXECUTABLE primitive: a candle trades through E."""

        if state.limit.triggered:

            return

        if low is None or high is None:

            return

        if not (low <= entry <= high):

            return

        state.limit.triggered = True

        state.limit.entry_bar = bar

        state.limit.entry_price = round(entry, 6)

        state.limit.bars_until_entry = bar - state.creation_bar

        state.limit.effective_distance = round(
            abs(entry - state.creation_price), 6
        )

        state.limit.effective_distance_atr = round(
            _safe_div(
                abs(entry - state.creation_price), state.atr
            ),
            6,
        )

    # ----------------------------------------------------------

    @staticmethod
    def _maybe_fill_market(
        state, low, high, close, entry, bull, bar
    ):
        """SHADOW: reach E and close beyond it toward the direction."""

        if state.market.triggered:

            return

        if not EntryShadow._shadow_mode_enabled(
            ENTRY_MODE_MARKET_CONFIRMATION
        ):

            return

        if low is None or high is None:

            return

        if not (low <= entry <= high):

            return

        closed_beyond = close >= entry if bull else close <= entry

        if not closed_beyond:

            return

        state.market.triggered = True

        state.market.entry_bar = bar

        state.market.entry_price = round(close, 6)

        state.market.bars_until_entry = bar - state.creation_bar

        state.market.effective_distance = round(
            abs(close - state.creation_price), 6
        )

        state.market.effective_distance_atr = round(
            _safe_div(
                abs(close - state.creation_price), state.atr
            ),
            6,
        )

    # ----------------------------------------------------------

    @staticmethod
    def _maybe_fill_breakout(
        state, low, high, close, entry, bull, bar
    ):
        """
        SHADOW: the continuation hypothesis -- exceed E on the trade
        side AND close beyond it, i.e. "price left the zone without
        giving the retest".
        """

        if state.breakout.triggered:

            return

        if not EntryShadow._shadow_mode_enabled(
            ENTRY_MODE_BREAKOUT_CONTINUATION
        ):

            return

        if low is None or high is None:

            return

        exceeded = (
            high > entry if bull
            else low < entry
        )

        if not exceeded:

            return

        closed_beyond = close > entry if bull else close < entry

        if not closed_beyond:

            return

        state.breakout.triggered = True

        state.breakout.entry_bar = bar

        state.breakout.entry_price = round(close, 6)

        state.breakout.bars_until_entry = bar - state.creation_bar

        state.breakout.effective_distance = round(
            abs(close - state.creation_price), 6
        )

        state.breakout.effective_distance_atr = round(
            _safe_div(
                abs(close - state.creation_price), state.atr
            ),
            6,
        )

    # ----------------------------------------------------------

    @staticmethod
    def _resolve_position(state, model, low, high, bull, bar):
        """
        Mirror TradeSimulator.update exactly: on every candle the stop
        is checked BEFORE the target; a candle that hits both resolves
        as a LOSS at the stop level.
        """

        entry_price = model.entry_price

        stop = state.stop_loss

        target = state.take_profit

        sl_hit = (
            low is not None and low <= stop
            if bull
            else high is not None and high >= stop
        )

        if not sl_hit:

            tp_hit = (
                high is not None and high >= target
                if bull
                else low is not None and low <= target
            )

            if tp_hit:

                model.resolved = "WIN"

                model.tp_hit = True

                model.bars_until_tp = bar - model.entry_bar

                # Cap the favorable excursion at the actual target level.
                model.mfe = round(
                    max(model.mfe or 0.0, abs(target - entry_price)), 6
                )

            return

        model.resolved = "LOSS"

        model.sl_hit = True

        model.bars_until_sl = bar - model.entry_bar

        model.mae = round(
            max(model.mae or 0.0, abs(entry_price - stop)), 6
        )

    # ----------------------------------------------------------

    @staticmethod
    def _update_excursions(state, candle, bull, bar):
        """MAE / MFE for bars strictly after the entry bar.

        The entry bar itself is excluded: its low/high preceded the
        trigger's close, so they happened before the hypothetical
        entry and must not count against the position.
        """

        low = getattr(candle, "low", None)

        high = getattr(candle, "high", None)

        if low is None or high is None:

            return

        for model in (
            state.limit,
            state.market,
            state.breakout,
        ):

            if (
                not model.triggered
                or model.entry_bar is None
                or bar <= model.entry_bar
                or model.resolved
            ):

                continue

            entry = model.entry_price

            if bull:

                mae_cand = entry - low

                mfe_cand = high - entry

            else:

                mae_cand = high - entry

                mfe_cand = entry - low

            model.mae = round(
                max(model.mae or 0.0, max(mae_cand, 0.0)), 6
            )

            model.mfe = round(
                max(model.mfe or 0.0, max(mfe_cand, 0.0)), 6
            )

    # ----------------------------------------------------------

    def _settle(self, state, bar):
        """
        Window end: order context is final, the LIMIT entry's
        within-expiry status is decided, untriggered models record
        their missed continuations, and every triggered model is
        finalized (UNRESOLVED when it never hit either level).
        """

        if state.atr and state.atr > 0:

            for model in self._filled(state):

                if not model.triggered:

                    continue

                model.mae_atr = round(
                    _safe_div(model.mae, state.atr), 6
                )

                model.mfe_atr = round(
                    _safe_div(model.mfe, state.atr), 6
                )

        # Reached-within-expiry: LIMIT touch inside the real order's
        # eligible window ([created+1, expires_at_bar]).
        expiry = state.order_expires_bar

        if expiry is None:

            expiry = (
                state.creation_bar + 1 + self._max_wait_bars
            )

        if (
            state.limit.entry_bar is not None
            and state.limit.entry_bar <= expiry
        ):

            state.reached_within_expiry = True

        for model in self._filled(state):

            if not model.triggered:

                model.missed_continuation = (
                    self._missed_continuation(state)
                )

            elif not model.resolved:

                model.resolved = "UNRESOLVED"

        state._settled = True

    # ----------------------------------------------------------

    def _missed_continuation(self, state):
        """
        Entry never reached under a model, yet price moved at least
        MISSED_CONTINUATION_TARGET_FRACTION of the way from E to the
        target in the trade direction (the Phase 4F diagnostic).
        """

        bull = _is_bullish(state.direction)

        entry = state.entry

        target = state.take_profit

        span = abs(target - entry)

        if not span:

            return False

        if bull:

            achieved = max(
                state.max_high_after or entry, entry
            ) - entry

        else:

            achieved = entry - min(
                state.min_low_after or entry, entry
            )

        achieved = max(achieved, 0.0)

        return achieved >= span * self._missed_fraction

    # ==========================================================
    # Reporting
    # ==========================================================

    def report(self, direction=None):
        """
        Aggregate the three-model comparison plus the ATR-distance vs
        expiry relationship over the population (optionally
        direction-filtered).
        """

        states = [
            s
            for s in self._states.values()
            if direction is None
            or (s.direction or "").upper() == (direction or "").upper()
        ]

        total = len(states)

        models = {
            mode: self._report_model(states, mode)
            for mode in _COMPARISON_MODELS
        }

        # LIMIT-model extras surfaced alongside the fill outcome.
        limit_fills = sum(
            1 for s in states if s.limit.triggered
        )

        models[ENTRY_MODE_LIMIT_RETEST][
            "reached_within_expiry"
        ] = sum(1 for s in states if s.reached_within_expiry)

        models[ENTRY_MODE_LIMIT_RETEST][
            "idea_invalidated"
        ] = sum(1 for s in states if s.idea_invalidated)

        return {
            "total_setups": total,
            "window_bars": self._window_bars,
            "max_wait_bars": self._max_wait_bars,
            "models": models,
            "limit_fills": limit_fills,
            "atr_versus_expiry": self._report_atr_expiry(states),
        }

    # ----------------------------------------------------------

    @staticmethod
    def _report_model(states, mode):

        fills = [
            getattr(s, "limit" if mode == ENTRY_MODE_LIMIT_RETEST
                    else "market" if mode == ENTRY_MODE_MARKET_CONFIRMATION
                    else "breakout")
            for s in states
        ]

        triggered = [f for f in fills if f.triggered]

        def bands(fills_in):
            wins = sum(1 for f in fills_in if f.resolved == "WIN")

            losses = sum(1 for f in fills_in if f.resolved == "LOSS")

            unresolved = sum(
                1 for f in fills_in if f.resolved == "UNRESOLVED"
            )

            return wins, losses, unresolved

        wins, losses, unresolved = bands(triggered)

        return {
            "fills": len(triggered),
            "fill_rate_share": _safe_div(len(triggered), len(states)),
            "avg_bars_until_entry": _mean(
                f.bars_until_entry for f in triggered
            ),
            "median_bars_until_entry": (
                round(float(median(
                    [f.bars_until_entry for f in triggered]
                )), 6)
                if triggered
                else 0.0
            ),
            "avg_entry_distance_atr": _mean(
                f.effective_distance_atr for f in triggered
            ),
            "avg_mae": _mean(f.mae for f in triggered),
            "avg_mae_atr": _mean(f.mae_atr for f in triggered),
            "avg_mfe": _mean(f.mfe for f in triggered),
            "avg_mfe_atr": _mean(f.mfe_atr for f in triggered),
            "wins": wins,
            "losses": losses,
            "unresolved": unresolved,
            "missed_continuation": sum(
                1 for f in fills if f.missed_continuation
            ),
        }

    # ----------------------------------------------------------

    def _report_atr_expiry(self, states):
        """
        The Phase 4H specific measurement: LIMIT entry distance in ATR
        vs the fixed MAX_WAIT_BARS order expiry. Answers whether the
        ~15-ATR average distance vs a 30-bar expiry is a structural
        or a calibration story, BEFORE either threshold moves.
        """

        distances = [
            s.entry_distance_atr for s in states if s.entry_distance_atr > 0
        ]

        filled = [
            s.entry_distance_atr
            for s in states
            if s.limit.triggered and s.entry_distance_atr > 0
        ]

        unfilled = [
            s.entry_distance_atr
            for s in states
            if not s.limit.triggered and s.entry_distance_atr > 0
        ]

        # Point-biserial r between entry distance (x) and the binary
        # reached-within-expiry outcome (y==1). Degenerate inputs -> 0.
        correlation = self._point_biserial(
            [
                s.entry_distance_atr
                for s in states
                if s.entry_distance_atr > 0
            ],
            [
                1 if s.reached_within_expiry else 0
                for s in states
                if s.entry_distance_atr > 0
            ],
        )

        buckets = []

        labels = []

        for label, lo, hi in _ATR_BUCKETS:

            cohort = []

            for s in states:

                d = s.entry_distance_atr

                if d <= 0:

                    continue

                if d < lo or (hi is not None and d >= hi):

                    continue

                cohort.append(s)

            reached_expiry = [
                s for s in cohort if s.reached_within_expiry
            ]

            reached_window = [
                s
                for s in cohort
                if s.limit.entry_bar is not None
            ]

            never = [
                s
                for s in cohort
                if s.limit.entry_bar is None
            ]

            avg_bars = _mean(
                s.limit.bars_until_entry for s in reached_window
            )

            buckets.append(
                {
                    "bucket": label,
                    "count": len(cohort),
                    "reached_within_expiry": len(reached_expiry),
                    "reached_within_window": len(reached_window),
                    "never_reached": len(never),
                    "avg_bars_to_reach": (
                        avg_bars if reached_window else 0.0
                    ),
                }
            )

            labels.append(label)

        return {
            "correlation_fill_within_expiry": round(correlation, 6),
            "avg_entry_distance_atr_all": _mean(distances),
            "avg_entry_distance_atr_filled": _mean(filled),
            "avg_entry_distance_atr_unfilled": _mean(unfilled),
            "reached_within_expiry_share": _safe_div(
                sum(1 for s in states if s.reached_within_expiry),
                len(states),
            ),
            "buckets": buckets,
            "labels": labels,
        }

    # ----------------------------------------------------------

    @staticmethod
    def _point_biserial(xs, ys):
        """Pearson r between a continuous and a 0/1 vector."""

        n = len(xs)

        if n < 2 or len(ys) != n:

            return 0.0

        mx = sum(xs) / n

        my = sum(ys) / n

        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))

        sx = sum((x - mx) ** 2 for x in xs) ** 0.5

        sy = sum((y - my) ** 2 for y in ys) ** 0.5

        if not sx or not sy:

            return 0.0

        return cov / (sx * sy)


# ==========================================================
# Report formatting
# ==========================================================


def format_shadow_report(report, title="ENTRY MODEL COMPARISON"):
    """
    Render the shadow report for a printed BacktestReport block.
    """

    lines = [f"{title}"]

    total = report["total_setups"]

    lines.append(f"Setups Compared        : {total}")

    lines.append(
        f"Window / Expiry Bars   : {report['window_bars']} / "
        f"{report['max_wait_bars']}"
    )

    for mode, m in report["models"].items():

        lines.append("-" * 66)

        lines.append(f"Model : {mode}")

        lines.append(
            f"  Fills                 : {m['fills']} "
            f"({m['fill_rate_share'] * 100.0:.1f}%)"
        )

        lines.append(
            f"  Avg/Med Bars to Entry : {m['avg_bars_until_entry']} / "
            f"{m['median_bars_until_entry']}"
        )

        lines.append(
            f"  Avg Entry Distance    : {m['avg_entry_distance_atr']} ATR"
        )

        lines.append(
            f"  Avg MAE / MFE         : {m['avg_mae_atr']} / "
            f"{m['avg_mfe_atr']} ATR  "
            f"({m['avg_mae']} / {m['avg_mfe']} pts)"
        )

        lines.append(
            f"  Win / Loss / Unsettled: {m['wins']} / "
            f"{m['losses']} / {m['unresolved']}"
        )

        lines.append(
            f"  Missed Continuations  : {m['missed_continuation']}"
        )

    lines.append("-" * 66)

    atr = report["atr_versus_expiry"]

    lines.append(
        f"Limit fills within expiry     : "
        f"{report['models'][ENTRY_MODE_LIMIT_RETEST]['reached_within_expiry']}"
    )

    lines.append(
        f"Correlation (ATR dist, expiry): {atr['correlation_fill_within_expiry']}"
    )

    lines.append(
        f"Avg entry distance (filled)   : {atr['avg_entry_distance_atr_filled']} ATR"
    )

    lines.append(
        f"Avg entry distance (unfilled) : "
        f"{atr['avg_entry_distance_atr_unfilled']} ATR"
    )

    lines.append(f"ATR-DISTANCE vs {report['max_wait_bars']}-BAR EXPIRY:")

    header = (
        f"  {'Bucket':<8} {'Count':>5} {'<=Expiry':>9} "
        f"{'<=Window':>9} {'Never':>6} {'AvgBars':>8}"
    )

    lines.append(header)

    for bucket in atr["buckets"]:

        lines.append(
            f"  {bucket['bucket']:<8} {bucket['count']:>5} "
            f"{bucket['reached_within_expiry']:>9} "
            f"{bucket['reached_within_window']:>9} "
            f"{bucket['never_reached']:>6} "
            f"{bucket['avg_bars_to_reach']:>8}"
        )

    return "\n".join(lines)