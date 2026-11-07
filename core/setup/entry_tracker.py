"""
====================================================

QuantEngine

Entry Tracker

Phase 4F -- post-creation retracement / continuation
measurement for every accepted setup.

PURPOSE (measurement, never signal):
    STEP 3 measures, for each accepted setup, what price actually
    DID after the creating candle:
        - the largest retracement toward the entry,
        - whether the entry was ever touched (low <= entry <= high),
        - the number of bars until the nearest approach / touch,
        - the largest continuation in the TARGET direction
          (STEP 5 MISSED_CONTINUATION proxy: price ran toward the
          take-profit without ever retracing to the limit entry).
    STEP 4 turns those per-setup measurements into an end-of-run
    ENTRY FEASIBILITY REPORT (totals by class, reached/un-reached,
    average/median distances, average remaining distance at
    expiration).

RE-ZERO LOOK-AHEAD:
    Everything the tracker records is FUTURE price action relative
    to the creating candle. It is DIAGNOSTIC ONLY: it is consumed
    solely by reports, never by TradeSetupBuilder / DecisionEngine /
    ExecutionEngine / RiskEngine / Backtester. The no-leak test
    proves that disabling the tracker leaves every order outcome
    byte-identical.

LIFECYCLE OF A STATE (per structural_id):
    recorded on the FIRST canonical appearance (EconomicSetupRegistry
    returns one canonical per cluster; the same structural setup is
    re-derived every candle, but one record per structural_id).
    extremes roll from creation_bar + 1 (the creation candle itself
    is ineligible under the no-same-candle look-ahead rule).
        FILLED        -> frozen immediately (entry was touched)
        INVALIDATED   -> frozen immediately (structural break first)
        EXPIRED       -> remaining distance snapshotted at the expiry
                         bar, then extremes keep rolling until the
                         tracking window so continuation/missed analysis
                         covers a real post-expiry window
        still PENDING / never ordered -> rolls to the window, then
                         resolves.
    Frozen states never touch signals.

GTG: DISTANCES ARE ATR-NORMALIZED -- no symbol-specific points.

====================================================
"""

from collections import Counter
from dataclasses import dataclass, field
from statistics import median

from config import risk_settings

from core.execution.order_registry import (
    EXPIRED,
    FILLED,
    INVALIDATED,
)
from core.setup.entry_feasibility import (
    create_entry_feasibility,
)

# Orders that freeze a state immediately (no further rolling).
_FREEZING_STATUSES = (FILLED, INVALIDATED)


@dataclass(slots=True)
class EntryTrackingState:
    """
    One accepted setup's post-creation price-action measurements.
    All roll fields are None until the first eligible candle.
    """

    # ---------------- Identity ----------------

    setup_id: str = ""

    structural_id: str = ""

    economic_fingerprint: str = ""

    direction: str = ""

    entry_mode: str = ""

    # ---------------- Economics ----------------

    entry: float = 0.0

    stop_loss: float = 0.0

    take_profit: float = 0.0

    atr: float = 0.0

    # ---------------- Feasibility (STEP 1) ----------------

    creation_bar: int = 0

    creation_price: float = 0.0

    entry_distance: float = 0.0

    entry_distance_pct: float = 0.0

    entry_distance_atr: float = 0.0

    entry_distance_ticks: float = 0.0

    classification: str = ""

    # ---------------- Retracement (STEP 3) ----------------

    min_low_after: float = None

    max_high_after: float = None

    # Closest price reached toward the entry (capped at the entry),
    # and the bar that produced it (post-creation).
    nearest_approach_price: float = None

    bars_until_nearest_approach: int = None

    # Fraction [0,1] of the entry distance the market actually
    # covered back toward the entry over the tracking window.
    retracement_toward_entry: float = None

    # True when a post-creation candle's range contained the entry
    # (low <= entry <= high) -- the fill primitive.
    entry_touched: bool = False

    entry_touch_bar: int = None

    bars_until_entry_touch: int = None

    # ---------------- Continuation / MISSED (STEP 5) ----------------

    # Extreme in the TARGET direction (bullish: lifetime high;
    # bearish: lifetime low) over the tracking window.
    target_direction_extreme: float = None

    # True when the entry was NEVER touched but price nevertheless
    # moved at least MISSED_CONTINUATION_TARGET_FRACTION of the
    # way from entry to target in the trade direction.
    missed_continuation: bool = False

    # ---------------- Terminal ----------------

    # FILLED / EXPIRED / INVALIDATED / PENDING (window elapsed with
    # an unresolved order) / NEVER_ORDERED (canonical never minted
    # an order -- e.g. slot-capped every bar).
    terminal_state: str = ""

    terminal_bar: int = None

    # Distance from the entry to the nearest price extreme at the
    # terminal EVENT (expiry bar for an EXPIRED order; the fill /
    # invalidation bar otherwise). 0.0 when the entry was reached.
    distance_remaining_at_terminal: float = None

    # ---------------- Internal ----------------

    _resolved: bool = False

    _expired_snapshot: bool = False


