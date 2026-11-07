"""
====================================================

QuantEngine

Canonical Entry Model Architecture

Phase 5A -- the single canonical home for ENTRY LOGIC.

Before this module, entry logic lived in three places that
never agreed cleanly: the backtester's pending-order fill gate
(core/execution/entry_mode.py, a switch on the mode string),
the EntryShadow comparison (core/setup/entry_shadow.py) and the
Phase 4H CausalValidator walk (core/setup/causal_validation.py).
This module is the ONE implementation of every entry model:

    EntryModel (base) + EntryDecision
        LimitRetestEntryModel
        MarketConfirmationEntryModel
        BreakoutContinuationEntryModel

Each model answers the SAME question -- "given this frozen setup
snapshot and this one candle, did MY entry trigger this bar, and
where do I enter?" -- and returns the SAME compatible decision
contract, an EntryDecision. The entry-mode vocabulary
(LIMIT_RETEST / MARKET_CONFIRMATION / BREAKOUT_CONTINUATION /
FVG_RETRACE / DISPLACEMENT_RETEST) lives HERE as the canonical
definition; core/execution/entry_mode.py and the setup layer
re-export it so the whole tree shares one vocabulary.

Contract fields (the EntryDecision):

    setup_id / structural_id / economic_fingerprint
    direction / entry_mode / triggered
    trigger_bar / trigger_timestamp
    entry_bar / entry_timestamp
    entry_price / stop_loss / take_profit
    reason / metadata

Additionally the MARKET_CONFIRMATION model exposes the Phase 4H
rejection-stage partition (structure / trend / distance) via
rejected_reason so a model that merely did not fire can be
ATTRIBUTED, not dismissed.

BREAKOUT trigger semantics (locked 1:1 to Phase 4H RULES):

  RULE 1 -- FREEZE AT CREATION. The model reads ONLY the setup
      snapshot it is handed. It never reads future candles; the
      caller decides WHEN a candle is passed in.
  RULE 2 -- TRIGGER AT CLOSE. A bullish trigger fires on the
      trigger candle only when high > entry level E AND close > E
      (bearish: low < E AND close < E) -- the price left the zone
      beyond E and CLOSED there. The structural stop breach
      (bullish: low <= stop; bearish: high >= stop) is checked
      BEFORE the trigger: a management-level idea that broke its
      zone is INVALIDATED, never triggered.
  RULE 3 -- NEXT-BAR EXECUTION. A trigger identified at bar N is
      entered at the OPEN of bar N+1 (the entry_bar). Nothing is
      ever entered retrospectively inside the trigger candle.
  RULE 4 -- DETERMINISTIC INTRABAR RESOLUTION is a POSITION
      concern, not an entry concern; it stays in the trading
      actor (causal walk / backtester), not this module.

LIMIT_RETEST trigger semantics (Phase 4D STEP 4):

  A pending bullish limit order fills when the candle's range
  touches the resting entry level: low <= entry <= high. The
  eligibility window (no same-candle fill) remains the registry's
  concern; this model only answers "did this candle touch my
  entry".

MARKET_CONFIRMATION trigger semantics (Phase 4H step 8):

  Reached = the candle's range crossed the reference level E
  (low <= E <= high). Triggered = reached AND closed beyond E in
  the direction (bullish close >= E). A candidate that never
  fired is attributed at settle via rejected_reason:
      structure  -- the idea was structurally invalidated first;
      distance   -- price never even reached E in the window;
      trend      -- reached E but never closed beyond it;
      ""         -- triggered (no rejection).

The models are PURE deciders. They hold no session state, write
nothing, and never mint an order -- the caller (backtester /
causal walk / shadow) owns the state machine that calls them.

====================================================
"""

from dataclasses import dataclass, field
from typing import Any

from config import risk_settings


# ==========================================================
# Entry mode constants (CANONICAL -- v4F STEP 6 vocabulary)
# ==========================================================

ENTRY_MODE_LIMIT_RETEST = "LIMIT_RETEST"

ENTRY_MODE_MARKET_CONFIRMATION = "MARKET_CONFIRMATION"

ENTRY_MODE_BREAKOUT_CONTINUATION = "BREAKOUT_CONTINUATION"

ENTRY_MODE_FVG_RETRACE = "FVG_RETRACE"

ENTRY_MODE_DISPLACEMENT_RETEST = "DISPLACEMENT_RETEST"

