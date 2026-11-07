"""Opt-in order-lifecycle instrumentation for the frozen OOS executor.

Phase 26 observability: the certified Phase-18 funnel records terminal
counts only, so a zero-fill outcome cannot be explained from the
persisted artifact. This module attaches a temporary root-log capture
around the frozen run and serializes every order with the lifecycle
events the frozen backtester already emits. It never changes execution
semantics: the capture is passive, the order registry is read after the
run, and nothing is written to disk here.

The tracer is deliberately research-only and only active when a caller
passes an ``order_trace`` sink to ``run_frozen_oos``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Mapping, Sequence

_LIFECYCLE_VERBS = frozenset({
    "ORDER_CREATED",
    "EXECUTION_SIGNAL",
    "BREAKOUT_TRIGGER",
    "BREAKOUT_ENTRY",
    "ORDER_SKIPPED_RR_EROSION",
    "ORDER_SKIPPED_INVERTED_FILL",
    "ORDER_INVALIDATED",
    "ORDER_EXPIRED",
})

_KEY_VALUE_SPLIT = re.compile(r"\s+(?=[a-z_]+=)")
_NUMERIC_FIELDS = frozenset({
    "bar", "created_bar", "eligible_from_bar", "expired_bar",
    "invalidated_bar", "waited_bars", "max_wait_bars", "bars_pending",
    "direction", "entry", "entry_level", "stop", "target", "close",
    "actual_rr", "min_rr", "max_rr", "rr", "score", "comm", "slip",
    "price", "invalidation_level", "min_low_since_creation",
    "max_high_since_creation", "entry_distance_from_nearest_price",
})

_INT_FIELDS = frozenset({
    "bar", "created_bar", "eligible_from_bar", "expired_bar",
    "invalidated_bar", "waited_bars", "max_wait_bars", "bars_pending",
})

_CONFIDENCE = {
    "FILLED": 1.0,
    "TRIGGERED_REJECTED_RR_EROSION": 1.0,
    "TRIGGERED_REJECTED_RR_EROSION_THEN_INVALIDATED": 1.0,
    "TRIGGERED_REJECTED_FILL_BEYOND_STOP": 1.0,
    "TRIGGERED_REJECTED_FILL_BEYOND_STOP_THEN_INVALIDATED": 1.0,
    "TRIGGERED_REJECTED_FILL_BEYOND_TARGET": 1.0,
    "TRIGGERED_REJECTED_FILL_BEYOND_TARGET_THEN_INVALIDATED": 1.0,
    "TRIGGERED_REJECTED_INVALID_GEOMETRY": 0.75,
    "INVALIDATED_BEFORE_TRIGGER": 1.0,
    "EXPIRED_WITHOUT_TRIGGER": 1.0,
    "STILL_PENDING": 1.0,
    "TRIGGERED_UNFILLED_UNCLASSIFIED": 0.5,
    "UNCLASSIFIED": 0.0,
}


class _CollectingHandler(logging.Handler):
    def __init__(self, sink: list[str]) -> None:
        super().__init__(level=logging.NOTSET)
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._sink.append(record.getMessage())
        except Exception:  # noqa: BLE001 - passive capture must not raise
            pass


class LogCapture:
    """Temporarily capture INFO+ records emitted during a frozen run."""

    def __init__(self) -> None:
        self.messages: list[str] = []
        self._handler: _CollectingHandler | None = None
        self._previous_level: int | None = None

    def start(self) -> "LogCapture":
        root = logging.getLogger()
        self._previous_level = root.level
        if root.level == logging.NOTSET or root.level > logging.INFO:
            root.setLevel(logging.INFO)
        self._handler = _CollectingHandler(self.messages)
        root.addHandler(self._handler)
        return self

    def stop(self) -> list[str]:
        root = logging.getLogger()
        if self._handler is not None:
            root.removeHandler(self._handler)
            self._handler = None
        if self._previous_level is not None:
            root.setLevel(self._previous_level)
            self._previous_level = None
        return list(self.messages)


def _coerce(field: str, value: str) -> Any:
    if field in _INT_FIELDS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if field in _NUMERIC_FIELDS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


def parse_lifecycle_event(message: str) -> dict[str, Any] | None:
    """Parse one frozen-backtester lifecycle log line into a record."""
    if not isinstance(message, str):
        return None
    verb, separator, rest = message.partition(" ")
    if not separator or verb not in _LIFECYCLE_VERBS:
        return None
    fields: dict[str, Any] = {}
    for chunk in _KEY_VALUE_SPLIT.split(rest):
        key, equals, value = chunk.partition("=")
        if not equals or not key:
            continue
        fields[key] = _coerce(key, value)
    return {"verb": verb, "fields": fields}


def _index_events(messages: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for message in messages:
        event = parse_lifecycle_event(message)
        if event is None:
            continue
        order_id = event["fields"].get("order_id")
        if not isinstance(order_id, str) or not order_id:
            continue
        indexed.setdefault(order_id, []).append(event)
    return indexed


def _first(events: Sequence[Mapping[str, Any]], verb: str) -> Mapping[str, Any] | None:
    for event in events:
        if event.get("verb") == verb:
            return event
    return None


def _progress_fraction(direction: str, reference: float, entry: float,
                       target: float) -> float | None:
    span = target - entry
    if span == 0.0 or reference is None:
        return None
    fraction = (reference - entry) / span
    return max(0.0, min(1.0, abs(fraction)))


def classify_order(status: str, verbs: Sequence[str],
                   geometry_at_attempt: str | None = None) -> str:
    """Assign a terminal lifecycle classification from status + events."""
    verb_set = set(verbs)
    triggered = "BREAKOUT_TRIGGER" in verb_set
    erosion = "ORDER_SKIPPED_RR_EROSION" in verb_set
    geometry_refused = "ORDER_SKIPPED_INVERTED_FILL" in verb_set
    status = (status or "").upper()
    invalidated = status == "INVALIDATED"
    suffix = "_THEN_INVALIDATED" if invalidated else ""

    if status == "FILLED":
        return "FILLED"
    if geometry_refused:
        if geometry_at_attempt == "BEYOND_STOP":
            base = "TRIGGERED_REJECTED_FILL_BEYOND_STOP"
        elif geometry_at_attempt == "BEYOND_TARGET":
            base = "TRIGGERED_REJECTED_FILL_BEYOND_TARGET"
        else:
            base = "TRIGGERED_REJECTED_INVALID_GEOMETRY"
        return (base + suffix) if triggered else "TRIGGERED_UNFILLED_UNCLASSIFIED"
    if erosion:
        return "TRIGGERED_REJECTED_RR_EROSION" + suffix
    if status == "INVALIDATED":
        return "INVALIDATED_BEFORE_TRIGGER" if not triggered else \
            "TRIGGERED_UNFILLED_UNCLASSIFIED"
    if status == "EXPIRED":
        return "EXPIRED_WITHOUT_TRIGGER" if not triggered else \
            "TRIGGERED_UNFILLED_UNCLASSIFIED"
    if status == "PENDING":
        return "STILL_PENDING"
    return "UNCLASSIFIED"


def _geometry_side(direction: str, entry: float, stop: float,
                   target: float) -> str:
    """Classify an executable entry against FIXED_TARGET geometry."""
    side = (direction or "").upper()
    try:
        entry_f, stop_f, target_f = float(entry), float(stop), float(target)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if side == "BULLISH":
        if entry_f <= stop_f:
            return "BEYOND_STOP"
        if entry_f >= target_f:
            return "BEYOND_TARGET"
        return "VALID"
    if side == "BEARISH":
        if entry_f >= stop_f:
            return "BEYOND_STOP"
        if entry_f <= target_f:
            return "BEYOND_TARGET"
        return "VALID"
    return "UNKNOWN"


def build_order_records(raw_orders: Iterable[Any], messages: Iterable[str],
                        rows_asc: Sequence[Mapping[str, Any]], *,
                        symbol: str = "BTCUSDT",
                        timeframe: str = "1m") -> list[dict[str, Any]]:
    """Serialize every frozen order with its lifecycle evidence."""
    from core.backtesting.accounting import order_rr, realized_rr

    rows = list(rows_asc)
    indexed = _index_events(messages)
    records: list[dict[str, Any]] = []

    for order in raw_orders:
        order_id = str(getattr(order, "order_id", "") or "")
        events = indexed.get(order_id, [])
        verbs = [event["verb"] for event in events]

        direction = str(getattr(order, "direction", "") or "")
        entry = float(getattr(order, "entry", 0.0) or 0.0)
        stop = float(getattr(order, "stop_loss", 0.0) or 0.0)
        target = float(getattr(order, "take_profit", 0.0) or 0.0)
        status = str(getattr(order, "status", "") or "")

        trigger = _first(events, "BREAKOUT_TRIGGER")
        erosion = _first(events, "ORDER_SKIPPED_RR_EROSION")
        inverted = _first(events, "ORDER_SKIPPED_INVERTED_FILL")
        entry_event = _first(events, "BREAKOUT_ENTRY")
        expired = _first(events, "ORDER_EXPIRED")
        invalidated = _first(events, "ORDER_INVALIDATED")

        trigger_bar = getattr(order, "breakout_trigger_bar", None)
        trigger_close = getattr(order, "breakout_trigger_close", None)
        if trigger is not None:
            trigger_bar = trigger["fields"].get("bar", trigger_bar)
            trigger_close = trigger["fields"].get("close", trigger_close)
        trigger_bar = int(trigger_bar) if trigger_bar is not None else None
        trigger_close = float(trigger_close) if trigger_close is not None else None

        # The frozen pipeline's ``bar`` domain is 1-based relative to the
        # run: PipelineContext.add_candle increments replay_index on the
        # candle currently being processed. The trigger candle therefore
        # has row index ``trigger_bar - 1`` and the NEXT candle (whose open
        # is the RULE-3 fill price) has row index ``trigger_bar``.
        trigger_candle_index = (
            trigger_bar - 1 if trigger_bar is not None else None)
        attempt_candle_index = trigger_bar
        attempt_bar = trigger_bar + 1 if trigger_bar is not None else None
        attempt_open = None
        trigger_close_row = None
        trigger_close_consistency = None
        if attempt_candle_index is not None and 0 <= attempt_candle_index < len(rows):
            attempt_open = float(rows[attempt_candle_index]["open"])
        if trigger_candle_index is not None and 0 <= trigger_candle_index < len(rows):
            trigger_close_row = float(rows[trigger_candle_index]["close"])
            if trigger_close is not None:
                trigger_close_consistency = (
                    abs(trigger_close - trigger_close_row) <= 1e-9)

        inverted_entry = None
        if inverted is not None:
            value = inverted["fields"].get("entry")
            if isinstance(value, (int, float)):
                inverted_entry = float(value)

        erosion_rr = None
        if erosion is not None:
            value = erosion["fields"].get("actual_rr")
            if isinstance(value, (int, float)):
                erosion_rr = float(value)

        geometry_at_attempt = None
        if attempt_open is not None:
            geometry_at_attempt = _geometry_side(
                direction, attempt_open, stop, target)

        rr_at_trigger_close = (
            realized_rr(direction, trigger_close, stop, target)
            if trigger_close is not None else None)
        rr_at_attempt_open = (
            realized_rr(direction, attempt_open, stop, target)
            if attempt_open is not None else None)

        rr_consistency = None
        if erosion_rr is not None and rr_at_attempt_open is not None:
            rr_consistency = abs(erosion_rr - rr_at_attempt_open) <= 1e-9
        if inverted_entry is not None and attempt_open is not None:
            inverted_consistency = abs(inverted_entry - attempt_open) <= 1e-9
        else:
            inverted_consistency = None

        classification = classify_order(status, verbs, geometry_at_attempt)
        record = {
            "order_id": order_id,
            "setup_id": str(getattr(order, "setup_id", "") or ""),
            "canonical_id": str(getattr(order, "canonical_id", "") or ""),
            "symbol": str(getattr(order, "symbol", "") or symbol),
            "timeframe": str(getattr(order, "timeframe", "") or timeframe),
            "direction": direction,
            "entry_mode": str(getattr(order, "entry_mode", "") or ""),
            "entry_execution": str(getattr(order, "entry_execution", "") or ""),
            "status": status,
            "classification": classification,
            "confidence": _CONFIDENCE.get(classification, 0.0),
            "status_consistent": bool(status) and status.upper() in {
                "FILLED", "EXPIRED", "INVALIDATED", "PENDING",
            },
            "created_bar": getattr(order, "created_bar", None),
            "eligible_from_bar": getattr(order, "eligible_from_bar", None),
            "trigger_bar": trigger_bar,
            "trigger_candle_index": trigger_candle_index,
            "attempt_bar": attempt_bar,
            "attempt_candle_index": attempt_candle_index,
            "terminal_bar": getattr(order, "terminal_bar", None),
            "waited_bars": getattr(order, "waited_bars", None),
            "entry_level": entry,
            "stop_loss": stop,
            "take_profit": target,
            "theoretical_risk_reward": getattr(order, "risk_reward", None),
            "theoretical_rr_recomputed": order_rr(entry, stop, target),
            "actual_risk_reward": getattr(order, "actual_risk_reward", None),
            "trigger_close": trigger_close,
            "trigger_close_row": trigger_close_row,
            "trigger_close_consistency": trigger_close_consistency,
            "attempt_open": attempt_open,
            "fill_geometry_at_attempt": geometry_at_attempt,
            "inverted_fill_entry": inverted_entry,
            "erosion_actual_rr": erosion_rr,
            "rr_at_trigger_close": rr_at_trigger_close,
            "rr_at_attempt_open": rr_at_attempt_open,
            "rr_consistency": rr_consistency,
            "inverted_entry_consistency": inverted_consistency,
            "trigger_close_progress_fraction": (
                _progress_fraction(direction, trigger_close, entry, target)
                if trigger_close is not None else None),
            "adverse_open_risk_multiple": (
                abs(attempt_open - entry) / abs(entry - stop)
                if attempt_open is not None and stop != entry else None),
            "trigger_entry_distance": (
                abs(trigger_close - entry) if trigger_close is not None else None),
            "quantity": getattr(order, "quantity", None),
            "risk_amount": getattr(order, "risk_amount", None),
            "score": getattr(order, "score", None),
            "expired_evidence": (
                {k: expired["fields"].get(k) for k in (
                    "created_bar", "eligible_from_bar", "expired_bar",
                    "waited_bars", "max_wait_bars",
                    "min_low_since_creation", "max_high_since_creation",
                    "bars_pending", "entry_distance_from_nearest_price")}
                if expired is not None else None),
            "invalidation_evidence": (
                {k: invalidated["fields"].get(k) for k in (
                    "created_bar", "eligible_from_bar", "invalidated_bar",
                    "reason", "price", "invalidation_level")}
                if invalidated is not None else None),
            "lifecycle_verbs": verbs,
            "events": [
                {"verb": event["verb"], "fields": event["fields"]}
                for event in events
            ],
            "evidence_refs": [
                "core/research/oos_validation/execution.py:run_frozen_oos",
                "backtesting/backtester.py:839-1088 (breakout trigger/fill)",
                "backtesting/backtester.py:777-837 (invalidation)",
                "backtesting/backtester.py:353 (expiry)",
            ],
        }
        records.append(record)

    records.sort(key=lambda item: (
        item["created_bar"] if item["created_bar"] is not None else -1,
        item["order_id"],
    ))
    return records


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def summarize_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate the lifecycle evidence without inventing any outcome."""
    def values(key: str) -> list[float]:
        return [float(record[key]) for record in records
                if isinstance(record.get(key), (int, float))]

    statuses: dict[str, int] = {}
    classifications: dict[str, int] = {}
    directions: dict[str, int] = {}
    for record in records:
        status = str(record.get("status") or "")
        classification = str(record.get("classification") or "")
        direction = str(record.get("direction") or "")
        statuses[status] = statuses.get(status, 0) + 1
        classifications[classification] = classifications.get(classification, 0) + 1
        directions[direction] = directions.get(direction, 0) + 1

    theoretical = values("theoretical_rr_recomputed")
    at_attempt = values("rr_at_attempt_open")
    erosion = values("erosion_actual_rr")
    progress = values("trigger_close_progress_fraction")
    adverse = values("adverse_open_risk_multiple")

    consistency_checked = [record for record in records
                           if record.get("rr_consistency") is not None]
    consistency_ok = [record for record in consistency_checked
                      if record.get("rr_consistency") is True]
    trigger_checked = [record for record in records
                       if record.get("trigger_close_consistency") is not None]
    trigger_ok = [record for record in trigger_checked
                  if record.get("trigger_close_consistency") is True]

    return {
        "orders": len(records),
        "statuses": dict(sorted(statuses.items())),
        "classifications": dict(sorted(classifications.items())),
        "directions": dict(sorted(directions.items())),
        "triggered_orders": sum(
            1 for record in records
            if record.get("trigger_bar") is not None),
        "fill_attempts": sum(
            1 for record in records
            if "ORDER_SKIPPED_RR_EROSION" in record.get("lifecycle_verbs", ())
            or "ORDER_SKIPPED_INVERTED_FILL" in record.get("lifecycle_verbs", ())),
        "rr_erosion_skips": sum(
            1 for record in records
            if "ORDER_SKIPPED_RR_EROSION" in record.get("lifecycle_verbs", ())),
        "inverted_fill_skips": sum(
            1 for record in records
            if "ORDER_SKIPPED_INVERTED_FILL" in record.get("lifecycle_verbs", ())),
        "geometry_rejections": {
            "beyond_stop": sum(
                1 for record in records
                if record.get("fill_geometry_at_attempt") == "BEYOND_STOP"),
            "beyond_target": sum(
                1 for record in records
                if record.get("fill_geometry_at_attempt") == "BEYOND_TARGET"),
        },
        "erosion_rr_consistency": {
            "checked": len(consistency_checked),
            "consistent": len(consistency_ok),
            "all_consistent": len(consistency_checked) == len(consistency_ok),
        },
        "trigger_close_consistency": {
            "checked": len(trigger_checked),
            "consistent": len(trigger_ok),
            "all_consistent": len(trigger_checked) == len(trigger_ok),
        },
        "theoretical_rr": {
            "min": min(theoretical) if theoretical else None,
            "median": _median(theoretical),
            "max": max(theoretical) if theoretical else None,
        },
        "rr_at_attempt_open": {
            "count": len(at_attempt),
            "min": min(at_attempt) if at_attempt else None,
            "median": _median(at_attempt),
            "max": max(at_attempt) if at_attempt else None,
        },
        "erosion_actual_rr": {
            "count": len(erosion),
            "min": min(erosion) if erosion else None,
            "median": _median(erosion),
            "max": max(erosion) if erosion else None,
        },
        "trigger_close_progress_fraction": {
            "count": len(progress),
            "min": min(progress) if progress else None,
            "median": _median(progress),
            "max": max(progress) if progress else None,
        },
        "adverse_open_risk_multiple": {
            "count": len(adverse),
            "min": min(adverse) if adverse else None,
            "median": _median(adverse),
            "max": max(adverse) if adverse else None,
        },
        "records_missing_trigger_evidence": [
            record["order_id"] for record in records
            if record.get("status") in ("EXPIRED", "INVALIDATED")
            and record.get("trigger_bar") is None
        ],
        "records_missing_attempt_price": [
            record["order_id"] for record in records
            if record.get("trigger_bar") is not None
            and record.get("attempt_open") is None
        ],
        "unknown_classifications": [
            record["order_id"] for record in records
            if record.get("classification") in
            ("UNCLASSIFIED", "TRIGGERED_UNFILLED_UNCLASSIFIED")
        ],
    }
