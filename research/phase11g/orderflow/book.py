"""11G-E order-book reconstruction (deterministic, validated).

Consumes BookSnapshotEvents + BookDeltaEvents in (timestamp, sequence)
order. Validates: sequence continuity (when sequenced), crossed book,
stale book (event older than state), missing updates (sequence gaps),
out-of-order, duplicates. Rejections are observable; the book only
advances on valid updates. Same raw input always yields same state.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11g.events.canonical import BookDeltaEvent, BookSnapshotEvent


class BookState:
    def __init__(self):
        self.bids = {}
        self.asks = {}
        self.last_sequence = None
        self.last_timestamp = None
        self.rejections = []

    def snapshot(self):
        return {"bids": dict(self.bids), "asks": dict(self.asks),
                "best_bid": max(self.bids) if self.bids else None,
                "best_ask": min(self.asks) if self.asks else None}

    def crossed(self):
        s = self.snapshot()
        if s["best_bid"] is not None and s["best_ask"] is not None:
            return s["best_bid"] >= s["best_ask"]
        return False

    def apply(self, event):
        if isinstance(event, BookSnapshotEvent):
            return self._apply_snapshot(event)
        if isinstance(event, BookDeltaEvent):
            return self._apply_delta(event)
        self.rejections.append({"event": str(event), "reason": ["unknown-event"]})
        return False

    def _sequence_ok(self, event):
        if event.sequence is None or self.last_sequence is None:
            return True
        if event.sequence == self.last_sequence:
            self.rejections.append({"sequence": event.sequence,
                                    "reason": ["duplicate-update"]})
            return False
        if event.sequence < self.last_sequence:
            self.rejections.append({"sequence": event.sequence,
                                    "reason": ["out-of-order-update"]})
            return False
        if event.sequence > self.last_sequence + 1:
            self.rejections.append({"sequence": event.sequence,
                                    "reason": ["missing-update"]})
        return True

    def _time_ok(self, event):
        if event.event_timestamp is None or self.last_timestamp is None:
            return True
        if event.event_timestamp < self.last_timestamp:
            self.rejections.append({"sequence": event.sequence,
                                    "reason": ["stale-book"]})
            return False
        return True

    def _apply_snapshot(self, event):
        if not self._time_ok(event):
            return False
        bids = {float(p): float(q) for p, q in (event.bids or []) if float(q) > 0}
        asks = {float(p): float(q) for p, q in (event.asks or []) if float(q) > 0}
        if bids and asks and max(bids) >= min(asks):
            self.rejections.append({"sequence": event.sequence,
                                    "reason": ["crossed-book"]})
            return False
        self.bids, self.asks = bids, asks
        self.last_sequence = event.sequence
        self.last_timestamp = event.event_timestamp
        return True

    def _apply_delta(self, event):
        if event.price is None or event.quantity is None or event.side is None:
            self.rejections.append({"sequence": event.sequence,
                                    "reason": ["malformed-event"]})
            return False
        if event.price <= 0 or event.quantity < 0:
            self.rejections.append({"sequence": event.sequence,
                                    "reason": ["impossible-price"
                                               if event.price <= 0
                                               else "negative-quantity"]})
            return False
        if not self._time_ok(event) or not self._sequence_ok(event):
            return False
        book = dict(self.bids) if event.side == "bid" else dict(self.asks)
        if event.quantity == 0:
            book.pop(float(event.price), None)
        else:
            book[float(event.price)] = float(event.quantity)
        trial_bids = book if event.side == "bid" else self.bids
        trial_asks = book if event.side == "ask" else self.asks
        if trial_bids and trial_asks and max(trial_bids) >= min(trial_asks):
            self.rejections.append({"sequence": event.sequence,
                                    "reason": ["crossed-book"]})
            return False
        if event.side == "bid":
            self.bids = book
        else:
            self.asks = book
        self.last_sequence = event.sequence
        self.last_timestamp = event.event_timestamp
        return True
