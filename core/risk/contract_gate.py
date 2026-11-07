"""
====================================================

QuantEngine

Verified-Contract Enforcement Gate (Phase 13)

The single choke point where VERIFIED contract semantics meet the
executable sizing path. Consumed by PositionManager.audit — which
TradeSimulator.open_trade runs for EVERY mode (Backtest, Paper,
Live Broker) — so verified terms, once attached to an order, are
enforced identically in all modes with no per-mode duplicate.

Status model (explicit; never fabricate):

    VERIFIED    order carries explicitly verified contract terms
                (tick_size, quantity_step, minimum_quantity,
                multiplier + provenance). Terms are ENFORCED:
                quantity is floored to the step, checked against
                the minimum, the entry is checked against the tick,
                and the multiplier-aware risk is revalidated
                against the risk budget. Violations fail closed.
    SYNTHETIC   order carries explicitly synthetic terms (e.g. the
                paper explicit-universe fallback). Labeled, NEVER
                enforced as venue truth; legacy float sizing passes
                through unchanged.
    UNAVAILABLE no contract terms attached. Legacy float sizing
                passes through unchanged (byte-identical); nothing
                is invented. Operations that REQUIRE verified
                semantics must refuse UNAVAILABLE via
                require_verified() — they must never silently size.

Domain matrix (Phase-14 adjudication — the pass-through above is
domain-scoped to SIMULATION, never a live authorization):

    Backtest  : VERIFIED enforced / UNAVAILABLE legacy / SYNTHETIC
                legacy-labeled (explicit LOCAL/UNVERIFIED).
    Paper     : same as Backtest; fills additionally consume
                paper_cost_profile().
    Dry-run   : same as Paper (entry-point paper stack).
    Live      : VERIFIED order terms do NOT authorize — the live
                trust root is the venue ContractRegistry plus
                live_execution evidence plus the safety gate
                (DeltaOrderExecutor._contract /
                _require_execution_evidence). UNAVAILABLE or
                SYNTHETIC registry state raises
                InvalidContractError BEFORE any transport, so a
                live order can never be authorized by missing or
                synthetic metadata. The executor additionally
                floors venue size (never increases it) and
                revalidates size/minimum/tick on the built payload.

This gate CONSUMES the contract-math library (contract_math /
contract_spec_factory) for its numeric primitives where they fit
the float executable world; it does not duplicate their Decimal
budget solver. PositionSizer remains the float sizing leg; this
gate is the enforcement leg. No venue values are invented here:
every numeric term must arrive attached to the order (future
provider discovery) or in tests.

====================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

VERIFIED = "VERIFIED"
SYNTHETIC = "SYNTHETIC"
UNAVAILABLE = "UNAVAILABLE"

_REQUIRED_NUMERIC_TERMS = (
    "tick_size",
    "quantity_step",
    "minimum_quantity",
    "multiplier",
)


@dataclass(frozen=True)
class ContractVerdict:
    """Outcome of verified-contract enforcement on one order."""

    quantity: float
    position_value: float
    status: str
    valid: bool
    reasons: tuple = field(default_factory=tuple)


def _finite_positive(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def resolve_terms(order: Any) -> tuple[dict | None, str]:
    """Resolve the contract terms attached to an order.

    Reads ``order.contract_terms`` (tolerant: missing attribute or
    None means no terms). Returns (terms, status) where status is
    one of VERIFIED / SYNTHETIC / UNAVAILABLE. Pure; never raises;
    never invents terms.
    """
    try:
        attached = getattr(order, "contract_terms", None)
    except Exception:  # noqa: BLE001 (fail closed to UNAVAILABLE)
        return None, UNAVAILABLE
    if attached is None:
        return None, UNAVAILABLE
    if not isinstance(attached, dict):
        return None, UNAVAILABLE
    if attached.get("verified") is True:
        terms: dict[str, float] = {}
        for name in _REQUIRED_NUMERIC_TERMS:
            parsed = _finite_positive(attached.get(name))
            if parsed is None:
                return None, UNAVAILABLE
            terms[name] = parsed
        return terms, VERIFIED
    return None, SYNTHETIC


def require_verified(order: Any) -> dict:
    """Return verified terms or fail closed.

    For operations that REQUIRE verified contract semantics
    (derivative sizing, live order construction): VERIFIED terms
    pass through; SYNTHETIC or UNAVAILABLE raise instead of
    silently sizing on fabricated metadata.
    """
    terms, status = resolve_terms(order)
    if status != VERIFIED or terms is None:
        raise ValueError(
            "verified contract terms are %s; refusing to size "
            "without venue-verified tick/step/minimum/multiplier"
            % status)
    return terms


def apply_terms(*, quantity: float, entry: float, stop: float,
                risk_amount: float, terms: dict) -> ContractVerdict:
    """Enforce verified terms on one candidate quantity. Pure.

    * Floors quantity DOWN to ``quantity_step`` (never rounds up:
      rounding up would exceed the risk budget).
    * Refuses (valid=False, quantity 0) when the floored quantity
      is below ``minimum_quantity``, when entry is not on the
      ``tick_size`` grid, on any non-finite input, or when the
      multiplier-aware risk (qty * |entry - stop| * multiplier)
      exceeds a positive ``risk_amount`` budget.
    * A non-positive ``risk_amount`` means "no budget to validate
      against" (scripted flows carry 0.0): discrete feasibility
      (step/minimum/tick) is still enforced, the budget check is
      skipped and documented in reasons.
    * LONG and SHORT are symmetric: only absolute distances enter
      the math.
    """
    reasons: list[str] = []

    quantity_f = _finite_positive(quantity)
    entry_f = _finite_positive(entry)
    tick = _finite_positive(terms.get("tick_size")) if terms else None
    step = _finite_positive(terms.get("quantity_step")) if terms else None
    minimum = _finite_positive(terms.get("minimum_quantity")) if terms else None
    multiplier = _finite_positive(terms.get("multiplier")) if terms else None

    def _refuse(reason: str) -> ContractVerdict:
        reasons.append(reason)
        return ContractVerdict(quantity=0.0, position_value=0.0,
                               status=VERIFIED, valid=False,
                               reasons=tuple(reasons))

    if quantity_f is None:
        return _refuse("contract gate: quantity is non-finite or "
                       "non-positive")
    if entry_f is None:
        return _refuse("contract gate: entry is non-finite or "
                       "non-positive")
    if tick is None or step is None or minimum is None \
            or multiplier is None:
        return _refuse("contract gate: verified terms are incomplete")

    try:
        stop_f = float(stop)
    except (TypeError, ValueError):
        return _refuse("contract gate: stop is non-numeric")
    if not math.isfinite(stop_f):
        return _refuse("contract gate: stop is non-finite")
    distance = abs(entry_f - stop_f)
    if distance <= 0:
        return _refuse("contract gate: stop distance must be "
                       "non-zero")

    # Entry must sit on the venue tick grid (within a tight
    # relative tolerance for float-grid artifacts).
    ticks = entry_f / tick
    if abs(ticks - round(ticks)) > 1e-6:
        return _refuse("contract gate: entry %.10f is off the "
                       "tick grid (tick %.10f)" % (entry_f, tick))

    steps = math.floor(quantity_f / step + 1e-9)
    floored = steps * step
    if floored < minimum or floored <= 0:
        return _refuse("contract gate: stepped quantity %.10f is "
                       "below verified minimum %.10f"
                       % (floored, minimum))
    if floored != quantity_f:
        reasons.append("contract gate: quantity floored to step "
                       "(%.10f -> %.10f)" % (quantity_f, floored))

    try:
        budget = float(risk_amount)
    except (TypeError, ValueError):
        budget = 0.0
    if math.isfinite(budget) and budget > 0:
        sized_risk = floored * distance * multiplier
        if sized_risk > budget * (1.0 + 1e-9):
            return _refuse("contract gate: multiplier-aware risk "
                           "%.6f exceeds budget %.6f"
                           % (sized_risk, budget))
        reasons.append("contract gate: multiplier-aware risk "
                       "%.6f within budget %.6f"
                       % (sized_risk, budget))
    else:
        reasons.append("contract gate: no risk budget to validate "
                       "against (risk_amount <= 0); discrete "
                       "feasibility only")

    return ContractVerdict(quantity=floored,
                           position_value=floored * entry_f,
                           status=VERIFIED, valid=True,
                           reasons=tuple(reasons))
