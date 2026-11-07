from __future__ import annotations

import pytest

from core.execution.position_fill_reconciliation import (
    PositionFillReconciliationError,
    reconstruct_signed_position,
    compare_position_to_fills,
)


def fill(fid, side, size, product_id=84):
    return {"id": fid, "order_id": int(fid), "product_id": product_id,
            "side": side, "size": str(size), "price": "100"}


def test_signed_position_reconstruction_nets_buys_and_sells():
    result = reconstruct_signed_position(
        [fill("1", "buy", "2.5"), fill("2", "sell", "1.25")], product_id=84
    )
    assert result["expected_signed_quantity"] == "1.25"
    assert result["buy_quantity"] == "2.5"
    assert result["sell_quantity"] == "1.25"


@pytest.mark.parametrize("rows", [
    [fill("1", "buy", "1"), fill("1", "sell", "1")],
    [fill("1", "hold", "1")],
    [fill("1", "buy", "0")],
    [fill("1", "buy", "NaN")],
    [fill("1", "buy", "1", product_id=85)],
])
def test_invalid_or_duplicate_fill_evidence_rejected(rows):
    with pytest.raises(PositionFillReconciliationError):
        reconstruct_signed_position(rows, product_id=84)


def test_position_quantity_matches_reconstructed_fills():
    fills = [fill("1", "buy", "3"), fill("2", "sell", "1")]
    rebuilt = reconstruct_signed_position(fills, product_id=84)
    result = compare_position_to_fills(
        rebuilt, [{"size": "2", "query_product_id": 84}], product_id=84
    )
    assert result["matches"] is True
    assert result["difference"] == "0"


def test_position_mismatch_is_explicit():
    rebuilt = reconstruct_signed_position([fill("1", "buy", "3")], product_id=84)
    result = compare_position_to_fills(
        rebuilt, [{"size": "2", "query_product_id": 84}], product_id=84
    )
    assert result["matches"] is False
    assert result["review"] == "POSITION_FILL_QUANTITY_MISMATCH"


@pytest.mark.parametrize("positions", [[], [{"size": "1", "query_product_id": 84},
                                               {"size": "0", "query_product_id": 84}]])
def test_missing_or_multiple_position_rows_are_ambiguous(positions):
    rebuilt = reconstruct_signed_position([], product_id=84)
    with pytest.raises(PositionFillReconciliationError):
        compare_position_to_fills(rebuilt, positions, product_id=84)
