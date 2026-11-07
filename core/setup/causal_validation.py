"""
====================================================

QuantEngine

Causal Breakout Continuation Validation

Phase 4H -- the continuation hypothesis under STRICT
causal execution rules, before anything is executable:

    The Phase 4H Entry Model Comparison (STATUS 104) showed
    BREAKOUT_CONTINUATION reaching ~96% of trade-eligible setups
    with a high in-sample win rate. A high win rate is cheap to
    fake (enter where you can already see price went), so this
    phase re-runs that hypothesis with FOUR causal guarantees
    and reports the performance metrics a risk report requires.

The causal rules this module enforces:

  RULE 1 -- FREEZE AT CREATION. Every structural value (direction,
      entry level E, stop, target, identity, creation state) is
      snapshotted in observe() and NEVER read from the setup again.
      No future candle can change any of them.

  RULE 2 -- TRIGGER AT CLOSE. The breakout trigger is decided by
      information available only at the CLOSE of the trigger candle:
      BULLISH  high > E AND close > E
      BEARISH  low  < E AND close < E
      (exceed the OB reference level E on the trade side AND close
      beyond it -- "price left the zone without the retest"). The
      structural stop breach is checked BEFORE the trigger on every
      candle (the backtester step-3-before-step-4 order): a candle
      that also breaches the stop invalidates the idea, no trigger.

  RULE 3 -- NEXT-BAR EXECUTION. A trigger identified at bar N is
      entered at the OPEN of bar N+1 -- the first price reachable
      after the trigger close. Nothing is ever entered
      retrospectively inside the candle whose close produced the
      signal. A trigger on the last in-window bar has no executable
      next bar and is counted as a trigger without an entry.

  RULE 4 -- DETERMINISTIC INTRABAR RESOLUTION. If one OHLC candle
      spans both the stop and the target, the favorable outcome is
      never assumed. Three deterministic policies:
          CONSERVATIVE  stop first (LOSS)   -- Phase 4H primary
          OPTIMISTIC    target first (WIN)
          EXCLUDE       the trade is dropped from W/L accounting.
      Every trade records whether its resolution bar was ambiguous
      and the CONSERVATIVE (stop-first) outcome, so the report can
      render any policy without re-running the walk.

Performance reporting (Phase 4H step 9): continuation triggers,
causally executable entries, ambiguous candles/trades, fills,
wins/losses/unresolved/excluded, win rate, profit factor,
expectancy, average R, MAE/MFE, maximum drawdown and the
bullish / bearish split -- computed in R multiples (each loss is
-1R, each win is the trade's actual reward/risk ratio).

MARKET_CONFIRMATION is DIAGNOSED SEPARATELY (Phase 4H step 8).
Its 0 fills in the comparison are NOT read as "confirmation is
bad"; rejection-stage counters record exactly why no confirmation
entry triggered:
    candidates                       eligible setups walked
    rejected_structure               idea invalidated before any
                                     confirmation candle
    rejected_trend                   reached E but never closed
                                     beyond it in the direction
    rejected_distance                never reached E in the window
    rejected_volume / orderflow      the model has no such axis;
                                     kept at 0 so the counters prove
                                     the diagnosis is complete
    triggered                        confirmations that fired
    (rejected_structure + rejected_trend + rejected_distance +
     triggered == candidates when volume/orderflow are 0)

Per-candle order mirrors the backtester exactly: resolve any OPEN
position, then the structural-stop invalidation check, then new
signals. The MARKET_CONFIRMATION primitive is diagnosed on every
bar independently of the breakout position (a confirmed market
entry and a breakout can legally co-exist), exactly like the
STATUS 104 comparison.

The validator is DIAGNOSTIC ONLY: it reacts to a candle only when
that candle reaches advance(), is never consulted by any engine for
accept/avoid/order/fill decisions, produces no executable order, and
self-gates on ENABLE_CAUSAL_VALIDATION. LIMIT_RETEST and
MARKET_CONFIRMATION remain diagnostic; BREAKOUT_CONTINUATION stays a
shadow until the user reviews this report.

DOMAIN: the TradeSetupBuilder calls observe() on every
TRADE-ELIGIBLE canonical candidate (first appearance per
structural_id), so the population is exactly the trade-eligible
structural set from Phase 4G. The Backtester calls advance() every
candle after the expiry pass, next to the EntryShadow.

====================================================
"""

