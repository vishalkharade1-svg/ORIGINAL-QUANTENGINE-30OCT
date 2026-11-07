"""
====================================================

QuantEngine

Entry Feasibility

Phase 4F -- entry distance measurement and feasibility
classification. Measurement BEFORE optimization: this module
never changes a strategy threshold, never waits longer and never
changes an entry; it objectively states HOW FAR an accepted setup's
limit entry sits from the market that just produced it, normalized
to the instrument's ATR so no symbol-specific point distance is
ever hard-coded.

    ENTRIES_AMONG_SETUPS_MEASURED:
        for each accepted setup:
            entry_distance        = |entry - creation_price|
            entry_distance_pct    = distance as percent of price
            entry_distance_atr    = distance as multiples of ATR_14
            entry_distance_ticks  = distance in tick units

    CLASSIFICATION (ATR-normalized, configurable):
        ENTRY_IMMEDIATE      distance <= 0.10 ATR
        ENTRY_NEAR           distance <= 0.35 ATR
        ENTRY_RETRACE        distance <= 0.75 ATR
        ENTRY_DEEP_RETRACE   distance <= 1.50 ATR
        ENTRY_TOO_FAR        distance >  1.50 ATR

The entry MODE constants (Phase 4F STEP 6) are the CANONICAL
vocabulary, owned by core/execution/entry_model.py (Phase 5A) and
re-exported here so every historical importer
(core/execution/entry_mode.py, core/setup/entry_shadow.py, the
tests) keeps working against ONE shared vocabulary:

    LIMIT_RETEST               limit order at the retest price
    MARKET_CONFIRMATION        confirmed market entry
    BREAKOUT_CONTINUATION      breakout continuation entry
    FVG_RETRACE                fair-value-gap retrace entry
    DISPLACEMENT_RETEST        displacement retest entry

LIMIT_RETEST is the ONLY deployed mode in Phase 4F -- all others
are declared for measurement, never enabled.

====================================================
"""

from dataclasses import dataclass

from config import risk_settings

from core.execution.entry_model import (
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
    ENTRY_MODE_FVG_RETRACE,
    ENTRY_MODE_DISPLACEMENT_RETEST,
    ENTRY_MODES,
)


# ==========================================================
# Entry mode constants (Phase 4F STEP 6 -- canonical vocabulary,
# re-exported from core/execution/entry_model.py, Phase 5A)
# ==========================================================
# ==========================================================

ENTRY_IMMEDIATE = "ENTRY_IMMEDIATE"

ENTRY_NEAR = "ENTRY_NEAR"

ENTRY_RETRACE = "ENTRY_RETRACE"

ENTRY_DEEP_RETRACE = "ENTRY_DEEP_RETRACE"

ENTRY_TOO_FAR = "ENTRY_TOO_FAR"

ENTRY_FEASIBILITY_STATES = (
    ENTRY_IMMEDIATE,
    ENTRY_NEAR,
    ENTRY_RETRACE,
    ENTRY_DEEP_RETRACE,
    ENTRY_TOO_FAR,
)


# ==========================================================
# Thresholds
# ==========================================================


def default_feasibility_thresholds():
    """
    ATR-normalized classification thresholds from config. Each
    threshold is the MAXIMUM ATR-normalized entry distance that
    still belongs to that class. Nothing is hard-coded to a
    single symbol's point grid.
    """

    return {
        ENTRY_IMMEDIATE: getattr(
            risk_settings, "ENTRY_FEASIBILITY_IMMEDIATE_ATR", 0.10
        ),
        ENTRY_NEAR: getattr(
            risk_settings, "ENTRY_FEASIBILITY_NEAR_ATR", 0.35
        ),
        ENTRY_RETRACE: getattr(
            risk_settings, "ENTRY_FEASIBILITY_RETRACE_ATR", 0.75
        ),
        ENTRY_DEEP_RETRACE: getattr(
            risk_settings, "ENTRY_FEASIBILITY_DEEP_ATR", 1.50
        ),
    }


