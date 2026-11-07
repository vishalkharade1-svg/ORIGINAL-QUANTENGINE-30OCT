"""11G-E canonical event model (schema-frozen, provenance-tagged).

Event types: CandleEvent, TradeEvent, QuoteEvent, BookSnapshotEvent,
BookDeltaEvent, FundingEvent, OpenInterestEvent, LiquidationEvent.
Unavailable source fields stay None — never synthesized. Schema
version is pinned per event for forward-compatibility checks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "11ge-v1"


@dataclass(frozen=True)
class BaseEvent:
    event_type: str = ""
    symbol: str = ""
    event_timestamp: Optional[int] = None
    exchange_timestamp: Optional[int] = None
    receive_timestamp: Optional[int] = None
    sequence: Optional[int] = None
    source: str = ""
    provenance: str = "REAL"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandleEvent(BaseEvent):
    event_type: str = "candle"
    timeframe: str = "1m"
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    closed: bool = True


@dataclass(frozen=True)
class TradeEvent(BaseEvent):
    event_type: str = "trade"
    price: Optional[float] = None
    quantity: Optional[float] = None
    side: Optional[str] = None
    trade_id: Optional[str] = None


@dataclass(frozen=True)
class QuoteEvent(BaseEvent):
    event_type: str = "quote"
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    quote_id: Optional[str] = None


@dataclass(frozen=True)
class BookSnapshotEvent(BaseEvent):
    event_type: str = "book_snapshot"
    bids: List[List[float]] = field(default_factory=list)
    asks: List[List[float]] = field(default_factory=list)


@dataclass(frozen=True)
class BookDeltaEvent(BaseEvent):
    event_type: str = "book_delta"
    side: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None
    is_snapshot: bool = False


@dataclass(frozen=True)
class FundingEvent(BaseEvent):
    event_type: str = "funding"
    rate: Optional[float] = None


@dataclass(frozen=True)
class OpenInterestEvent(BaseEvent):
    event_type: str = "open_interest"
    open_interest: Optional[float] = None


@dataclass(frozen=True)
class LiquidationEvent(BaseEvent):
    event_type: str = "liquidation"
    price: Optional[float] = None
    quantity: Optional[float] = None
    side: Optional[str] = None


EVENT_TYPES = ("candle", "trade", "quote", "book_snapshot", "book_delta",
               "funding", "open_interest", "liquidation")
