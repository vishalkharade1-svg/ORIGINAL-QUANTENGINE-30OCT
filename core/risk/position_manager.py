"""
====================================================

QuantEngine

Position Manager

Execution-layer hygiene over the SHARED OrderIntent and the
SHARED Trade objects -- deliberately the INVERSE of the
legacy archived position_manager (which owned its own
Position + SL/TP state and was quarantined under the
No-duplicate-classes rule).

Two responsibilities, both stateless / read-only over shared
objects:

    1. Order refinement (the attack surface, applied by
       TradeSimulator.open_trade for EVERY mode -- Backtest,
       Paper, Live Broker):

           - round quantity to QUANTITY_PRECISION decimals
           - cap notional (entry * quantity) at
             MAX_ALLOCATION_PER_TRADE (scaling quantity down)
           - optionally cap the same way by LEVERAGE * equity
             when equity is provided (manage_into)
           - drop dust: any quantity below MIN_QUANTITY
             invalidates the order (quantity -> 0) so the
             simulator never books a fractional-tick trade

       manage() is PURE: the input OrderIntent is never
       mutated; a corrected copy is returned via replace().
       Applying it twice is a no-op.

    2. Position reading (display only -- SL/TP management
       stays in TradeSimulator.update):

           - unrealized(trade, price)  -> float
           - snapshot(trade, price)    -> dict view of the
             shared open Trade at a market price

The manager keeps NO position state of its own; the open
position remains exactly where the architecture puts it
(TradeSimulator.current_trade / TradeRegistry).

====================================================
"""

from dataclasses import is_dataclass, replace

import math

import config.risk_settings as risk_settings

from core.risk.order_intent import OrderIntent

from core.risk.contract_gate import (
    UNAVAILABLE,
    VERIFIED,
    apply_terms,
    resolve_terms,
)


class _ManagedOrder:
    """Pure attribute-adapter carrying the refined quantity /
    position_value over any order-like source (e.g. the paper
    slippage wrapper) without mutating the original."""

    __slots__ = ("_order", "quantity", "position_value")

    def __init__(self, order, quantity, position_value):
        self._order = order
        self.quantity = quantity
        self.position_value = position_value

    def __getattr__(self, name):
        return getattr(self._order, name)


