"""Forensic signed-position reconstruction from venue fill evidence.

The calculation assumes a single netted position for one product, signed BUY
positive and SELL negative. It is diagnostic only: unsupported position modes,
ambiguous rows, or incomplete fill evidence are never certified as a match.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


class PositionFillReconciliationError(ValueError):
    """Fill/position evidence cannot be safely interpreted."""


def _decimal(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise PositionFillReconciliationError(f"{label} is not a valid decimal") from None
    if not number.is_finite():
        raise PositionFillReconciliationError(f"{label} must be finite")
    return number


def reconstruct_signed_position(
    fills: Iterable[dict[str, Any]], *, product_id: int
) -> dict[str, Any]:
    """Reconstruct signed quantity and detect duplicate/ambiguous fill evidence."""
    seen: set[str] = set()
    signed = Decimal("0")
    buy_qty = Decimal("0")
    sell_qty = Decimal("0")
    count = 0
    for index, fill in enumerate(fills):
        if not isinstance(fill, dict):
            raise PositionFillReconciliationError(f"fill row {index} must be an object")
        if str(fill.get("product_id", "")) != str(product_id):
            raise PositionFillReconciliationError(f"fill row {index} product scope mismatch")
        fill_id = str(fill.get("id", fill.get("fill_id", ""))).strip()
        if not fill_id:
            raise PositionFillReconciliationError(f"fill row {index} missing stable fill ID")
        if fill_id in seen:
            raise PositionFillReconciliationError(f"duplicate fill ID {fill_id!r}")
        seen.add(fill_id)
        side = str(fill.get("side", "")).strip().lower()
        if side not in {"buy", "sell"}:
            raise PositionFillReconciliationError(f"fill {fill_id!r} has unsupported side")
        qty = _decimal(fill.get("size"), f"fill {fill_id!r} size")
        if qty <= 0:
            raise PositionFillReconciliationError(f"fill {fill_id!r} size must be positive")
        # Price is required by the venue adapter; validate here as well so a
        # malformed fill cannot contribute to a seemingly valid exposure.
        price = _decimal(fill.get("price"), f"fill {fill_id!r} price")
        if price <= 0:
            raise PositionFillReconciliationError(f"fill {fill_id!r} price must be positive")
        if side == "buy":
            signed += qty
            buy_qty += qty
        else:
            signed -= qty
            sell_qty += qty
        count += 1
    return {
        "fill_count": count,
        "unique_fill_count": len(seen),
        "buy_quantity": str(buy_qty),
        "sell_quantity": str(sell_qty),
        "expected_signed_quantity": str(signed),
        "position_model": "NETTED_SIGNED_BUY_POSITIVE_SELL_NEGATIVE",
        "certified": True,
    }


def compare_position_to_fills(
    reconstruction: dict[str, Any], positions: Iterable[dict[str, Any]], *, product_id: int
) -> dict[str, Any]:
    """Compare reconstructed net exposure with exactly one scoped position row."""
    rows = list(positions)
    if len(rows) != 1:
        raise PositionFillReconciliationError(
            "exactly one product-scoped position row is required; empty/multiple rows are ambiguous"
        )
    position = rows[0]
    if not isinstance(position, dict):
        raise PositionFillReconciliationError("position row must be an object")
    scoped_product = position.get("product_id", position.get("query_product_id"))
    if str(scoped_product) != str(product_id):
        raise PositionFillReconciliationError("position product scope mismatch")
    # Delta's signed `size` is the comparison quantity. Do not infer sign from
    # side/entry fields or silently abs() the quantity.
    actual = _decimal(position.get("size"), "exchange position size")
    expected = _decimal(reconstruction.get("expected_signed_quantity"), "reconstructed quantity")
    difference = actual - expected
    return {
        "expected_signed_quantity": str(expected),
        "exchange_signed_quantity": str(actual),
        "difference": str(difference),
        "matches": difference == 0,
        "certified": True,
        "position_model": reconstruction["position_model"],
        "review": "MATCH" if difference == 0 else "POSITION_FILL_QUANTITY_MISMATCH",
    }
