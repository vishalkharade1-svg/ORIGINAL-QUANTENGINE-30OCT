"""Venue-neutral instrument metadata validation (Phase 199).

This validates descriptive contract metadata only. It does not discover venue
contracts, price orders, or establish that any adapter can trade an instrument.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
import re


class OptionRight(str, Enum):
    CALL = "call"
    PUT = "put"


_FX_CODE = re.compile(r"^[A-Z]{3}/[A-Z]{3}$")


def _positive_decimal(name: str, value: Decimal | str | int | float) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return result


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Normalized contract facts; unsupported/unknown venue facts stay explicit.

    ``expiry`` is an ISO-8601 calendar date (YYYY-MM-DD), not a guessed
    exchange timestamp. ``lot_size`` is required for options and may be absent
    for instruments whose venue defines quantities differently.
    """

    symbol: str
    family: str
    instrument_type: str
    tick_size: Decimal | str | int | float
    quantity_step: Decimal | str | int | float
    contract_multiplier: Decimal | str | int | float = 1
    currency: str = ""
    underlying: str = ""
    option_right: OptionRight | str | None = None
    strike: Decimal | str | int | float | None = None
    expiry: str | None = None
    lot_size: int | None = None

    def __post_init__(self) -> None:
        for field in ("symbol", "family", "instrument_type"):
            if not getattr(self, field).strip():
                raise ValueError(f"{field} is required")
        object.__setattr__(self, "tick_size", _positive_decimal("tick_size", self.tick_size))
        object.__setattr__(self, "quantity_step", _positive_decimal("quantity_step", self.quantity_step))
        object.__setattr__(self, "contract_multiplier", _positive_decimal("contract_multiplier", self.contract_multiplier))

        is_option = self.instrument_type.lower() == "option"
        if is_option:
            if not self.underlying.strip():
                raise ValueError("option underlying is required")
            if self.option_right is None:
                raise ValueError("option_right must be call or put")
            try:
                right = self.option_right if isinstance(self.option_right, OptionRight) else OptionRight(str(self.option_right).lower())
            except ValueError as exc:
                raise ValueError("option_right must be call or put") from exc
            object.__setattr__(self, "option_right", right)
            if self.strike is None:
                raise ValueError("option strike is required")
            object.__setattr__(self, "strike", _positive_decimal("strike", self.strike))
            if not self.expiry:
                raise ValueError("option expiry is required as YYYY-MM-DD")
            try:
                parsed = date.fromisoformat(self.expiry)
            except (TypeError, ValueError) as exc:
                raise ValueError("option expiry must be a valid YYYY-MM-DD date") from exc
            if parsed.isoformat() != self.expiry:
                raise ValueError("option expiry must be canonical YYYY-MM-DD")
            if not isinstance(self.lot_size, int) or isinstance(self.lot_size, bool) or self.lot_size <= 0:
                raise ValueError("option lot_size must be a positive integer")
        elif any(value is not None for value in (self.option_right, self.strike, self.expiry)):
            raise ValueError("option fields may only be set for option instruments")

        if self.family.lower() == "forex":
            if not _FX_CODE.fullmatch(self.symbol):
                raise ValueError("forex symbol must use normalized BASE/QUOTE form, e.g. EUR/USD")
            if self.currency and len(self.currency) != 3:
                raise ValueError("forex currency, when supplied, must be a three-letter code")
