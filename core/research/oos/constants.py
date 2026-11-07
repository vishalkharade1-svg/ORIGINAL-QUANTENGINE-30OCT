"""
====================================================================

QuantEngine

Multi-Period Out-of-Sample Validation (Phase 9M) -- constants

Locked, closed vocabularies and the frozen validation protocol.

The OOS protocol is a VALIDATION PROTOCOL, not a hyperparameter: the
defaults below are the locked 9M contract and are never auto-optimized
(no 40/60 vs 50/50 vs 60/40 search). They can be overridden only by
explicit caller configuration.

   * 6 chronological, non-overlapping OOS periods over the trailing
     half of the time-ordered opportunity population;
   * discovery = the leading 50% (never re-used as validation);
   * a period is SETTLED only when it provides enough evidence
     (>= min opportunities AND >= min trades); otherwise it is
     INCONCLUSIVE, never silently discarded;
   * robust validation requires 5/6 periods economically positive with
     <= 1 rejected period and 5/6 sign-consistent periods.

Causality vocabulary is closed: a finding may hold one of the
8-status ladder values and each settled period one of the 5 statuses.
====================================================================
"""

# ------------------------------------------------------------------
# Closed status vocabularies
# ------------------------------------------------------------------

# Per-period statuses (Section 6 of the 9M spec).
PERIOD_STATUSES = (
    "VALIDATED",    # economically acceptable, no unresolved trade-off
    "PROMISING",    # acceptable but with a reportable MAE trade-off
    "INCONCLUSIVE", # evidence present but below the settling sample gate
    "REJECTED",     # genuine loss expansion / worsening economics
    "UNAVAILABLE",  # no eligible evidence in this period for the claim
)

# Finding-level status ladder (Section 17 of the 9M spec). Every
# transition carries an explicit reason; no status may skip mandatory
# OOS evidence.
OOS_STATUSES = (
    "BLOCKED",                # 7E NO-GO surface -- can never be validated
    "UNAVAILABLE",            # no eligible OOS evidence at all
    "INCONCLUSIVE",           # nothing settled; cannot conclude
    "REJECTED",               # repeated adverse OOS evidence
    "OOS_PARTIAL",            # positive but too few settled periods
    "OOS_PROMISING",          # strong but not meeting full robustness
    "OOS_ROBUST",             # 5/6 survival + sign consistency + gates
    "VALIDATED_RESEARCH_ONLY",# full survival + provenance + consistency
)

# Origin of the discovery being re-validated (9M consumes, never
# re-discovers).
ORIGINS = ("9J", "9K", "9L")

# The 7E directional safety boundary: a seven_e_no_go hypothesis can
# never be resurrected by repeated OOS evidence.
SEVEN_E_NO_GO = "7E-NO-GO"

# The fixed candidate entry-model vocabulary (mirrors the 9C supported
# grid -- 9M never tests an unbounded model search).
CANDIDATE_ALTERNATIVES = (
    "LIMIT_RETEST",
    "MARKET_CONFIRMATION",
    "BREAKOUT_CONTINUATION",
)

DIRECTIONS = ("LONG", "SHORT")

ROBUSTNESS_LEVELS = ("LOW", "MEDIUM", "HIGH")

# ------------------------------------------------------------------
# Locked validation protocol defaults
# ------------------------------------------------------------------

OOS_PERIODS = 6
DISCOVERY_FRACTION = 0.5
MIN_OOS_OPPORTUNITIES_PER_PERIOD = 30
MIN_OOS_TRADES_PER_PERIOD = 10
MIN_TOTAL_OOS_TRADES = 60
MIN_SURVIVING_PERIODS = 5
REQUIRED_SIGN_CONSISTENT_PERIODS = 5
PURGE_BARS = 0
EMBARGO_BARS = 0
ECONOMIC_DELTA_R = 0.5
LOSS_RATE_EXPANSION = 0.05
ALPHA = 0.05

# The split is protocol, not a hyperparameter.
SPLIT_PROTOCOL_FROZEN = True
SPLIT_PROTOCOL_NOTE = (
    "9M never optimizes the split: 6 chronological OOS periods over "
    "the trailing 50%, 30 opportunities / 10 trades per settled "
    "period, 60 minimum total trades, 5/6 survival and 5/6 "
    "sign-consistent periods, no shuffle / randomization, and purge / "
    "embargo of 0 unless derived from the existing outcome horizon."
)