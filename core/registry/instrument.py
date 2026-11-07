"""
====================================================

QuantEngine

Canonical Instrument

Phase 6 -- Universal Instrument Discovery.

A normalized, exchange-agnostic instrument record. The
rest of QuantEngine receives THIS object (never raw
Delta JSON), so BTC, SOL, a newly listed token and -- in
Phase 10 -- an option are all handled the same way:

    discovery -> normalize -> Instrument -> registry ->
    eligibility -> universe -> strategy

Instrument carries the exchange contract rules (tick /
quantity steps, minimum order size, funding-related
precision) so a consumer never needs exchange-specific
code to size or price an order correctly.

====================================================
"""

from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from typing import Any
from typing import Dict
from typing import Optional

from core.registry.product_types import (
    PRODUCT_STATE_NEWLY_LISTED,
    PRODUCT_UNKNOWN,
)


@dataclass(slots=True)
class Instrument:

    # Identity (canonical key)
    instrument_id: str
    symbol: str
    exchange: str

    # Product classification
    product_type: str = PRODUCT_UNKNOWN

    # Underying / quote assets (symbols)
    underlying_asset: str = ""
    quote_asset: str = ""

    # Option-specific (""/None when not an option)
    expiry_time: Optional[int] = None
    strike_price: Optional[float] = None
    option_type: str = ""

    # Exchange contract rules (precision + sizing)
    tick_size: float = 0.0
    quantity_step: float = 0.0
    minimum_quantity: float = 0.0

    # Market access
    trading_enabled: bool = False

    # Lifecycle state (registry overlay)
    state: str = PRODUCT_STATE_NEWLY_LISTED

    # Raw exchange metadata preserved verbatim
    metadata: Dict[str, Any] = field(default_factory=dict)

    # =====================================================
    # Identity
    # =====================================================

    @classmethod
    def key_for(cls, exchange, symbol):
        return f"{exchange}:{symbol}"

    @property
    def key(self):
        return Instrument.key_for(self.exchange, self.symbol)

    # =====================================================
    # Precision / contract rules
    # =====================================================

    @property
    def valid_precision(self):
        """A contract with no printable price / quantity step is
        not tradable (would round to nothing)."""
        return self.tick_size > 0.0 and self.quantity_step > 0.0

    @property
    def valid(self):
        return (
            bool(self.instrument_id)
            and bool(self.symbol)
            and bool(self.exchange)
            and self.trading_enabled
        )

    def round_price(self, price):
        if self.tick_size <= 0.0:
            return float(price)
        return round(round(float(price) / self.tick_size) * self.tick_size, 12)

    def round_quantity(self, quantity):
        if self.quantity_step <= 0.0:
            return float(quantity)
        return round(float(quantity) / self.quantity_step) * self.quantity_step

    # =====================================================
    # Serialization (persistent registry)
    # =====================================================

    def to_dict(self):
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
        }

    @classmethod
    def from_dict(cls, data):
        known = {f.name for f in fields(cls)}
        meta = data.get("metadata") or {}
        return cls(
            **{
                k: v
                for k, v in data.items()
                if k in known and k != "metadata"
            },
            metadata=dict(meta),
        )