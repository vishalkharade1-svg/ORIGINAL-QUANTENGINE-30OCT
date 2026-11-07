"""
====================================================

QuantEngine

Instrument Eligibility (Phase 6A core / 6B filters)

The boundary between DISCOVER-EVERYTHING and
TRADE-SOMETHING. An instrument is ELIGIBLE only when it
passes the mandatory gates:

  GATE 1  valid identity   -- instrument_id + symbol
  GATE 2  trading enabled  -- exchange reports it tradable
  GATE 3  canonical       -- a supported strategy product
                            type (options are a separate layer)
  GATE 4  precision        -- printable tick + quantity step

LIQUIDITY / HISTORY / PORTFOLIO gates arrive with Phase
6B/6C/8. When no price value is provided the liquidity
gate is UNKNOWN -- and unknown is a DENY, so discovery can
never silently open the exotic-token path.

========================================================================
"""

from core.registry.instrument import Instrument
from core.registry.product_types import (
    PRODUCT_UNKNOWN,
    SUPPORTED_STRATEGY_PRODUCT_TYPES,
)


class IneligibleReason:
    NOT_ENABLED = "NOT_ENABLED"
    UNKNOWN_TYPE = "UNKNOWN_TYPE"
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    NO_PRECISION = "NO_PRECISION"
    NO_LIQUIDITY_DATA = "NO_LIQUIDITY_DATA"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    NO_HISTORY_DATA = "NO_HISTORY_DATA"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    NOT_CONFIRMED = "NOT_CONFIRMED"


class InstrumentEligibility:

    def __init__(self, min_quote_volume_24h=None, min_history_bars=None):
        # None min_quote_volume_24h -> any liquidity figure passes
        # the bound, but a MISSING figure (None) is ALWAYS a deny:
        # never trade what we cannot measure.
        self.min_quote_volume_24h = min_quote_volume_24h
        # None min_history_bars -> the history/lookback gate is not
        # configured (off). A configured value ("window/lookback
        # requirement, e.g. 30 bars") requires real history data.
        self.min_history_bars = min_history_bars

    def evaluate(self, instrument, quote_volume_24h=None,
                 history_bars=None):
        """Return (eligible: bool, reason: str)."""
        instrument = (
            instrument
            if isinstance(instrument, Instrument)
            else Instrument.from_dict(instrument)
        )

        if not instrument.valid:
            return False, IneligibleReason.NOT_ENABLED

        if instrument.product_type == PRODUCT_UNKNOWN:
            return False, IneligibleReason.UNKNOWN_TYPE

        if instrument.product_type not in SUPPORTED_STRATEGY_PRODUCT_TYPES:
            return False, IneligibleReason.UNSUPPORTED_TYPE

        if not instrument.valid_precision:
            return False, IneligibleReason.NO_PRECISION

        # Liquidity data is mandatory. A live product with NO volume
        # figure is unmeasurable -> not tradable, whatever the bound.
        if quote_volume_24h is None:
            return False, IneligibleReason.NO_LIQUIDITY_DATA

        if (
            self.min_quote_volume_24h is not None
            and quote_volume_24h < self.min_quote_volume_24h
        ):
            return False, IneligibleReason.LOW_LIQUIDITY

        # History / lookback window gate (off unless configured).
        if self.min_history_bars is not None:
            if history_bars is None:
                return False, IneligibleReason.NO_HISTORY_DATA
            if history_bars < self.min_history_bars:
                return False, IneligibleReason.INSUFFICIENT_HISTORY

        return True, ""


def run_basic_gates(instrument):
    """Gates 1-4 only (identity, enabled, type, precision).
    IMPORTANT: passing gates 1-4 is NOT eligibility -- the
    liquidity gate remains a DENY until Phase 6B provides it."""
    eligibility = InstrumentEligibility()
    eligible, reason = eligibility.evaluate(
        instrument, quote_volume_24h=0.0
    )
    return eligible, reason