ENTRY_MODES = (
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
    ENTRY_MODE_FVG_RETRACE,
    ENTRY_MODE_DISPLACEMENT_RETEST,
)


# ==========================================================
# Execution semantics (Phase 5B)
# ==========================================================

# The two order-execution channels the backtester supports through
# one registry-managed lifecycle.
EXECUTION_LIMIT = "LIMIT"          # resting limit: low <= entry <= high

EXECUTION_NEXT_BAR_OPEN = "NEXT_BAR_OPEN"   # market: OPEN of trigger + 1

EXECUTION_TYPES = (
    EXECUTION_LIMIT,
    EXECUTION_NEXT_BAR_OPEN,
)


def execution_type_for(entry_mode):
    """
    The order-execution channel a setup's entry mode enters with.
    Defaults to EXECUTION_LIMIT and only BREAKOUT_CONTINUATION
    declares the next-bar-open market channel. A safe default means
    a badly-configured mode can never silently change how an order
    is filled.
    """

    if (entry_mode or "") == ENTRY_MODE_BREAKOUT_CONTINUATION:

        return EXECUTION_NEXT_BAR_OPEN

    return EXECUTION_LIMIT


# ==========================================================
# The compatible decision contract
# ==========================================================


@dataclass(slots=True)
class EntryDecision:
    """
    One entry-model decision for ONE setup on ONE candle. Every
    model returns this. The fields a model does not use stay at
    their defaults, so every consumer (backtester, causal walk,
    shadow) can read the same contract and ignore what it does not
    need.
    """

    # ---------------- Identity ----------------

    setup_id: str = ""

    structural_id: str = ""

    economic_fingerprint: str = ""

    # ---------------- Direction / mode ----------------

    direction: str = ""

    entry_mode: str = ""

    # ---------------- Outcome ----------------

    # True when THIS candle triggered the model's entry.
    triggered: bool = False

    trigger_bar: int = None

    trigger_timestamp: Any = None

    # The bar the position may actually open (entry mode's
    # execution bar). For NEXT_BAR_OPEN this is trigger_bar + 1.
    entry_bar: int = None

    entry_timestamp: Any = None

    # The price the position opens at. For a limit touch this is
    # the resting entry; for NEXT_BAR_OPEN it is filled at the
    # entry bar's OPEN by the trading actor.
    entry_price: float = 0.0

    stop_loss: float = 0.0

    take_profit: float = 0.0

    # ---------------- Rejection attribution ----------------

    # For MARKET_CONFIRMATION: "" / structure / trend / distance
    # (Phase 4H step 8 partition). Reported at settle, not on the
    # deciding candle.
    rejected_reason: str = ""

    # ---------------- Free text / audit ----------------

    reason: str = ""

    metadata: dict = field(default_factory=dict)


# ==========================================================
# The model base
# ==========================================================


class EntryModel:
    """
    One entry model: a PURE function from (setup snapshot, candle)
    to an EntryDecision. Subclasses implement decide(); the base
    owns the common identity/level snapshots so every decision
    carries the setup contract (setup_id / structural_id /
    economic_fingerprint / direction / mode / stop / target).
    """

    mode = ""

    def __init__(self):
        pass

    # --------------------------------------------------

    @staticmethod
    def _snapshot(setup, candle, bar):
        """
        FROZEN at-creation reading of the setup (Rule 1). The
        caller passes the setup it wants decided; this only picks
        the fields the trigger contract needs, so a future candle
        or a mutated setup can never leak into a decision.
        """

        direction = (
            getattr(setup, "direction", "") or ""
        ).upper()

        return {
            "setup_id": getattr(setup, "setup_id", "") or "",
            "structural_id": (
                getattr(setup, "structural_id", "")
                or getattr(setup, "setup_id", "")
                or ""
            ),
            "economic_fingerprint": getattr(
                setup, "economic_fingerprint", ""
            ) or "",
            "direction": direction,
            "entry": float(getattr(setup, "entry", 0.0) or 0.0),
            "stop_loss": float(
                getattr(setup, "stop_loss", 0.0) or 0.0
            ),
            "take_profit": float(
                getattr(setup, "take_profit", 0.0) or 0.0
            ),
        }

    # --------------------------------------------------

    def _base_decision(self, snapshot, candle, bar, timestamp=None):

        return EntryDecision(
            setup_id=snapshot["setup_id"],
            structural_id=snapshot["structural_id"],
            economic_fingerprint=snapshot["economic_fingerprint"],
            direction=snapshot["direction"],
            entry_mode=self.mode,
            stop_loss=snapshot["stop_loss"],
            take_profit=snapshot["take_profit"],
        )

    # --------------------------------------------------

    def decide(self, setup, candle, bar, timestamp=None):
        """
        Decide this candle for one setup. Subclasses override.
        """
        raise NotImplementedError

    # --------------------------------------------------

    @staticmethod
    def _is_bullish(decision_or_snapshot):
        return (
            decision_or_snapshot.get("direction", "")
            if isinstance(decision_or_snapshot, dict)
            else decision_or_snapshot.direction
        ).upper() == "BULLISH"


