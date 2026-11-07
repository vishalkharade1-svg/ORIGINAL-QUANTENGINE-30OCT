"""Contract-aware, Decimal-based sizing and loss math.

This is an isolated Phase-2 calculation boundary.  It deliberately does not
guess a venue product's settlement convention: callers must choose a contract
kind and provide a complete cost model.  The legacy float ``PositionSizer``
is not changed by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from enum import Enum


class ContractKind(str, Enum):
    LINEAR = "LINEAR"
    INVERSE = "INVERSE"
    OPTION_PREMIUM = "OPTION_PREMIUM"


class ContractMathError(ValueError):
    pass


def _d(value: object, name: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as error:  # Decimal raises several implementation errors
        raise ContractMathError(f"{name} is not numeric") from error
    if not result.is_finite() or (positive and result <= 0) or (nonnegative and result < 0):
        raise ContractMathError(f"{name} is invalid")
    return result


@dataclass(frozen=True, slots=True)
class ContractSpec:
    kind: ContractKind
    multiplier: Decimal
    tick_size: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ContractKind(self.kind))
        for name in ("multiplier", "tick_size", "quantity_step"):
            object.__setattr__(self, name, _d(getattr(self, name), name, positive=True))
        object.__setattr__(self, "minimum_quantity", _d(self.minimum_quantity, "minimum_quantity", nonnegative=True))


@dataclass(frozen=True, slots=True)
class CostModel:
    """All values are quote-currency amounts or rates, never implicit zero."""

    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    half_spread: Decimal
    slippage_bps: Decimal
    funding_per_contract: Decimal

    def __post_init__(self) -> None:
        for name in ("entry_fee_bps", "exit_fee_bps", "half_spread", "slippage_bps", "funding_per_contract"):
            object.__setattr__(self, name, _d(getattr(self, name), name, nonnegative=True))


@dataclass(frozen=True, slots=True)
class RiskQuote:
    quantity: Decimal
    gross_stop_loss: Decimal
    estimated_costs: Decimal
    total_stop_loss: Decimal
    entry_notional: Decimal


@dataclass(frozen=True, slots=True)
class SizedContractPosition:
    quantity: Decimal
    risk_quote: RiskQuote | None
    valid: bool
    reason: str


def _price(value: object, name: str) -> Decimal:
    return _d(value, name, positive=True)


def _notional(spec: ContractSpec, quantity: Decimal, price: Decimal) -> Decimal:
    # Both linear and premium options quote notional as qty * multiplier * price.
    # For inverse contracts multiplier is the quote contract value per contract.
    return quantity * spec.multiplier * price


def gross_stop_loss(spec: ContractSpec, quantity: object, entry_price: object, stop_price: object) -> Decimal:
    """Quote-currency loss at the stop, excluding costs.

    INVERSE uses the standard fixed-quote contract result converted at the
    stop: qty * contract_value * abs(1/entry - 1/stop) * stop.
    This equals qty * contract_value * abs(entry-stop) / entry.
    """
    quantity = _d(quantity, "quantity", nonnegative=True)
    entry, stop = _price(entry_price, "entry_price"), _price(stop_price, "stop_price")
    if spec.kind in (ContractKind.LINEAR, ContractKind.OPTION_PREMIUM):
        return quantity * spec.multiplier * abs(entry - stop)
    return quantity * spec.multiplier * abs(entry - stop) / entry


def estimated_stop_costs(spec: ContractSpec, costs: CostModel, quantity: object, entry_price: object, stop_price: object) -> Decimal:
    """Conservative round-trip costs in quote currency for a stop exit."""
    quantity = _d(quantity, "quantity", nonnegative=True)
    entry, stop = _price(entry_price, "entry_price"), _price(stop_price, "stop_price")
    entry_notional, exit_notional = _notional(spec, quantity, entry), _notional(spec, quantity, stop)
    fees = entry_notional * costs.entry_fee_bps / Decimal("10000") + exit_notional * costs.exit_fee_bps / Decimal("10000")
    slippage = (entry_notional + exit_notional) * costs.slippage_bps / Decimal("10000")
    spread = quantity * spec.multiplier * costs.half_spread * Decimal("2")
    funding = quantity * costs.funding_per_contract
    return fees + slippage + spread + funding


def stop_risk(spec: ContractSpec, costs: CostModel, quantity: object, entry_price: object, stop_price: object) -> RiskQuote:
    quantity = _d(quantity, "quantity", nonnegative=True)
    entry = _price(entry_price, "entry_price")
    gross = gross_stop_loss(spec, quantity, entry, stop_price)
    estimated = estimated_stop_costs(spec, costs, quantity, entry, stop_price)
    return RiskQuote(quantity, gross, estimated, gross + estimated, _notional(spec, quantity, entry))


def _round_down(quantity: Decimal, step: Decimal) -> Decimal:
    return (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step


def size_to_risk_budget(spec: ContractSpec, costs: CostModel, risk_budget: object, entry_price: object, stop_price: object) -> SizedContractPosition:
    """Return the largest executable quantity whose inclusive stop loss fits budget."""
    budget = _d(risk_budget, "risk_budget", positive=True)
    entry, stop = _price(entry_price, "entry_price"), _price(stop_price, "stop_price")
    if entry == stop:
        return SizedContractPosition(Decimal("0"), None, False, "stop distance must be non-zero")
    one = stop_risk(spec, costs, Decimal("1"), entry, stop)
    if one.total_stop_loss <= 0:
        return SizedContractPosition(Decimal("0"), None, False, "per-contract loss is invalid")
    quantity = _round_down(budget / one.total_stop_loss, spec.quantity_step)
    if quantity < spec.minimum_quantity or quantity <= 0:
        return SizedContractPosition(Decimal("0"), None, False, "risk budget is below minimum quantity")
    quote = stop_risk(spec, costs, quantity, entry, stop)
    if quote.total_stop_loss > budget:  # decimal guard; must never over-risk
        return SizedContractPosition(Decimal("0"), None, False, "rounded quantity exceeds risk budget")
    return SizedContractPosition(quantity, quote, True, "accepted")
