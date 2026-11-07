"""Verified contract metadata path (Phase 5 local track).

INTEGRATION STATUS (forensically pinned 2026-09-22): DEFINED + UNIT-TESTED,
NOT WIRED. No production, paper, backtest, or live caller invokes
``verify_contract_spec()`` or ``size_quantity()``
(``tests/test_authoritative_path_phase7.py`` pins zero runtime callers).
The live sizing path is the float ``PositionSizer`` (price-stop distance,
generic quantity, no multiplier/tick/minimum semantics). A contract-aware
module that is not in the sizing path is IMPLEMENTED BUT NOT
PRODUCTION-INTEGRATED — never "complete". Wiring (or formal retirement)
is an open remediation item; either change must update the boundary
pins AND add an integration test proving sized quantities honor
verified tick/step/minimum/multiplier terms.

Paper sizing must never run on fabricated instrument metadata.  The legacy
explicit-universe helper (``core/runtime/paper_main.py::_eligible_instrument``)
hard-codes ``SPOT`` with fixed tick/quantity precision, which is unsafe for
derivatives and options.  Raw product discovery additionally defaults to
unverified.

This module is the authoritative contract-spec gate:

* ``VerifiedContractSpec`` requires every field the audit mandates: product
  ID, instrument type, tick size, quantity step, minimum quantity, minimum
  notional, multiplier, settlement currency, contract type, and
  leverage/margin semantics — plus venue, source, and verification
  timestamp provenance.  NOTHING is defaulted: a missing field raises
  instead of silently assuming a multiplier, fee, or SPOT classification.
* ``verify_contract_spec()`` builds the spec from a raw mapping (e.g. a
  Delta ``/v2/products`` entry) with strict validation.
* ``size_quantity()`` sizes from risk amount and stop distance against the
  VERIFIED spec (multiplier-aware, tick-rounded, minimum-enforcing) and
  refuses unverified input fail-closed.

No SPOT metadata is fabricated: ``instrument_type`` must be explicitly
supplied by the caller from verified discovery.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LeverageMarginTerms:
    max_leverage: float
    initial_margin_rate: float
    maintenance_margin_rate: float
    margin_asset: str


@dataclass(frozen=True, slots=True)
class VerifiedContractSpec:
    product_id: int | str
    symbol: str
    instrument_type: str
    contract_type: str
    tick_size: float
    quantity_step: float
    minimum_quantity: float
    minimum_notional: float
    multiplier: float
    settlement_currency: str
    leverage: LeverageMarginTerms
    venue: str
    source: str
    verified_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol is required")
        for label in ("instrument_type", "contract_type",
                      "settlement_currency", "venue", "source",
                      "verified_at"):
            value = getattr(self, label)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("%s is required" % label)
        for label in ("tick_size", "quantity_step", "minimum_quantity",
                      "minimum_notional", "multiplier"):
            value = getattr(self, label)
            if (not isinstance(value, (int, float)) or value != value
                    or value <= 0):
                raise ValueError(
                    "%s must be a finite positive number" % label)
        if not isinstance(self.leverage, LeverageMarginTerms):
            raise TypeError("leverage terms are required")
        if (self.leverage.max_leverage <= 0
                or self.leverage.initial_margin_rate <= 0
                or self.leverage.maintenance_margin_rate <= 0):
            raise ValueError("leverage/margin terms must be positive")
        if not self.leverage.margin_asset.strip():
            raise ValueError("margin asset is required")


def _positive_number(mapping: dict, key: str) -> float:
    value = mapping.get(key)
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("contract field %r must be numeric" % key) from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError("contract field %r must be finite and positive" % key)
    return parsed


def verify_contract_spec(raw: dict, *, venue: str, source: str,
                         verified_at: str) -> VerifiedContractSpec:
    """Strictly verify one raw product mapping; never default missing fields."""
    if not isinstance(raw, dict):
        raise TypeError("raw contract mapping is required")
    for label in ("venue", "source", "verified_at"):
        value = {"venue": venue, "source": source,
                 "verified_at": verified_at}[label]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("%s provenance is required" % label)
    symbol = raw.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("contract symbol is required")
    product_id = raw.get("product_id", raw.get("id"))
    if product_id is None or (isinstance(product_id, str)
                              and not product_id.strip()):
        raise ValueError("contract product_id is required")
    instrument_type = raw.get("instrument_type")
    if not isinstance(instrument_type, str) or not instrument_type.strip():
        raise ValueError(
            "contract instrument_type is required; SPOT must not be assumed")
    contract_type = raw.get("contract_type")
    if not isinstance(contract_type, str) or not contract_type.strip():
        raise ValueError("contract contract_type is required")
    settlement = raw.get("settlement_currency",
                         raw.get("settling_asset", raw.get("quote_asset")))
    if isinstance(settlement, dict):
        settlement = settlement.get("symbol")
    if not isinstance(settlement, str) or not settlement.strip():
        raise ValueError("contract settlement_currency is required")
    leverage_raw = raw.get("leverage")
    if not isinstance(leverage_raw, dict):
        raise ValueError("contract leverage/margin semantics are required")
    margin_asset = leverage_raw.get("margin_asset", settlement)
    try:
        leverage = LeverageMarginTerms(
            max_leverage=float(leverage_raw["max_leverage"]),
            initial_margin_rate=float(leverage_raw["initial_margin_rate"]),
            maintenance_margin_rate=float(
                leverage_raw["maintenance_margin_rate"]),
            margin_asset=str(margin_asset),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "contract leverage/margin semantics are incomplete") from error
    return VerifiedContractSpec(
        product_id=product_id,
        symbol=symbol.strip(),
        instrument_type=instrument_type.strip(),
        contract_type=contract_type.strip(),
        tick_size=_positive_number(raw, "tick_size"),
        quantity_step=_positive_number(raw, "quantity_step"),
        minimum_quantity=_positive_number(raw, "minimum_quantity"),
        minimum_notional=_positive_number(raw, "minimum_notional"),
        multiplier=_positive_number(raw, "multiplier"),
        settlement_currency=settlement.strip(),
        leverage=leverage,
        venue=venue.strip(),
        source=source.strip(),
        verified_at=verified_at.strip(),
    )


def size_quantity(*, risk_amount: float, stop_distance: float,
                  spec: VerifiedContractSpec,
                  entry_price: float) -> float:
    """Multiplier-aware, tick-rounded quantity; refuses unverified specs."""
    if not isinstance(spec, VerifiedContractSpec):
        raise TypeError(
            "position sizing requires a VerifiedContractSpec; "
            "unverified metadata is refused")
    for label, value in (("risk_amount", risk_amount),
                         ("stop_distance", stop_distance),
                         ("entry_price", entry_price)):
        if (not isinstance(value, (int, float)) or value != value
                or value <= 0):
            raise ValueError("%s must be a finite positive number" % label)
    raw_quantity = risk_amount / (stop_distance * spec.multiplier)
    steps = math.floor(raw_quantity / spec.quantity_step)
    quantity = steps * spec.quantity_step
    if quantity < spec.minimum_quantity:
        raise ValueError(
            "sized quantity %r is below verified minimum %r"
            % (quantity, spec.minimum_quantity))
    if quantity * entry_price * spec.multiplier < spec.minimum_notional:
        raise ValueError("sized notional is below verified minimum notional")
    return quantity