def classify_entry_feasibility(entry_distance_atr, thresholds=None):
    """
    Classify one setup's ATR-normalized entry distance:

        <= immediate -> ENTRY_IMMEDIATE
        <= near      -> ENTRY_NEAR
        <= retrace   -> ENTRY_RETRACE
        <= deep      -> ENTRY_DEEP_RETRACE
        else         -> ENTRY_TOO_FAR

    `thresholds` is a dict {state: max_distance_atr}; defaults to
    the configured values above.
    """

    t = thresholds or default_feasibility_thresholds()

    d = float(entry_distance_atr or 0.0)

    if d <= t[ENTRY_IMMEDIATE]:
        return ENTRY_IMMEDIATE

    if d <= t[ENTRY_NEAR]:
        return ENTRY_NEAR

    if d <= t[ENTRY_RETRACE]:
        return ENTRY_RETRACE

    if d <= t[ENTRY_DEEP_RETRACE]:
        return ENTRY_DEEP_RETRACE

    return ENTRY_TOO_FAR


# ==========================================================
# Feasibility snapshot
# ==========================================================


@dataclass(slots=True)
class EntryFeasibility:
    """
    Point-in-time feasibility measurement of one accepted setup,
    captured by the TradeSetupBuilder at build time from the
    market state that produced the setup.

    All four distance axes derive from ONE quantity
    (|entry - creation_price|) and are expressed in different
    normalizations so any consumer can compare apples-to-apples
    across symbols/timeframes.
    """

    structural_id: str = ""

    economic_fingerprint: str = ""

    direction: str = ""

    entry_mode: str = ""

    entry: float = 0.0

    stop_loss: float = 0.0

    take_profit: float = 0.0

    creation_bar: int = 0

    # Market price at signal/build time (the creating candle's
    # close). The entry sits |entry - creation_price| away.
    creation_price: float = 0.0

    # ATR_14 available at build time (0.0 when no indicator
    # stack exists, e.g. a scripted test harness).
    atr: float = 0.0

    # |entry - creation_price|
    entry_distance: float = 0.0

    # entry_distance / creation_price * 100 (percent of price)
    entry_distance_pct: float = 0.0

    # entry_distance / ATR (multiples of ATR -- the axis the
    # feasibility classification keys on)
    entry_distance_atr: float = 0.0

    # entry_distance / tick (tick units)
    entry_distance_ticks: float = 0.0

    # ENTRY_IMMEDIATE / ENTRY_NEAR / ENTRY_RETRACE /
    # ENTRY_DEEP_RETRACE / ENTRY_TOO_FAR
    classification: str = ""


def create_entry_feasibility(
    setup,
    creation_price=None,
    atr=None,
    tick=None,
    creation_bar=0,
):
    """
    Measure the entry feasibility of a setup-like object from the
    market price that produced it.

    `creation_price` defaults to the setup's observed_price (the
    builder's snapshot of the creating candle's close). The ATR
    defaults to the setup's carried ATR (0.0 when absent). `tick`
    defaults to config ECONOMIC_TICK_SIZE.
    """

    entry = float(getattr(setup, "entry", 0.0) or 0.0)

    creation_price = (
        creation_price
        if creation_price is not None
        else float(getattr(setup, "observed_price", 0.0) or 0.0)
    )

    atr = (
        atr
        if atr is not None
        else float(getattr(setup, "atr", 0.0) or 0.0)
    )

    if tick is None:

        tick = getattr(
            risk_settings, "ECONOMIC_TICK_SIZE", 0.0
        ) or 0.0

    entry_distance = abs(entry - creation_price)

    entry_distance_atr = (
        entry_distance / atr
        if atr and atr > 0
        else 0.0
    )

    entry_distance_pct = (
        entry_distance / creation_price * 100.0
        if creation_price and creation_price > 0
        else 0.0
    )

    entry_distance_ticks = (
        entry_distance / tick
        if tick and tick > 0
        else 0.0
    )

    return EntryFeasibility(
        structural_id=(
            getattr(setup, "structural_id", "")
            or getattr(setup, "setup_id", "")
            or ""
        ),
        economic_fingerprint=getattr(
            setup, "economic_fingerprint", ""
        ) or "",
        direction=getattr(setup, "direction", "") or "",
        entry_mode=getattr(setup, "entry_mode", "")
        or ENTRY_MODE_LIMIT_RETEST,
        entry=entry,
        stop_loss=float(getattr(setup, "stop_loss", 0.0) or 0.0),
        take_profit=float(getattr(setup, "take_profit", 0.0) or 0.0),
        creation_bar=int(getattr(setup, "observed_bar", 0) or creation_bar or 0),
        creation_price=creation_price,
        atr=atr,
        entry_distance=entry_distance,
        entry_distance_pct=round(entry_distance_pct, 6),
        entry_distance_atr=round(entry_distance_atr, 6),
        entry_distance_ticks=round(entry_distance_ticks, 6),
        classification=classify_entry_feasibility(
            entry_distance_atr
        ),
    )