from dataclasses import dataclass

from config import risk_settings

# --------------------------------------------------
# Intrabar resolution policies (Rule 4)
# --------------------------------------------------

INTRABAR_CONSERVATIVE = "CONSERVATIVE"

INTRABAR_OPTIMISTIC = "OPTIMISTIC"

INTRABAR_EXCLUDE = "EXCLUDE"

INTRABAR_POLICIES = (
    INTRABAR_CONSERVATIVE,
    INTRABAR_OPTIMISTIC,
    INTRABAR_EXCLUDE,
)

# Next-bar execution convention (Rule 3). Single supported value.
CAUSAL_EXECUTION_NEXT_BAR_OPEN = "NEXT_BAR_OPEN"

# Confirmation rejection-reason vocabulary (Phase 4H step 8).
CONFIRM_REJECT_STRUCTURE = "structure"

CONFIRM_REJECT_TREND = "trend"

CONFIRM_REJECT_DISTANCE = "distance"


def _is_bullish(direction):
    return (direction or "").upper() == "BULLISH"


def _mean(values):
    """Mean with an explicit zero-observations guard."""

    values = [v for v in values if v is not None]

    if not values:

        return 0.0

    return round(float(sum(values) / len(values)), 6)


def _safe_div(numer, denom):
    """Integer-safe division that never divides by zero.

    A `None` numerator is treated as 0.0.
    """

    if numer is None:

        numer = 0.0

    if not denom:

        return 0.0

    return float(numer) / float(denom)


def _round(value, digits=6):
    """Round with an explicit None guard."""

    if value is None:

        return None

    return round(float(value), digits)


# ==========================================================
# One setup's causal record
# ==========================================================


@dataclass(slots=True)
class CausalValidationState:
    """
    One trade-eligible structural setup's causal breakout walk.

    Every structural value is a FROZEN snapshot from observe()
    (Rule 1); the breakout position is described by the trigger /
    entry / resolution fields (Rules 2-4).
    """

    # ---------------- Identity ----------------

    setup_id: str = ""

    structural_id: str = ""

    economic_fingerprint: str = ""

    direction: str = ""

    # ---------------- Frozen economics ----------------

    entry: float = 0.0

    stop_loss: float = 0.0

    take_profit: float = 0.0

    # ATR_14 at creation (0.0 when the harness carried none).
    atr: float = 0.0

    # ---------------- Frozen at-creation snapshot ----------------

    creation_bar: int = 0

    creation_price: float = 0.0

    entry_distance_atr: float = 0.0

    classification: str = ""

    # ---------------- Order context ----------------

    # Attached once from the real order registry when the canonical
    # setup actually minted an order (cooldown / slot caps can leave
    # a borderline case unminted). Reported for diagnosis; the causal
    # walk itself uses the full tracking window.
    order_id: str = ""

    order_created_bar: int = None

    order_expires_bar: int = None

    # ---------------- Breakout lifecycle (Rules 2-4) ----------------

    # Trigger (Rule 2): identified at the close of the trigger bar.
    breakout_triggered: bool = False

    breakout_trigger_bar: int = None

    breakout_trigger_close: float = None

    # Entry (Rule 3): the OPEN of the trigger bar + 1.
    breakout_entry_bar: int = None

    breakout_entry_price: float = None

    breakout_entered: bool = False

    breakout_causally_executable: bool = False

    # Resolution (Rule 4): "" / WIN / LOSS / UNRESOLVED / EXCLUDED.
    # `breakout_conservative` is the stop-first outcome (always the
    # CONSERVATIVE result regardless of the configured policy), so
    # the report can render any intrabar policy from one walk.
    breakout_resolved: str = ""

    breakout_conservative: str = ""

    breakout_sl_hit: bool = False

    breakout_tp_hit: bool = False

    breakout_ambiguous: bool = False

    breakout_ambiguous_bar: int = None

    breakout_mae: float = None

    breakout_mfe: float = None

    breakout_mae_atr: float = None

    breakout_mfe_atr: float = None

    # Settled R multiple: each LOSS pays -1R, each WIN pays the
    # trade's reward/risk ratio (computed from the actual open entry).
    breakout_r_multiple: float = None

    # ---------------- Market-confirmation diagnosis (step 8) ----------------

    # Reached the entry level E at least once inside the window.
    crossed_entry_level: bool = False

    # Reach E AND closed beyond it in the direction.
    confirmation_triggered: bool = False

    confirmation_trigger_bar: int = None

    # "" / structure / trend / distance (decided at settle).
    confirmation_rejected_reason: str = ""

    # ---------------- Shared ----------------

    idea_invalidated: bool = False

    idea_invalidated_bar: int = None

    _settled: bool = False


