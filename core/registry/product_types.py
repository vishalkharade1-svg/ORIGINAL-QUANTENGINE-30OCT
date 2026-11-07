"""
====================================================

QuantEngine

Product Types & Lifecycle States

Phase 6 -- Universal Instrument Discovery.

The canonical vocabulary for the instrument universe.
Everything that subscribes to / trades a product works
with these values, so a newly listed Delta instrument
enters the system without any upstream code change.

====================================================
"""

# -------------------------------------------------
# Product types (canonical, exchange-agnostic)
# -------------------------------------------------

PRODUCT_SPOT = "SPOT"

PRODUCT_PERPETUAL = "PERPETUAL"

PRODUCT_FUTURE = "FUTURE"

PRODUCT_CALL_OPTION = "CALL_OPTION"

PRODUCT_PUT_OPTION = "PUT_OPTION"

PRODUCT_UNKNOWN = "UNKNOWN"

PRODUCT_TYPES = (
    PRODUCT_SPOT,
    PRODUCT_PERPETUAL,
    PRODUCT_FUTURE,
    PRODUCT_CALL_OPTION,
    PRODUCT_PUT_OPTION,
)

# Types the current perpetual/spot strategy layer understands.
# Options are a SEPARATE capability layer (Phase 10) -- they are
# discovered and normalized, but never sent to the existing
# strategy/execution path.
SUPPORTED_STRATEGY_PRODUCT_TYPES = (
    PRODUCT_SPOT,
    PRODUCT_PERPETUAL,
    PRODUCT_FUTURE,
)

STANDALONE_OPTION_TYPES = (
    PRODUCT_CALL_OPTION,
    PRODUCT_PUT_OPTION,
)

# -------------------------------------------------
# Delta contract_type -> canonical product type
# -------------------------------------------------

_DELTA_CONTRACT_TO_PRODUCT = {
    "spot": PRODUCT_SPOT,
    "perpetual_futures": PRODUCT_PERPETUAL,
    "call_options": PRODUCT_CALL_OPTION,
    "put_options": PRODUCT_PUT_OPTION,
    "binary_call_options": PRODUCT_CALL_OPTION,
    "binary_put_options": PRODUCT_PUT_OPTION,
}


def product_type_from_delta(contract_type):
    """
    Canonical product type for a Delta `contract_type` /
    `product_type` value. Unknown values resolve to
    PRODUCT_UNKNOWN (never an exception -- discovery keeps
    every product visible, eligibility decides).
    """
    return _DELTA_CONTRACT_TO_PRODUCT.get(
        (contract_type or "").lower(),
        PRODUCT_UNKNOWN,
    )


# -------------------------------------------------
# Instrument lifecycle states (registry overlay)
# -------------------------------------------------

PRODUCT_STATE_NEWLY_LISTED = "NEWLY_LISTED"

PRODUCT_STATE_ACTIVE = "ACTIVE"

PRODUCT_STATE_ELIGIBLE = "ELIGIBLE"

PRODUCT_STATE_INELIGIBLE = "INELIGIBLE"

PRODUCT_STATE_DELISTED = "DELISTED"

PRODUCT_STATES = (
    PRODUCT_STATE_NEWLY_LISTED,
    PRODUCT_STATE_ACTIVE,
    PRODUCT_STATE_ELIGIBLE,
    PRODUCT_STATE_INELIGIBLE,
    PRODUCT_STATE_DELISTED,
)

# Provisional states whose instruments may be COLLECTED (data) but
# must NEVER reach the execution path until they transition to
# ELIGIBLE.
NON_EXECUTABLE_STATES = (
    PRODUCT_STATE_NEWLY_LISTED,
    PRODUCT_STATE_ACTIVE,
    PRODUCT_STATE_INELIGIBLE,
    PRODUCT_STATE_DELISTED,
)

EXECUTABLE_STATES = (PRODUCT_STATE_ELIGIBLE,)