class PositionManager:

    def __init__(
        self,
        max_allocation=None,
        quantity_precision=None,
        min_quantity=None,
        leverage=None,
    ):

        self.max_allocation = (
            max_allocation
            if max_allocation is not None
            else risk_settings.MAX_ALLOCATION_PER_TRADE
        )

        self.quantity_precision = (
            quantity_precision
            if quantity_precision is not None
            else risk_settings.QUANTITY_PRECISION
        )

        self.min_quantity = (
            min_quantity
            if min_quantity is not None
            else risk_settings.MIN_QUANTITY
        )

        self.leverage = (
            leverage
            if leverage is not None
            else risk_settings.LEVERAGE
        )

    # --------------------------------------------------

    def round_quantity(self, quantity):

        return round(float(quantity), self.quantity_precision)

    # --------------------------------------------------

    def notional(self, quantity, entry):

        return float(quantity) * float(entry)

    # --------------------------------------------------

    def max_quantity(self, entry, equity=None):
        """Maximum executable quantity at `entry` under the
        NOTIONAL cap (11E-Prep H1): quantity * entry <=
        max_allocation, with an optional tighter
        LEVERAGE * equity bound when equity is provided."""

        entry = float(entry)

        if entry <= 0:
            return 0.0

        cap = float(self.max_allocation)

        if (
            equity is not None
            and equity > 0
            and self.leverage > 0
        ):

            leverage_notional = float(self.leverage) * equity

            cap = min(cap, leverage_notional)

        return self.round_quantity(cap / entry)

    # --------------------------------------------------

    def audit(self, order, equity=None):

        """Pure refinement. Returns (corrected, reasons)."""

        reasons = []

        # Tolerant: the legacy signal fallback hands open_trade a
        # SetupCandidate (no quantity/entry). Refinement applies
        # to OrderIntent-shaped orders only -- that path is then
        # byte-identical to the pre-manager behavior.
        if not hasattr(order, "quantity") or not hasattr(order, "entry"):
            return order, []

        raw = float(order.quantity)

        quantity = self.round_quantity(raw)

        if not math.isfinite(quantity):
            # Fail closed (11E-Prep C1-B): a non-finite
            # quantity (NaN/Inf survives every comparison
            # below) can never remain executable. Zero it
            # with an explicit reason instead of leaving
            # quantity = nan inside the position.
            reasons.append(
                f"non-finite quantity {raw} rejected"
            )

            quantity = 0.0

        if quantity < 0:
            # Fail closed: a negative quantity can never be a
            # valid position (previously it propagated onto
            # the corrected copy and relied on open_trade to
            # drop it). Clamp to zero with an explicit reason.
            reasons.append(
                f"{raw:.10f} negative quantity clamped to zero"
            )

            quantity = 0.0

        if raw > 0 and raw < self.min_quantity:

            reasons.append(
                f"{raw:.10f} below minimum quantity "
                f"{self.min_quantity:.0e} (dust)"
            )

            quantity = 0.0

        elif raw > 0 and quantity <= 0:

            reasons.append(
                "quantity rounds to zero below precision "
                f"({self.quantity_precision} decimals)"
            )

            quantity = 0.0

        elif quantity != raw:

            reasons.append(
                f"quantity rounded to {self.quantity_precision} "
                "decimals"
            )

        entry = float(order.entry)

        if not math.isfinite(entry) or entry <= 0:
            # Fail closed: no valid order has a
            # non-positive entry (the PositionSizer already
            # rejects these upstream; this is the
            # defense-in-depth choke-point check). Non-finite
            # entries are rejected here too (11E-Prep C1-B):
            # an Inf entry would otherwise zero the
            # notional cap and pass an infinite notional.
            reasons.append(
                f"invalid entry {entry} (must be finite > 0)"
            )

            quantity = 0.0

        cap = self.max_quantity(entry, equity)

        if cap > 0 and quantity > cap:

            before = quantity

            quantity = cap

            reasons.append(
                f"quantity capped {before:.8f} -> {quantity:.8f} "
                "(notional limit)"
            )

        reconciled = self.notional(quantity, entry)

        # Phase 13 verified-contract enforcement (single choke
        # point for every mode: TradeSimulator.open_trade runs
        # manage()/audit() for Backtest, Paper, and Live Broker).
        # LAYERING (explicit, zero blast radius when unused):
        #   * UNAVAILABLE / SYNTHETIC terms -> silent pass-through.
        #     Legacy float sizing is byte-identical; nothing is
        #     invented and no reason noise is appended (callers
        #     asserting reasons == [] keep passing). Status remains
        #     queryable via contract_gate.resolve_terms().
        #   * VERIFIED terms -> enforced: step floor, minimum,
        #     tick grid, and multiplier-aware budget revalidation.
        #     Violations zero the quantity and invalidate, with
        #     explicit reasons (same fail-closed posture as dust).
        try:
            attached_terms, contract_status = resolve_terms(order)
        except Exception:  # noqa: BLE001 (fail open to legacy)
            attached_terms, contract_status = None, UNAVAILABLE

        if contract_status == VERIFIED and attached_terms is not None:

            try:
                stop_for_gate = float(order.stop_loss)
            except (TypeError, ValueError):
                stop_for_gate = 0.0

            try:
                budget_for_gate = float(
                    getattr(order, "risk_amount", 0.0) or 0.0)
            except (TypeError, ValueError):
                budget_for_gate = 0.0

            gate = apply_terms(
                quantity=quantity,
                entry=entry,
                stop=stop_for_gate,
                risk_amount=budget_for_gate,
                terms=attached_terms,
            )

            reasons.extend(gate.reasons)

            quantity = float(gate.quantity)

            reconciled = self.notional(quantity, entry)

            if not gate.valid:

                quantity = 0.0

                reconciled = 0.0

        if (
            quantity > 0
            and hasattr(order, "position_value")
            and float(order.position_value) > 0
            and float(order.position_value) != reconciled
        ):

            reasons.append(
                "position_value reconciled to entry * quantity"
            )

        corrected = None

        if is_dataclass(order) and not isinstance(order, type):

            corrected = replace(
                order,
                quantity=quantity,
                position_value=reconciled,
                valid=(
                    order.valid and quantity >= self.min_quantity
                ),
                reason=(
                    order.reason
                    if quantity > 0
                    else (
                        "rejected: quantity below minimum"
                        if order.reason == ""
                        else order.reason
                    )
                ),
            )

        else:

            corrected = _ManagedOrder(
                order,
                quantity,
                self.notional(quantity, entry),
            )

        return corrected, reasons

    # --------------------------------------------------

    def manage(self, order):

        corrected, _ = self.audit(order)

        return corrected

    # --------------------------------------------------

    def manage_into(self, order, equity):

        corrected, _ = self.audit(order, equity=equity)

        return corrected

    # --------------------------------------------------

    def unrealized(self, trade, current_price):

        current_price = float(current_price)

        direction = str(trade.direction).upper()

        if direction == "BEARISH":
            return (trade.entry - current_price) * trade.quantity

        return (current_price - trade.entry) * trade.quantity

    # --------------------------------------------------

    def snapshot(self, trade, current_price):

        position_value = self.notional(
            trade.quantity, trade.entry
        )

        pnl = self.unrealized(trade, current_price)

        pnl_percent = (
            (pnl / position_value * 100.0)
            if position_value > 0
            else 0.0
        )

        state = (
            "WIN"
            if pnl > 0
            else "LOSS"
            if pnl < 0
            else "FLAT"
        )

        return {
            "symbol": getattr(trade, "symbol", ""),
            "direction": str(trade.direction).upper(),
            "quantity": trade.quantity,
            "entry": trade.entry,
            "stop_loss": trade.stop_loss,
            "take_profit": trade.take_profit,
            "current_price": current_price,
            "position_value": position_value,
            "unrealized_pnl": pnl,
            "unrealized_percent": pnl_percent,
            "state": state,
        }