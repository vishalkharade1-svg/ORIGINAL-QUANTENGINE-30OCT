"""Strict parser/state machine for Delta public order-book WebSocket evidence.

No network client lives here. The caller supplies decoded Delta messages from an
actual transport. This module enforces snapshot/update sequencing and emits
canonical top-of-book observations suitable for Phase-74 friction evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class DeltaBookObservation:
    symbol: str
    timestamp_us: int
    sequence: int
    best_bid: str
    best_ask: str

    def to_sample(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp_ms": self.timestamp_us // 1000,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
        }


class DeltaOrderbookState:
    """Fail-closed ob_updates state machine.

    A snapshot establishes the book. Every subsequent update must advance the
    sequence by exactly one. A gap invalidates the state and requires a new
    snapshot/subscription before observations can resume.
    """

    def __init__(self, symbol: str):
        if not symbol:
            raise ValueError("symbol is required")
        self.symbol = symbol
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self._sequence: int | None = None
        self._timestamp_us: int | None = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def sequence(self) -> int | None:
        return self._sequence

    def reset(self) -> None:
        self._bids.clear()
        self._asks.clear()
        self._sequence = None
        self._timestamp_us = None
        self._ready = False

    @staticmethod
    def _levels(raw: Any, side: str) -> list[tuple[Decimal, Decimal]]:
        if not isinstance(raw, list):
            raise ValueError(f"{side} levels must be a list")
        out: list[tuple[Decimal, Decimal]] = []
        for row in raw:
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                raise ValueError(f"malformed {side} level")
            try:
                price = Decimal(str(row[0])); size = Decimal(str(row[1]))
            except Exception as exc:
                raise ValueError(f"malformed {side} numeric level") from exc
            if not price.is_finite() or not size.is_finite() or price <= 0 or size < 0:
                raise ValueError(f"invalid {side} level")
            out.append((price, size))
        return out

    def _validate_book(self) -> None:
        if not self._bids or not self._asks:
            raise ValueError("orderbook has no two-sided top of book")
        bid = max(self._bids)
        ask = min(self._asks)
        if ask <= bid:
            raise ValueError("crossed or locked orderbook")

    def apply(self, message: Mapping[str, Any]) -> DeltaBookObservation | None:
        if not isinstance(message, Mapping) or message.get("type") != "ob_updates":
            raise ValueError("expected Delta ob_updates message")
        if str(message.get("sy")) != self.symbol:
            raise ValueError("orderbook symbol mismatch")
        action = message.get("action")
        if action not in {"snapshot", "update"}:
            if action == "error":
                self.reset()
                raise ValueError("Delta orderbook error message")
            raise ValueError("unsupported orderbook action")
        try:
            seq = int(message["seq"]); ts = int(message["ts"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("orderbook sequence/timestamp missing") from exc
        if seq <= 0 or ts <= 0:
            raise ValueError("invalid orderbook sequence/timestamp")

        bids = self._levels(message.get("b", []), "bid")
        asks = self._levels(message.get("a", []), "ask")
        if action == "snapshot":
            if self._ready:
                raise ValueError("duplicate snapshot while book is active")
            self._bids = {p: s for p, s in bids if s > 0}
            self._asks = {p: s for p, s in asks if s > 0}
            self._sequence = seq
            self._timestamp_us = ts
            self._validate_book()
            self._ready = True
        else:
            if not self._ready or self._sequence is None:
                raise ValueError("update received before snapshot")
            if seq != self._sequence + 1:
                self.reset()
                raise ValueError("orderbook sequence gap; resubscribe required")
            for price, size in bids:
                if size == 0: self._bids.pop(price, None)
                else: self._bids[price] = size
            for price, size in asks:
                if size == 0: self._asks.pop(price, None)
                else: self._asks[price] = size
            self._validate_book()
            self._sequence = seq
            self._timestamp_us = ts

        bid = max(self._bids); ask = min(self._asks)
        return DeltaBookObservation(self.symbol, ts, seq, str(bid), str(ask))