# ==========================================================
# Limit retest (Phase 4D STEP 4 -- the executable baseline)
# ==========================================================


class LimitRetestEntryModel(EntryModel):
    """
    The resting-limit model: a bullish order fills when the
    candle's range touches the resting entry (low <= entry <=
    high). That IS the decision; the eligibility window (never the
    same candle that formed the signal) stays the registry's
    concern.
    """

    mode = ENTRY_MODE_LIMIT_RETEST

    def decide(self, setup, candle, bar, timestamp=None):

        snapshot = self._snapshot(setup, candle, bar)

        decision = self._base_decision(
            snapshot, candle, bar, timestamp
        )

        entry = snapshot["entry"]

        low = getattr(candle, "low", None)

        high = getattr(candle, "high", None)

        # No OHLC (pure tick harness): legacy behavior treats an
        # unspecified range as a touch.
        touched = (
            True
            if low is None or high is None
            else (low <= entry <= high)
        )

        decision.triggered = bool(touched)

        if touched:

            decision.entry_price = entry

            decision.entry_bar = bar

            decision.entry_timestamp = timestamp

            decision.reason = (
                "limit retest: candle range touched resting entry"
            )

        return decision


# ==========================================================
# Market confirmation (Phase 4H step 8 -- rejection-attributed)
# ==========================================================


class MarketConfirmationEntryModel(EntryModel):
    """
    The confirmed-market model. Two-stage per candle plus a
    settle-time rejection attribution:

        reached   -- the candle's range crossed the reference
                     level E (low <= E <= high);
        triggered -- reached AND closed beyond E in the
                     direction (bullish close >= E).

    triggered is True only on the triggering candle. For a
    candidate window that closes without a trigger, settle() maps
    the observed state to the Phase 4H rejection partition
    (structure > trend > distance). The model itself is a pure
    decider: it reports what IT would do on each candle.
    """

    mode = ENTRY_MODE_MARKET_CONFIRMATION

    def decide(self, setup, candle, bar, timestamp=None):

        snapshot = self._snapshot(setup, candle, bar)

        decision = self._base_decision(
            snapshot, candle, bar, timestamp
        )

        entry = snapshot["entry"]

        low = getattr(candle, "low", None)

        high = getattr(candle, "high", None)

        close = getattr(candle, "close", None)

        bull = self._is_bullish(snapshot)

        reached = (
            low is not None
            and high is not None
            and low <= entry <= high
        )

        decision.metadata["reached"] = bool(reached)

        if not reached:

            decision.reason = (
                "market confirmation: never reached reference level"
            )

            return decision

        closed_beyond = (
            close is not None
            and (close >= entry if bull else close <= entry)
        )

        if closed_beyond:

            decision.triggered = True

            decision.trigger_bar = bar

            decision.trigger_timestamp = timestamp

            decision.entry_bar = bar

            decision.entry_timestamp = timestamp

            decision.entry_price = close

            decision.reason = (
                "market confirmation: crossed E and closed beyond it"
            )

        else:

            decision.reason = (
                "market confirmation: reached E, close not beyond it"
            )

        return decision

    # --------------------------------------------------

    @staticmethod
    def settle(decision, invalidated=False, reached=False):
        """
        Phase 4H step 8 rejection attribution at window settle:
        structure > trend > distance, matching the causal walk's
        priority. Mutates and returns the decision.
        """

        if decision.triggered:

            decision.rejected_reason = ""

            decision.metadata["rejected_structure"] = 0

            decision.metadata["rejected_trend"] = 0

            decision.metadata["rejected_distance"] = 0

            return decision

        if invalidated:

            decision.rejected_reason = "structure"

        elif not reached:

            decision.rejected_reason = "distance"

        else:

            decision.rejected_reason = "trend"

        counts = {
            "structure": 0,
            "trend": 0,
            "distance": 0,
        }

        counts[decision.rejected_reason] = 1

        decision.metadata.update(counts)

        return decision


