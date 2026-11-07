"""
====================================================

QuantEngine

Entry Mode Gate

Phase 4F STEP 6/7 -- explicit multi-mode entry architecture.

The entry model is a first-class value carried from the
SetupCandidate through the OrderIntent onto the Trade. This
module is the tiny gate that decides which modes are live and
which order gets which mode -- so entry logic is NEVER silently
mixed inside one execution function.

    select_entry_mode(setup)   -> the mode this setup enters with
    is_active(mode)            -> may this mode fill in the run?

LIMIT_RETEST is the default and the only ACTIVE mode in Phase 4F.
MARKET_CONFIRMATION / BREAKOUT_CONTINUATION / FVG_RETRACE /
DISPLACEMENT_RETEST are declared for measurement; an order whose
mode is not active stays parked (honest diagnostics, never a fill).

====================================================
"""

from config import risk_settings

from core.setup.entry_feasibility import (
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
    ENTRY_MODE_FVG_RETRACE,
    ENTRY_MODE_DISPLACEMENT_RETEST,
)

# Research-only mode. No implicit mode routing is ever performed:
# AUTO is a FIRST-CLASS routing decision that stays disabled until
# a statistically validated policy exists. Configured AUTO raises
# immediately instead of silently falling back to LIMIT_RETEST (a
# silent mode change would corrupt measurement). Declared here so
# the vocabulary is complete and the gate fails loudly by design.
ENTRY_MODE_AUTO = "AUTO"

# All declared modes. Imported here so this gate and the setup
# layer's feasibility snapshot share one vocabulary.
ENTRY_MODES = (
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
    ENTRY_MODE_FVG_RETRACE,
    ENTRY_MODE_DISPLACEMENT_RETEST,
)


class EntryModeRouterError(RuntimeError):
    """
    Raised when the entry-mode router is asked to make an
    unvalidated routing decision (AUTO), so a silent fallback can
    never change what an order actually executes with.
    """


def _is_declared(mode):
    return mode in ENTRY_MODES


def resolve_routed_mode(mode):
    """
    The routing contract for an explicitly chosen entry mode.
    AUTO -- and every undeclared mode -- is rejected LOUDLY: this
    router never silently substitutes a different mode for the one
    the caller asked for.
    """

    if mode == ENTRY_MODE_AUTO:

        raise EntryModeRouterError(
            "EntryModeRouter: 'AUTO' is a research-gated routing "
            "state, not an executable mode. Configure a declared "
            "mode (LIMIT_RETEST / MARKET_CONFIRMATION / "
            "BREAKOUT_CONTINUATION / FVG_RETRACE / "
            "DISPLACEMENT_RETEST) explicitly until a validated "
            "routing policy exists."
        )

    if not _is_declared(mode):

        raise EntryModeRouterError(
            f"EntryModeRouter: '{mode}' is not a declared entry "
            f"mode. No silent fallback is allowed."
        )

    return mode


def active_entry_modes():
    """
    The modes that may actually fill in the current run, from
    config.ACTIVE_ENTRY_MODES. Defensive normalization: empty /
    invalid config degrades to LIMIT_RETEST only -- a measurement
    run must never enable an undeployed mode by accident.
    """

    modes = getattr(
        risk_settings, "ACTIVE_ENTRY_MODES", None
    )

    if not modes:

        return (ENTRY_MODE_LIMIT_RETEST,)

    active = tuple(
        m for m in modes
        if m in ENTRY_MODES and m != ENTRY_MODE_AUTO
    )

    return active or (ENTRY_MODE_LIMIT_RETEST,)


def configured_entry_mode():
    """
    The default mode configured for new setups. Raises for AUTO /
    undeclared config -- the router never silently substitutes a
    mode for the one configured.
    """

    mode = getattr(
        risk_settings, "ENTRY_MODE", ENTRY_MODE_LIMIT_RETEST
    ) or ENTRY_MODE_LIMIT_RETEST

    return resolve_routed_mode(mode)


def select_entry_mode(setup):
    """
    PHASE 5C -- the canonical Entry Model Router for a setup.

    Routing precedence, in order:

        1. An explicit entry_mode already carried on the setup
           (stamped by a mode-derivation rule or by an external
           harness) is honored once it is a DECLARED mode.
        2. Otherwise the configured ENTRY_MODE is routed.

    AUTO and undeclared modes RAISE (EntryModeRouterError), so a
    research-only mode can never silently become LIMIT_RETEST in
    production, and production can never silently execute a mode
    different from the one that was researched.
    """

    if setup is None:

        return configured_entry_mode()

    carried = getattr(setup, "entry_mode", "") or ""

    if carried:

        return resolve_routed_mode(carried)

    return configured_entry_mode()


def is_active(mode):
    """
    May an order carrying this mode actually fill in the run?
    Only ACTIVE modes fill; undeployed modes stay parked.
    """

    return mode in active_entry_modes()