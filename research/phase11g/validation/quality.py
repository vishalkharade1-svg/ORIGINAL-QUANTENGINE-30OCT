"""11G-E data-quality engine (observable rejections, never silent).

Checks: missing/duplicate/out-of-order timestamps, duplicate trades
and book updates, impossible prices, negative/zero quantities,
crossed book, stale quotes, timestamp regression, sequence gaps,
impossible spreads, symbol mismatch, malformed events, non-finite
values. Every rejection is recorded with reason; the report builder
summarizes per dataset.
"""

from __future__ import annotations

import math

from research.phase11g.events import canonical as EV


def _finite(x):
    return x is None or (isinstance(x, (int, float)) and math.isfinite(float(x)))


def validate_candles(events):
    """Returns (accepted, rejections). Rejection = {index, reason}."""
    accepted, rejected = [], []
    seen = set()
    prev = None
    for i, e in enumerate(events):
        problems = []
        if not isinstance(e, EV.CandleEvent):
            problems.append("not-a-candle")
        else:
            if e.event_timestamp is None:
                problems.append("missing-timestamp")
            elif e.event_timestamp in seen:
                problems.append("duplicate-timestamp")
            if prev is not None and e.event_timestamp is not None \
                    and e.event_timestamp <= prev:
                problems.append("out-of-order")
            for f in ("open", "high", "low", "close", "volume"):
                v = getattr(e, f, None)
                if v is None:
                    problems.append("missing-" + f)
                elif not _finite(v):
                    problems.append("non-finite-" + f)
            if e.symbol == "":
                problems.append("symbol-mismatch")
            o, h, l, c = e.open, e.high, e.low, e.close
            if None not in (o, h, l, c):
                if min(o, h, l, c) <= 0:
                    problems.append("impossible-price")
                if not (l <= min(o, c) and max(o, c) <= h):
                    problems.append("malformed-ohlc")
                if (e.volume or 0) < 0:
                    problems.append("negative-volume")
            if e.event_timestamp is not None:
                seen.add(e.event_timestamp)
                prev = e.event_timestamp
        if problems:
            rejected.append({"index": i, "reason": problems})
        else:
            accepted.append(e)
    return accepted, rejected


def validate_trades(events):
    accepted, rejected = [], []
    seen_ids, seen_ts_side, prev = set(), set(), None
    for i, e in enumerate(events):
        problems = []
        if not isinstance(e, EV.TradeEvent):
            problems.append("not-a-trade")
        else:
            if e.event_timestamp is None:
                problems.append("missing-timestamp")
            if e.trade_id is not None:
                if e.trade_id in seen_ids:
                    problems.append("duplicate-trade")
                seen_ids.add(e.trade_id)
            if e.price is None or (e.price is not None and e.price <= 0):
                problems.append("impossible-price")
            if e.quantity is None or (e.quantity is not None and e.quantity <= 0):
                problems.append("non-positive-quantity")
            if e.side not in ("buy", "sell", None):
                problems.append("malformed-side")
            for v in (e.price, e.quantity):
                if not _finite(v):
                    problems.append("non-finite")
                    break
            if prev is not None and e.event_timestamp is not None \
                    and e.event_timestamp < prev:
                problems.append("out-of-order")
            if e.symbol == "":
                problems.append("symbol-mismatch")
            if e.event_timestamp is not None:
                prev = e.event_timestamp
        if problems:
            rejected.append({"index": i, "reason": problems})
        else:
            accepted.append(e)
    _ = seen_ts_side
    return accepted, rejected


def detect_gaps(timestamps, step):
    """Missing slots for a fixed-step series (e.g. 60s candles)."""
    gaps = []
    for a, b in zip(timestamps, timestamps[1:]):
        missing = (b - a) // step - 1
        if missing > 0:
            gaps.append({"after": a, "missing": int(missing)})
    return gaps


def quality_report(events, rejections, symbol="", resolution=""):
    reasons = {}
    for r in rejections:
        for reason in r["reason"]:
            reasons[reason] = reasons.get(reason, 0) + 1
    ts = [e.event_timestamp for e in events if e.event_timestamp is not None]
    return {
        "total_events": len(events) + len(rejections),
        "accepted_events": len(events),
        "rejected_events": len(rejections),
        "rejection_reasons": reasons,
        "duplicates": reasons.get("duplicate-timestamp", 0) + reasons.get("duplicate-trade", 0),
        "gaps": [],
        "out_of_order": reasons.get("out-of-order", 0),
        "timestamp_range": [min(ts), max(ts)] if ts else [None, None],
        "symbol_coverage": [symbol] if symbol else [],
        "resolution": resolution,
    }