# ==========================================================
# The validator
# ==========================================================


class CausalValidator:
    """
    Stateful session tracker with the EntryShadow's lifecycle
    (observe / advance / report / reset) but under the Phase 4H
    causal rules.

    observe() captures trade-eligible canonical setups (frozen
    snapshot); advance() walks them one candle (no look-ahead: a
    candle is only read when it is passed in); report() renders the
    causal validation metrics under all three intrabar policies plus
    the MARKET_CONFIRMATION rejection diagnosis; reset() drops state.
    """

    def __init__(
        self,
        window_bars=None,
        intrabar_policy=None,
    ):
        self._states = {}

        self._window_bars = (
            window_bars
            if window_bars is not None
            else getattr(
                risk_settings, "ENTRY_TRACKING_WINDOW_BARS", 60
            )
        )

        configured_policy = getattr(
            risk_settings, "INTRABAR_POLICY", INTRABAR_CONSERVATIVE
        )

        if intrabar_policy in INTRABAR_POLICIES:

            self._intrabar_policy = intrabar_policy

        elif configured_policy in INTRABAR_POLICIES:

            self._intrabar_policy = configured_policy

        else:

            self._intrabar_policy = INTRABAR_CONSERVATIVE

    # ----------------------------------------------------------

    @staticmethod
    def _enabled():
        """Self-gate: the whole tracker is a no-op unless enabled."""

        return bool(
            getattr(risk_settings, "ENABLE_CAUSAL_VALIDATION", True)
        )

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
    # Observe (builder call site) -- Rule 1: freeze
    # ==========================================================

    def observe(self, setup, bar=0, order_registry=None):
        """
        Register one setup population first-appearance-per-structural_id
        (the same dedup rule as the EntryShadow / ZoneEligibility /
        EntryTracker). Skips candidates that were not trade-eligible.

        The state is a FULL FROZEN SNAPSHOT: the setup object (and
        any bar ever seen after) can be mutated freely without
        touching this record.
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

        state = CausalValidationState(
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
            atr=float(
                getattr(ef, "atr", 0.0)
                or float(getattr(setup, "atr", 0.0) or 0.0)
            ),
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
        Walk every open causal record one candle. Same one-bar rule
        as the live EntryTracker: the creation candle contributes
        nothing. Records settle once the tracking window closes.
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
        One bar of the causal walk. Per-candle order mirrors the
        backtester: resolve any OPEN position, then the structural
        stop invalidation, then new signals. The MARKET_CONFIRMATION
        primitive is diagnosed independent of the breakout position.
        """

        low = getattr(candle, "low", None)

        high = getattr(candle, "high", None)

        close = getattr(candle, "close", None)

        open_ = getattr(candle, "open", None)

        bull = _is_bullish(state.direction)

        entry = state.entry

        stop = state.stop_loss

        # ---------------- A. Position already open ----------------

        if state.breakout_entered and not state.breakout_resolved:

            if bar >= state.breakout_entry_bar:

                self._update_excursions(state, low, high, bull, bar)

            self._resolve_position(state, low, high, bull, bar)

            if state.breakout_resolved:

                state.breakout_r_multiple = self._r_multiple(
                    state, state.breakout_resolved
                )

        # ---------------- B. Next-bar market entry ----------------

        # Rule 3: a trigger at bar N fills at the OPEN of bar N+1.
        # The entry bar's own intrabar range is then resolved
        # normally (SL before TP), because the position was real
        # from the open -- so this fill runs BEFORE the same bar's
        # structural-invalidation check, unlike a resting-limit fill.
        if (
            state.breakout_triggered
            and not state.breakout_entered
            and state.breakout_entry_bar is not None
            and bar == state.breakout_entry_bar
        ):

            fill = open_

            if fill is None:

                fill = close

            state.breakout_entry_price = _round(fill) or 0.0

            state.breakout_entered = True

            if bar >= state.breakout_entry_bar:

                self._update_excursions(state, low, high, bull, bar)

            self._resolve_position(state, low, high, bull, bar)

            if state.breakout_resolved:

                state.breakout_r_multiple = self._r_multiple(
                    state, state.breakout_resolved
                )

        # ---------------- C. Structural-stop invalidation ----------------

        if low is not None and high is not None and (
            (bull and low <= stop)
            or (not bull and high >= stop)
        ):

            state.idea_invalidated = True

            state.idea_invalidated_bar = bar

        if state.idea_invalidated:

            # A dead idea fires nothing else (any position that was
            # open already resolved its stop above).
            return

        # ---------------- D. Confirmation diagnosis ----------------

        # The MARKET_CONFIRMATION primitive runs on every bar,
        # independent of the breakout (mirrors the comparison, where
        # a confirmed market entry and a breakout can co-exist).
        if not state.confirmation_triggered:

            crossed = (
                low is not None
                and high is not None
                and low <= entry <= high
            )

            if crossed:

                state.crossed_entry_level = True

                if close is not None:

                    closed_beyond = (
                        close >= entry if bull else close <= entry
                    )

                    if closed_beyond:

                        state.confirmation_triggered = True

                        state.confirmation_trigger_bar = bar

        # ---------------- E. Breakout trigger ----------------

        if state.breakout_triggered:

            return

        # Rule 2: only the trigger candle's own range and close.
        triggered = (
            bull
            and high is not None
            and close is not None
            and high > entry
            and close > entry
        ) or (
            not bull
            and low is not None
            and close is not None
            and low < entry
            and close < entry
        )

        if not triggered:

            return

        state.breakout_triggered = True

        state.breakout_trigger_bar = bar

        state.breakout_trigger_close = _round(close)

        state.breakout_entry_bar = bar + 1

        age = bar - state.creation_bar

        state.breakout_causally_executable = (
            age + 1 <= self._window_bars
        )

    # ----------------------------------------------------------

    @staticmethod
    def _update_excursions(state, low, high, bull, bar):
        """
        MAE / MFE for the breakout position. Because the entry is at
        the OPEN, the ENTRY bar's post-open range is real exposure
        and DOES count (unlike a close-entry, whose entry-bar
        internals preceded the fill).
        """

        if low is None or high is None:

            return

        entry = state.breakout_entry_price

        if entry is None or entry <= 0:

            return

        if bull:

            mae_cand = entry - low

            mfe_cand = high - entry

        else:

            mae_cand = high - entry

            mfe_cand = entry - low

        state.breakout_mae = _round(
            max(state.breakout_mae or 0.0, max(mae_cand, 0.0))
        )

        state.breakout_mfe = _round(
            max(state.breakout_mfe or 0.0, max(mfe_cand, 0.0))
        )

    # ----------------------------------------------------------

    def _resolve_position(self, state, low, high, bull, bar):
        """
        Rule 4: SL/TP resolution with deterministic intrabar
        ambiguity handling. The CONSERVATIVE (stop-first) outcome is
        always recorded so the report can render any policy from one
        walk.
        """

        entry_price = state.breakout_entry_price

        stop = state.stop_loss

        target = state.take_profit

        sl_hit = (
            low is not None and low <= stop
            if bull
            else high is not None and high >= stop
        )

        tp_hit = (
            high is not None and high >= target
            if bull
            else low is not None and low <= target
        )

        ambiguous = bool(sl_hit) and bool(tp_hit)

        state.breakout_ambiguous = (
            state.breakout_ambiguous or ambiguous
        )

        if ambiguous:

            state.breakout_ambiguous_bar = bar

        if state.breakout_mae is None:

            state.breakout_mae = 0.0

        if state.breakout_mfe is None:

            state.breakout_mfe = 0.0

        # Caps at the levels a real order would resolve at.
        state.breakout_mae = _round(
            max(state.breakout_mae, abs(entry_price - stop))
        )

        state.breakout_mfe = _round(
            max(state.breakout_mfe, abs(target - entry_price))
        )

        if ambiguous:

            policy = self._intrabar_policy

            state.breakout_conservative = (
                "LOSS" if sl_hit else "WIN"
            )

            if policy == INTRABAR_OPTIMISTIC:

                state.breakout_resolved = "WIN"

                state.breakout_tp_hit = True

                return

            if policy == INTRABAR_EXCLUDE:

                state.breakout_resolved = "EXCLUDED"

                state.breakout_sl_hit = sl_hit

                return

            # CONSERVATIVE: stop first.
            state.breakout_resolved = "LOSS"

            state.breakout_sl_hit = True

            return

        if sl_hit:

            state.breakout_resolved = "LOSS"

            state.breakout_sl_hit = True

            state.breakout_conservative = "LOSS"

            return

        if tp_hit:

            state.breakout_resolved = "WIN"

            state.breakout_tp_hit = True

            state.breakout_conservative = "WIN"

            return

        state.breakout_conservative = "UNRESOLVED"

    # ----------------------------------------------------------

    @staticmethod
    def _r_multiple(state, outcome):
        """
        R multiple from the ACTUAL open fill: each LOSS pays -1R,
        each WIN pays reward / risk.

        The live backtester fills a WIN at the target and a LOSS at
        the stop, so a WIN's R is the reward/risk ratio and a LOSS's
        R is -1 exactly.
        """

        risk = abs(state.breakout_entry_price - state.stop_loss)

        if outcome == "LOSS":

            return round(-_safe_div(
                abs(state.breakout_entry_price - state.stop_loss),
                risk,
            ), 6)

        if outcome == "WIN":

            reward = abs(state.take_profit - state.breakout_entry_price)

            return round(_safe_div(reward, risk), 6)

        return 0.0

    # ----------------------------------------------------------

    def _settle(self, state, bar):
        """
        Window end: alternate-history positions finalize, confirmation
        rejection reasons are decided, and the R multiple / ATR
        excursions are fixed.
        """

        if state.atr and state.atr > 0:

            if state.breakout_entered:

                state.breakout_mae_atr = round(
                    _safe_div(state.breakout_mae, state.atr), 6
                )

                state.breakout_mfe_atr = round(
                    _safe_div(state.breakout_mfe, state.atr), 6
                )

        if (
            state.breakout_triggered
            and state.breakout_entered
            and not state.breakout_resolved
        ):

            state.breakout_resolved = "UNRESOLVED"

            state.breakout_conservative = "UNRESOLVED"

            state.breakout_r_multiple = 0.0

        if state.breakout_entered and state.breakout_r_multiple is None:

            state.breakout_r_multiple = self._r_multiple(
                state, state.breakout_resolved
            )

        # Confirmation rejection reason (structure > trend > distance).
        if not state.confirmation_triggered:

            if state.idea_invalidated:

                state.confirmation_rejected_reason = (
                    CONFIRM_REJECT_STRUCTURE
                )

            elif not state.crossed_entry_level:

                state.confirmation_rejected_reason = (
                    CONFIRM_REJECT_DISTANCE
                )

            else:

                state.confirmation_rejected_reason = (
                    CONFIRM_REJECT_TREND
                )

        state._settled = True

    # ==========================================================
    # Reporting
    # ==========================================================

    def report(self, direction=None):
        """
        Aggregate the causal validation metrics under all three
        intrabar policies plus the MARKET_CONFIRMATION diagnosis over
        the population (optionally direction-filtered).
        """

        states = [
            s
            for s in self._states.values()
            if direction is None
            or (s.direction or "").upper() == (direction or "").upper()
        ]

        total = len(states)

        breakout = {
            policy: self._report_breakout(states, policy)
            for policy in INTRABAR_POLICIES
        }

        return {
            "eligible_setups": total,
            "window_bars": self._window_bars,
            "execution": CAUSAL_EXECUTION_NEXT_BAR_OPEN,
            "intrabar_policy": self._intrabar_policy,
            "breakout": breakout,
            "confirmation": self._report_confirmation(states),
        }

    # ----------------------------------------------------------

    @staticmethod
    def _report_breakout(states, policy):
        """
        Phase 4H step 9 metrics for one intrabar policy. Derives the
        policy outcome from the recorded CONSERVATIVE result + the
        ambiguity flag, so all three policies share one walk.
        """

        entered = [s for s in states if s.breakout_entered]

        triggered = sum(1 for s in states if s.breakout_triggered)

        fills = len(entered)

        ambiguous = len(
            [s for s in entered if s.breakout_ambiguous]
        )

        resolved = [
            CausalValidator._policy_outcome(s, policy)
            for s in entered
        ]

        wins = resolved.count("WIN")

        losses = resolved.count("LOSS")

        unresolved = resolved.count("UNRESOLVED")

        excluded = resolved.count("EXCLUDED")

        settled = wins + losses

        win_rate = _safe_div(wins, settled)

        # R-based performance over the settled set, in insertion
        # order (dict order == observe order == the walk order).
        rs = []

        for s, out in zip(entered, resolved):

            if out == "WIN":

                rs.append(_safe_div(
                    abs(s.take_profit - s.breakout_entry_price),
                    abs(s.breakout_entry_price - s.stop_loss),
                ))

            elif out == "LOSS":

                rs.append(-1.0)

        gross_profit = sum(r for r in rs if r > 0)

        gross_loss = -sum(r for r in rs if r < 0)

        profit_factor = _safe_div(gross_profit, gross_loss)

        expectancy = _mean(rs)

        # Max drawdown of the running R equity curve.
        peak = 0.0

        running = 0.0

        max_dd = 0.0

        for r in rs:

            running += r

            peak = max(peak, running)

            max_dd = max(max_dd, peak - running)

        entry_bars = [
            (
                s.breakout_entry_bar - s.creation_bar
                if s.breakout_entry_bar is not None
                else None
            )
            for s in entered
        ]

        return {
            "triggers": triggered,
            "triggers_without_executable_next_bar": triggered - fills,
            "fills": fills,
            "ambiguous_trades": ambiguous,
            "wins": wins,
            "losses": losses,
            "unresolved": unresolved,
            "excluded": excluded,
            "settled": settled,
            "win_rate": round(win_rate, 6),
            "gross_profit_r": round(gross_profit, 6),
            "gross_loss_r": round(gross_loss, 6),
            "profit_factor": round(profit_factor, 6),
            "expectancy_r": expectancy,
            "average_r": expectancy,
            "max_drawdown_r": round(max_dd, 6),
            "max_drawdown_pct": round(
                _safe_div(max_dd, peak) * 100.0, 6
            ),
            "avg_bars_to_entry": _mean(entry_bars),
            "avg_mae_atr": _mean(
                s.breakout_mae_atr for s in entered
            ),
            "avg_mfe_atr": _mean(
                s.breakout_mfe_atr for s in entered
            ),
        }

    # ----------------------------------------------------------

    @staticmethod
    def _policy_outcome(state, policy):
        """
        The result a state contributes to a policy's W/L accounting.
        The walk always records the CONSERVATIVE (stop-first) outcome;
        the other policies are deterministic transformations of it.
        """

        conservative = state.breakout_conservative

        if not state.breakout_ambiguous:

            return conservative

        if policy == INTRABAR_OPTIMISTIC:

            return "WIN" if conservative == "LOSS" else conservative

        if policy == INTRABAR_EXCLUDE:

            return "EXCLUDED"

        return conservative

    # ----------------------------------------------------------

    @staticmethod
    def _report_confirmation(states):
        """
        Phase 4H step 8: MARKET_CONFIRMATION rejection-stage counters.
        One count per rejection stage so a 0-fill result can be
        attributed instead of dismissed.
        """

        total = len(states)

        reasons = [
            s.confirmation_rejected_reason for s in states
        ]

        triggered = sum(
            1 for s in states if s.confirmation_triggered
        )

        return {
            "candidates": total,
            "triggered": triggered,
            "rejected_structure": reasons.count(
                CONFIRM_REJECT_STRUCTURE
            ),
            "rejected_trend": reasons.count(
                CONFIRM_REJECT_TREND
            ),
            "rejected_distance": reasons.count(
                CONFIRM_REJECT_DISTANCE
            ),
            "rejected_volume": 0,
            "rejected_orderflow": 0,
        }


