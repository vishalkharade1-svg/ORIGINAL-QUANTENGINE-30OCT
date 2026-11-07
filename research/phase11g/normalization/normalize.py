"""11G-E normalization (raw dicts -> canonical events, deterministic).

OHLCV path: REAL. Trade/quote/book paths: REQUIRE their source fields;
missing fields raise DataMissing (never silently estimated). Output
ordering is deterministic (timestamp, then sequence, then type rank).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11g.events import canonical as EV


class DataMissing(ValueError):
    pass


def _req(row, *keys):
    for k in keys:
        if k not in row or row[k] is None:
            raise DataMissing("missing required field %r" % k)
    return True


def normalize_candles(rows, symbol, timeframe="1m", source="delta:/v2/history/candles",
                      provenance="REAL"):
    out = []
    for r in rows:
        _req(r, "time", "open", "high", "low", "close", "volume")
        out.append(EV.CandleEvent(
            symbol=symbol, event_timestamp=int(r["time"]),
            exchange_timestamp=int(r.get("exchange_time", r["time"])),
            timeframe=timeframe, open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]),
            volume=float(r["volume"]), closed=bool(r.get("closed", True)),
            source=source, provenance=provenance))
    return out


def normalize_trades(rows, symbol, source, provenance="REAL"):
    out = []
    for r in rows:
        _req(r, "time", "price", "quantity")
        if "side" not in r or r["side"] is None:
            raise DataMissing("trade side required for REAL classification")
        out.append(EV.TradeEvent(
            symbol=symbol, event_timestamp=int(r["time"]),
            exchange_timestamp=int(r.get("exchange_time", r["time"])),
            receive_timestamp=r.get("receive_time"),
            sequence=r.get("sequence"), price=float(r["price"]),
            quantity=float(r["quantity"]), side=str(r["side"]),
            trade_id=r.get("trade_id"), source=source, provenance=provenance))
    return out


def normalize_quotes(rows, symbol, source, provenance="REAL"):
    out = []
    for r in rows:
        _req(r, "time", "bid", "ask")
        out.append(EV.QuoteEvent(
            symbol=symbol, event_timestamp=int(r["time"]),
            exchange_timestamp=int(r.get("exchange_time", r["time"])),
            sequence=r.get("sequence"), bid=float(r["bid"]), ask=float(r["ask"]),
            bid_size=r.get("bid_size"), ask_size=r.get("ask_size"),
            quote_id=r.get("quote_id"), source=source, provenance=provenance))
    return out


_TYPE_RANK = {t: i for i, t in enumerate(EV.EVENT_TYPES)}


def order_stream(events):
    """Deterministic ordering: (event_timestamp, sequence-or-0, type rank)."""
    def key(e):
        return (e.event_timestamp if e.event_timestamp is not None else 0,
                e.sequence if e.sequence is not None else 0,
                _TYPE_RANK.get(e.event_type, 99))
    return sorted(events, key=key)
