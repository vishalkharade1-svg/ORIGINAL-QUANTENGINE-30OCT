"""11G-J REAL trade events (superset of 11G canonical, no fork).

Audit finding (corrected 11G-J): Binance UM aggTrades transact_time is
MILLISECOND precision throughout (13 digits; 219,213 distinct ms over
410,535 events; 191,322 same-ms collisions, max 141/ms, mean 1.87/ms).
Intra-ms order therefore comes ONLY from source row order, preserved
as source_index. Ordering key = (event_ms, source_index).

The canonical ms field is retained for 11G compatibility; us-scale
precision does not exist in this source and is never synthesized.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research.phase11g.events import canonical as EV  # noqa: E402

FEATURE_VERSION = "real-trade-features-v1"
TICK_SIZE = 0.01
VENUE = "binance-um"


@dataclass(frozen=True)
class RealTrade:
    event_ms: int
    transact_raw: int
    source_index: int
    symbol: str
    venue: str
    price: float
    quantity: float
    aggressor_side: str  # "buy" | "sell" (provider is_buyer_maker mapping)
    trade_id: str
    first_trade_id: str
    last_trade_id: str
    provenance: str = "REAL"
    feature_version: str = FEATURE_VERSION

    def order_key(self):
        return (self.event_ms, self.source_index)

    def to_canonical(self):
        return EV.TradeEvent(
            symbol=self.symbol, event_timestamp=self.event_ms,
            price=self.price, quantity=self.quantity,
            side=self.aggressor_side, trade_id=self.trade_id,
            source="%s:um-aggTrades" % self.venue, provenance="REAL")


def side_from_buyer_maker(value):
    s = str(value).strip().lower()
    if s in ("true", "1", "t", "yes"):
        return "sell"
    if s in ("false", "0", "f", "no"):
        return "buy"
    raise ValueError("uninterpretable is_buyer_maker: %r" % value)


def from_csv_row(row, source_index, symbol="BTCUSDT", venue=VENUE):
    raw = int(row["transact_time"])
    if not 10 ** 12 <= raw < 10 ** 14:
        # Millisecond epoch expected (13 digits). Anything else means
        # the provider changed precision: fail loud for re-audit rather
        # than silently mis-scaling time.
        raise ValueError("expected millisecond transact_time, got %r" % row["transact_time"])
    return RealTrade(
        event_ms=raw, transact_raw=raw, source_index=source_index,
        symbol=symbol, venue=venue, price=float(row["price"]),
        quantity=float(row["quantity"]),
        aggressor_side=side_from_buyer_maker(row["is_buyer_maker"]),
        trade_id=str(row["agg_trade_id"]),
        first_trade_id=str(row["first_trade_id"]),
        last_trade_id=str(row["last_trade_id"]))