# ==========================================================
# Report formatting
# ==========================================================


def format_causal_report(
    report,
    title="PHASE 4H CAUSAL BREAKOUT VALIDATION",
    setups_discovered=None,
):
    """
    Render the causal validation report for a printed BacktestReport
    block (ALL / BULLISH / BEARISH).
    """

    lines = [title]

    total = report["eligible_setups"]

    discovered = (
        setups_discovered
        if setups_discovered is not None
        else "?"
    )

    lines.append(
        f"Setups Discovered / Eligible : {discovered} / {total}"
    )

    lines.append(
        f"Window Bars / Execution     : {report['window_bars']} / "
        f"{report['execution']}"
    )

    lines.append("-" * 66)

    lines.append(
        "Breakout Continuation (shadow, causal rules 1-4):"
    )

    header = (
        f"  {'Policy':<11} {'Trigs':>5} {'Fills':>5} "
        f"{'Ambig':>5} {'W':>4} {'L':>4} {'Unr':>4} {'Exc':>4} "
        f"{'Win%':>6} {'PF':>6} {'ExpR':>5} {'MaxDD%':>6} "
        f"{'MAE':>6} {'MFE':>6}"
    )

    lines.append(header)

    for policy in INTRABAR_POLICIES:

        m = report["breakout"][policy]

        lines.append(
            f"  {policy:<11} {m['triggers']:>5} {m['fills']:>5} "
            f"{m['ambiguous_trades']:>5} {m['wins']:>4} "
            f"{m['losses']:>4} {m['unresolved']:>4} "
            f"{m['excluded']:>4} {m['win_rate'] * 100.0:>6.1f} "
            f"{m['profit_factor']:>6.2f} {m['expectancy_r']:>5.2f} "
            f"{m['max_drawdown_pct']:>6.1f} {m['avg_mae_atr']:>6.2f} "
            f"{m['avg_mfe_atr']:>6.2f}"
        )

    lines.append("-" * 66)

    lines.append(
        f"PRIMARY INTRABAR POLICY          : "
        f"{report['intrabar_policy']}"
    )

    lines.append(
        f"Triggers without executable next bar  : "
        f"{report['breakout'][INTRABAR_CONSERVATIVE]['triggers_without_executable_next_bar']}"
    )

    lines.append(
        f"Avg bars creation -> entry            : "
        f"{report['breakout'][INTRABAR_CONSERVATIVE]['avg_bars_to_entry']}"
    )

    lines.append(
        f"Expectancy / Average R (primary)      : "
        f"{report['breakout'][INTRABAR_CONSERVATIVE]['expectancy_r']}"
    )

    lines.append(
        f"Gross profit / loss (R, primary)      : "
        f"{report['breakout'][INTRABAR_CONSERVATIVE]['gross_profit_r']} / "
        f"{report['breakout'][INTRABAR_CONSERVATIVE]['gross_loss_r']}"
    )

    lines.append(
        f"Max drawdown (R, primary)             : "
        f"{report['breakout'][INTRABAR_CONSERVATIVE]['max_drawdown_r']}"
    )

    lines.append("-" * 66)

    conf = report["confirmation"]

    lines.append("MARKET_CONFIRMATION diagnostics (step 8):")

    lines.append(
        f"  candidates                     : {conf['candidates']}"
    )

    lines.append(
        f"  rejected_structure             : {conf['rejected_structure']}"
    )

    lines.append(
        f"  rejected_trend                 : {conf['rejected_trend']}"
    )

    lines.append(
        f"  rejected_distance              : {conf['rejected_distance']}"
    )

    lines.append(
        f"  rejected_volume                : {conf['rejected_volume']}"
    )

    lines.append(
        f"  rejected_orderflow             : {conf['rejected_orderflow']}"
    )

    lines.append(
        f"  triggered                      : {conf['triggered']}"
    )

    return "\n".join(lines)