class EntryTracker:
    """
    Session-state diagnostic (lives on PipelineContext exactly like
    the OrderRegistry / EconomicSetupRegistry): created once per
    run, untouched by reset_cycle(), re-created on reset().

        track(setups, bar, order_registry)   called by ExecutionEngine
                                             AFTER economic funnel --
                                             canonical reps only.
        advance(candle, bar, order_registry) called by the Backtester
                                             AFTER the expiry pass.
        report()                             end-of-run summary.
        reset()                              fresh run.
    """

    def __init__(self, window_bars=None, missed_target_fraction=None):

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
                risk_settings,
                "MISSED_CONTINUATION_TARGET_FRACTION",
                0.5,
            )
        )

    # ==========================================================
    # Configuration / reset
    # ==========================================================

    def reset(self):

        self._states.clear()

    # ----------------------------------------------------------

    @staticmethod
    def _enabled():

        return bool(getattr(
            risk_settings, "ENABLE_ENTRY_DIAGNOSTICS", True
        ))

    # ==========================================================
    # Recording (STEP-by-STEP, from the ExecutionEngine chokepoint)
    # ==========================================================

    def track(self, setups, bar, order_registry=None):

        if not self._enabled():

            return

        for setup in setups or []:

            sid = (
                getattr(setup, "structural_id", "")
                or getattr(setup, "setup_id", "")
                or ""
            )

            if not sid or sid in self._states:

                continue

            self._states[sid] = self._build_state(setup, sid, bar)

    # ----------------------------------------------------------

    def _build_state(self, setup, sid, bar):

        snapshot = getattr(setup, "entry_feasibility", None)

        if snapshot is None:

            snapshot = create_entry_feasibility(
                setup,
                creation_price=getattr(
                    setup, "observed_price", 0.0
                ) or 0.0,
                atr=getattr(setup, "atr", 0.0) or 0.0,
                creation_bar=bar,
            )

        state = EntryTrackingState(
            setup_id=(getattr(setup, "setup_id", "") or sid),
            structural_id=sid,
            economic_fingerprint=getattr(
                setup, "economic_fingerprint", ""
            ) or "",
            direction=getattr(setup, "direction", "") or "",
            entry_mode=getattr(setup, "entry_mode", "") or "",
            entry=float(getattr(setup, "entry", 0.0) or 0.0),
            stop_loss=float(getattr(setup, "stop_loss", 0.0) or 0.0),
            take_profit=float(
                getattr(setup, "take_profit", 0.0) or 0.0
            ),
            atr=float(getattr(setup, "atr", 0.0) or 0.0),
            creation_bar=int(
                getattr(snapshot, "creation_bar", 0) or bar or 0
            ),
            creation_price=float(
                getattr(snapshot, "creation_price", 0.0) or 0.0
            ),
            entry_distance=getattr(
                snapshot, "entry_distance", 0.0
            ) or 0.0,
            entry_distance_pct=getattr(
                snapshot, "entry_distance_pct", 0.0
            ) or 0.0,
            entry_distance_atr=getattr(
                snapshot, "entry_distance_atr", 0.0
            ) or 0.0,
            entry_distance_ticks=getattr(
                snapshot, "entry_distance_ticks", 0.0
            ) or 0.0,
            classification=getattr(
                snapshot, "classification", ""
            ) or "",
        )

        return state

    # ==========================================================
    # Rolling (called by the Backtester after the expiry pass)
    # ==========================================================

    def advance(self, candle, bar=None, order_registry=None):

        if not self._enabled():

            return

        for state in self._states.values():

            if state._resolved:

                continue

            age = bar - state.creation_bar

            if age < 1:

                # The creation candle contributes nothing (the
                # no-same-candle look-ahead rule).
                continue

            order = self._lookup_order(state, order_registry)

            status = getattr(order, "status", "") if order else ""

            self._roll(state, candle, bar)

            if status in _FREEZING_STATUSES:

                self._settle(
                    state,
                    status,
                    getattr(order, "terminal_bar", None) or bar,
                    snapshot=True,
                )

                continue

            if status == EXPIRED:

                if not state._expired_snapshot:

                    # Snapshot the remaining distance AT the expiry
                    # bar, then keep rolling a full extra window so
                    # the continuation/missed analysis is honest.
                    state._expired_snapshot = True

                    state.terminal_state = EXPIRED

                    state.terminal_bar = (
                        getattr(order, "terminal_bar", None) or bar
                    )

                    state.distance_remaining_at_terminal = (
                        self._remaining_distance(state)
                    )

                if age >= self._window_bars:

                    self._settle(
                        state, EXPIRED, state.terminal_bar,
                        snapshot=False,
                    )

                continue

            # Still PENDING (or no order yet / never ordered):
            # roll to the horizon, then resolve.
            if age >= self._window_bars:

                terminal = status or "NEVER_ORDERED"

                self._settle(state, terminal, bar, snapshot=True)

    # ----------------------------------------------------------

    def _lookup_order(self, state, order_registry):

        if order_registry is None:

            return None

        return order_registry.get_by_setup_id(state.setup_id)

    # ----------------------------------------------------------

    def _roll(self, state, candle, bar):

        low = getattr(candle, "low", None)

        high = getattr(candle, "high", None)

        if low is not None:

            state.min_low_after = (
                low
                if state.min_low_after is None
                else min(state.min_low_after, low)
            )

        if high is not None:

            state.max_high_after = (
                high
                if state.max_high_after is None
                else max(state.max_high_after, high)
            )

        if low is not None and high is not None:

            if (
                not state.entry_touched
                and state.entry > 0
                and low <= state.entry <= high
            ):

                state.entry_touched = True

                state.entry_touch_bar = bar

                state.bars_until_entry_touch = (
                    bar - state.creation_bar
                )

        approach = self._approach_extreme(state)

        if approach is not None:

            state.nearest_approach_price = approach

            state.bars_until_nearest_approach = bar

        state.retracement_toward_entry = self._retracement(state)

    # ----------------------------------------------------------

    def _approach_extreme(self, state):
        """
        The price extreme closest to the entry, squeezed into the
        [min(entry, creation_price), max(entry, creation_price)]
        band so the "retracement toward the entry" can never exceed
        the original entry distance.

        Entry ABOVE creation price: approach improves as price RISES
            (nearest = min(lifetime high, entry)).
        Entry BELOW creation price: approach improves as price FALLS
            (nearest = max(lifetime low, entry)).
        """

        if state.entry >= state.creation_price:

            if state.max_high_after is None:

                return None

            return min(state.max_high_after, state.entry)

        if state.min_low_after is None:

            return None

        return max(state.min_low_after, state.entry)

    # ----------------------------------------------------------

    def _retracement(self, state):
        """
        Fraction [0, 1] of the entry distance the market covered back
        toward the entry over the tracking window.
        """

        span = abs(state.entry - state.creation_price)

        if state.entry_touched:

            return 1.0

        if span <= 0:

            return None

        approach = state.nearest_approach_price

        if approach is None:

            return 0.0

        covered = abs(approach - state.creation_price)

        return min(covered / span, 1.0)

    # ----------------------------------------------------------

    def _settle(self, state, terminal_state, terminal_bar, snapshot):

        state.terminal_state = terminal_state

        state.terminal_bar = terminal_bar

        state.target_direction_extreme = self._target_extreme(state)

        if snapshot:

            state.distance_remaining_at_terminal = (
                self._remaining_distance(state)
            )

        state.missed_continuation = self._missed_continuation(state)

        state._resolved = True

    # ----------------------------------------------------------

    @staticmethod
    def _target_extreme(state):

        if state.direction == "BULLISH":

            return state.max_high_after

        return state.min_low_after

    # ----------------------------------------------------------

    @staticmethod
    def _remaining_distance(state):
        """
        Distance from the entry to the NEAREST price extreme at the
        snapshot moment (mirror of OrderIntent.entry_distance_
        from_nearest_price): 0.0 whenever the entry was reached.
        """

        if state.entry_touched:

            return 0.0

        mn = state.min_low_after

        mx = state.max_high_after

        if mn is None or mx is None:

            return None

        if mn <= state.entry <= mx:

            return 0.0

        return min(
            abs(state.entry - mn),
            abs(state.entry - mx),
        )

    # ----------------------------------------------------------

    def _missed_continuation(self, state):
        """
        STEP 5: entry was never touched AND price nevertheless moved
        at least _missed_fraction of the way from entry to target in
        the trade direction. Diagnostic only -- never a signal.
        """

        if state.entry_touched:

            return False

        frac = float(self._missed_fraction or 0.5)

        if state.direction == "BULLISH":

            span = state.take_profit - state.entry

            if span <= 0:

                return False

            achieved = (
                (state.max_high_after or state.entry)
                - state.entry
            )

        else:

            span = state.entry - state.take_profit

            if span <= 0:

                return False

            achieved = (
                state.entry
                - (state.min_low_after or state.entry)
            )

        return achieved >= span * frac

    # ==========================================================
    # Report (STEP 3 / 4 / 11)
    # ==========================================================

    def report(self, direction=None):
        """
        End-of-run ENTRY FEASIBILITY aggregates. `direction` filters
        to BULLISH / BEARISH for the report's per-direction block.

        Returns a dict with counts by class and direction plus the
        averages the STEP 4 report requires. Every number is
        DIAGNOSTIC ONLY.
        """

        states = list(self._states.values())

        if direction is not None:

            states = [
                s for s in states
                if (s.direction or "").upper()
                == (direction or "").upper()
            ]

        total = len(states)

        by_class = Counter(s.classification for s in states)

        touched = [s for s in states if s.entry_touched]

        untouched = [s for s in states if not s.entry_touched]

        def _mean(values):

            vals = [v for v in values if v is not None]

            return (
                sum(vals) / len(vals)
                if vals
                else 0.0
            )

        distances = [s.entry_distance for s in states]

        atr_distances = [s.entry_distance_atr for s in states]

        pct_distances = [s.entry_distance_pct for s in states]

        retracements = [
            s.retracement_toward_entry for s in states
        ]

        remaining = [
            s.distance_remaining_at_terminal
            for s in states
            if s.distance_remaining_at_terminal is not None
        ]

        return {
            "total_setups": total,
            "by_class": dict(
                (k, by_class.get(k, 0))
                for k in (
                    "ENTRY_IMMEDIATE",
                    "ENTRY_NEAR",
                    "ENTRY_RETRACE",
                    "ENTRY_DEEP_RETRACE",
                    "ENTRY_TOO_FAR",
                )
            ),
            "entries_reached": len(touched),
            "entries_not_reached": len(untouched),
            "avg_entry_distance": round(_mean(distances), 4),
            "median_entry_distance": round(
                median(distances), 4
            ) if distances else 0.0,
            "avg_entry_distance_atr": round(
                _mean(atr_distances), 4
            ),
            "median_entry_distance_atr": round(
                median(atr_distances), 4
            ) if atr_distances else 0.0,
            "avg_entry_distance_pct": round(
                _mean(pct_distances), 6
            ),
            "avg_retracement_toward_entry": round(
                _mean(retracements), 4
            ),
            "avg_distance_remaining_at_terminal": round(
                _mean(remaining), 4
            ),
            "missed_continuation": sum(
                1 for s in states if s.missed_continuation
            ),
            "by_terminal_state": dict(
                Counter(s.terminal_state for s in states)
            ),
            "entry_modes": dict(
                Counter(s.entry_mode for s in states)
            ),
        }

    # ----------------------------------------------------------

    def states(self):

        return list(self._states.values())

    # ----------------------------------------------------------

    def count(self):

        return len(self._states)