# ==========================================================
# Breakout continuation (Phase 4H RULES 1-4 -- the executable
# continuation hypothesis)
# ==========================================================


class BreakoutContinuationEntryModel(EntryModel):
    """
    The breakout-continuation model, decided EXACTLY as the Phase
    4H causal walk decides it:

        RULE 2 trigger-at-close -- bullish fires when the trigger
        candle's high > E AND its close > E (bearish: low < E AND
        close < E). The structural stop breach (bullish low <=
        stop) is checked BEFORE the trigger: broke-zone ideas are
        invalidated, never triggered.

        RULE 3 next-bar execution -- trigger at bar N => entry_bar
        = N + 1, entry_price reported by the trading actor at the
        OPEN of N+1.

    The model is pure: it reports triggered on the trigger candle
    and lets the caller (backtester for executed fills, causal walk
    for measurement) own the position state machine.
    """

    mode = ENTRY_MODE_BREAKOUT_CONTINUATION

    def decide(self, setup, candle, bar, timestamp=None):

        snapshot = self._snapshot(setup, candle, bar)

        decision = self._base_decision(
            snapshot, candle, bar, timestamp
        )

        entry = float(snapshot["entry"] or 0.0)

        stop = float(snapshot["stop_loss"] or 0.0)

        low = getattr(candle, "low", None)

        high = getattr(candle, "high", None)

        close = getattr(candle, "close", None)

        bull = self._is_bullish(snapshot)

        # ---- structural stop breach BEFORE the trigger ----

        breached = (
            low is not None and stop and low <= stop
            if bull
            else high is not None and stop and high >= stop
        )

        if breached:

            decision.reason = (
                "breakout: structural stop breached before trigger"
            )

            decision.metadata["invalidated"] = True

            return decision

        # ---- RULE 2 trigger-at-close ----

        triggered = (
            bull
            and high is not None
            and close is not None
            and entry
            and high > entry
            and close > entry
        ) or (
            not bull
            and low is not None
            and close is not None
            and entry
            and low < entry
            and close < entry
        )

        if not triggered:

            decision.reason = (
                "breakout: no trigger this candle"
            )

            return decision

        decision.triggered = True

        decision.trigger_bar = bar

        decision.trigger_timestamp = timestamp

        # ---- RULE 3 next-bar execution ----

        decision.entry_bar = (bar + 1) if bar is not None else None

        decision.entry_timestamp = None  # stamped by the actor at open

        decision.reason = (
            "breakout continuation: trigger at close, enter at "
            "next bar open"
        )

        return decision

    # --------------------------------------------------

    @classmethod
    def _causal_executable(cls, decision, window_bars, trigger_age):
        """
        Rule 3 completeness check used by the measurement walk: a
        trigger on the LAST in-window bar has no executable next
        bar. Returns the (causally_executable, reason) pair.
        """

        executable = (
            decision.entry_bar is not None
            and (trigger_age + 1) <= window_bars
        )

        return executable, (
            "executable next bar"
            if executable
            else "no executable next bar (last in-window bar)"
        )


# ==========================================================
# Factory / selection
# ==========================================================


ENTRY_MODEL_CLASSES = {
    ENTRY_MODE_LIMIT_RETEST: LimitRetestEntryModel,
    ENTRY_MODE_MARKET_CONFIRMATION: MarketConfirmationEntryModel,
    ENTRY_MODE_BREAKOUT_CONTINUATION: BreakoutContinuationEntryModel,
}


def get_entry_model(mode):
    """
    The canonical EntryModel instance for an entry mode. Modes
    without a canonical implementation (FVG_RETRACE /
    DISPLACEMENT_RETEST -- measured, not implemented) resolve to
    None so a caller can prove it has no decider rather than
    silently choose the wrong model.
    """

    cls = ENTRY_MODEL_CLASSES.get(mode or "")

    return cls() if cls is not None else None


def default_entry_model():
    """
    The canonical model for the configured default mode (a strategy
    that does not carry an explicit mode per-setup still gets a
    decidable model).
    """

    mode = getattr(
        risk_settings, "ENTRY_MODE", ENTRY_MODE_LIMIT_RETEST
    ) or ENTRY_MODE_LIMIT_RETEST

    model = get_entry_model(mode)

    return model if model is not None else LimitRetestEntryModel()