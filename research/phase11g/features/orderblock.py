"""11G-A order-block adapter (REAL, OHLCV).

Anchor rule (frozen): last opposite-range candle strictly before the
reference bar (exclusive past lookup — the anchor can never be the
reference bar itself or any later bar). Exposes anchor, zone
(edge/extreme), direction, invalidation (close beyond far extreme),
and formation/confirmation/availability timestamps.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11g.features import common as C


def order_block_at(bars, index, direction):
    """Order block resolved AT bar `index` (uses bars[<index] only)."""
    ob = F11.order_block_before(bars, index, direction)
    if ob is None:
        return C.empty("order_block", index, bars, "phase11f.order_block_before",
                       reason="NO_EVENT")
    edge, far = ob["edge"], ob["extreme"]
    return C.event(
        "order_block",
        {"direction": direction, "edge": edge, "far": far,
         "anchor_index": ob["index"],
         "zone": sorted([edge, far]),
         "invalidation": "close beyond far extreme"},
        index, bars, "phase11f.order_block_before",
        formation=ob["index"], confirmation=index,
        metadata={"anchor_time": int(bars[ob["index"]]["time"])})


def order_block_series(bars, direction):
    return [order_block_at(bars, i, direction) for i in range(len(bars))]
