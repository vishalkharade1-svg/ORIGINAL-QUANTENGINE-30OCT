"""Live position/order reconciliation (fail-closed, never auto-trades).

Compares the engine's local mirror against exchange authority and
HALTS new orders on any unexplained divergence. The reconciler never
places, amends, cancels, or closes anything: mismatch → halt +
record, and an explicit operator resolution is required to resume.

Verdicts: MATCH, IN_FLIGHT (transient, documented), MISMATCH (halt),
UNKNOWN (executor failure → halt, fail-closed), SKIP (paper/dry-run:
no exchange authority exists to compare against).

Drift kinds: UNEXPECTED_POSITION, MISSING_POSITION, QTY_MISMATCH
(includes partial fills: same side, smaller exchange size),
SIDE_MISMATCH, ENTRY_MISMATCH, ORDER_LOST, STALE_SNAPSHOT,
NO_SNAPSHOT, EXECUTOR_ERROR.

Snapshot persistence is atomic (tmp + os.replace) and best-effort:
a missing/corrupt snapshot degrades to NO_SNAPSHOT/STALE_SNAPSHOT
handling, never a crash. Halt state itself is NOT persisted — every
boot re-derives it from a fresh startup check.
"""

from __future__ import annotations

import json
import math
import os
import tempfile

from core.common.logging_config import get_logger

log = get_logger(__name__)

MATCH = "MATCH"
IN_FLIGHT = "IN_FLIGHT"
MISMATCH = "MISMATCH"
UNKNOWN = "UNKNOWN"
SKIP = "SKIP"

# Local order states that may legitimately precede an exchange
# position (route happened, fill not yet observable).
TRANSIT_ORDER_STATES = ("NEW", "PENDING", "ACKNOWLEDGED", "PARTIAL")

# A routed order older than this (bars) with no exchange position
# and no observable order is lost, not in flight.
DEFAULT_MAX_TRANSIT_BARS = 30


def _num(value, default=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out or out in (math.inf, -math.inf):
        return default
    return out


def _side_of(record):
    for key in ("side", "direction"):
        raw = record.get(key) if isinstance(record, dict) else getattr(
            record, key, None)
        if raw is not None:
            text = str(raw).upper()
            if "LONG" in text or text in ("BUY", "BULLISH", "B"):
                return "LONG"
            if "SHORT" in text or text in ("SELL", "BEARISH", "S"):
                return "SHORT"
            return text
    return None


def _qty_of(record):
    if isinstance(record, dict):
        raw = record.get("size", record.get("quantity", 0.0))
    else:
        raw = getattr(record, "size", getattr(record, "quantity", 0.0))
    return _num(raw, 0.0)


def _entry_of(record):
    if isinstance(record, dict):
        raw = record.get("entry", record.get("entry_price",
                         record.get("average_entry", record.get("avg_price"))))
    else:
        raw = getattr(record, "entry", getattr(
            record, "entry_price", getattr(record, "average_entry", None)))
    return _num(raw)


class Reconciler:
    """Fail-closed local-vs-exchange comparator with snapshot journal."""

    def __init__(self, executor=None, snapshot_path=None,
                 check_interval_bars=30,
                 max_transit_bars=DEFAULT_MAX_TRANSIT_BARS,
                 entry_tolerance=1e-6):
        self.executor = executor
        self.snapshot_path = snapshot_path
        self.check_interval_bars = max(1, int(check_interval_bars))
        self.max_transit_bars = max(0, int(max_transit_bars))
        self.entry_tolerance = float(entry_tolerance)
        self.halt_new_orders = False
        self.halt_reason = ""
        self.drifts = []
        self.resolutions = []
        self.checks_run = 0

    # --------------------------------------------------
    # Snapshot journal (atomic, best-effort)
    # --------------------------------------------------

    def snapshot_state(self, in_position, open_order_id, product_id,
                       live_trade, timestamp, ack_state=None,
                       order_seq=None):
        # Phase 12: the journal also records the acknowledgement
        # truth (ACKNOWLEDGED vs FILLED vs ...) and the
        # deterministic order-sequence counter so a restart can
        # resume both without reusing client order ids. Additive
        # keys only -- existing v1 readers keep working.
        trade = None
        if live_trade is not None:
            trade = {
                "direction": getattr(live_trade, "direction", None),
                "entry": getattr(live_trade, "entry", None),
                "stop_loss": getattr(live_trade, "stop_loss", None),
                "take_profit": getattr(live_trade, "take_profit", None),
                "quantity": getattr(live_trade, "quantity", None),
                "entry_time": getattr(live_trade, "entry_time", None),
            }
        return {"schema": "broker-snapshot-v1",
                "in_position": bool(in_position),
                "open_order_id": open_order_id,
                "product_id": product_id,
                "live_trade": trade,
                "timestamp": timestamp,
                "ack_state": ack_state,
                "order_seq": order_seq}

    def persist(self, state):
        if not self.snapshot_path:
            return False
        try:
            directory = os.path.dirname(self.snapshot_path) or "."
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps(state, sort_keys=True))
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            os.replace(tmp, self.snapshot_path)
            return True
        except Exception as exc:  # noqa: BLE001 (best-effort journal)
            log.error("Reconciler snapshot persist failed: %s", exc)
            return False

    def load_snapshot(self):
        if not self.snapshot_path:
            return None
        try:
            with open(self.snapshot_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (OSError, ValueError) as exc:
            log.error("Reconciler snapshot unreadable: %s", exc)
            return None
        if not isinstance(state, dict) or state.get("schema") != "broker-snapshot-v1":
            log.error("Reconciler snapshot schema mismatch")
            return None
        return state

    def clear_snapshot(self):
        if not self.snapshot_path:
            return False
        try:
            os.remove(self.snapshot_path)
            return True
        except OSError:
            return False

    # --------------------------------------------------
    # Halt / resolve
    # --------------------------------------------------

    def _halt(self, reason, drift=None):
        self.halt_new_orders = True
        self.halt_reason = reason
        if drift is not None:
            self.drifts.append(drift)
        log.error("RECONCILE_HALT reason=%s", reason)
        return {"verdict": MISMATCH, "reason": reason, "drift": drift}

    def resolve(self, operator_note):
        """Explicit operator resolution: clears the halt, records why."""
        note = str(operator_note or "").strip()
        if not note:
            raise ValueError("resolve requires a non-empty operator note")
        self.resolutions.append({"note": note, "prior_reason": self.halt_reason})
        log.info("RECONCILE_RESOLVED note=%s prior=%s", note, self.halt_reason)
        self.halt_new_orders = False
        self.halt_reason = ""
        return True

    # --------------------------------------------------
    # Exchange reads (tolerant interface probing)
    # --------------------------------------------------

    @staticmethod
    def _unwrap(records):
        # Tolerate live transport shapes: a bare record, a list of
        # records, or a Delta {"result": [...]} envelope (the same
        # envelope BrokerEngine._sync_live unwraps). Anything
        # unreadable degrades to [] (flat) — never a crash; a
        # genuinely diverged exchange then halts via comparison.
        if records is None:
            return []
        if isinstance(records, dict):
            for key in ("result", "data", "positions", "orders"):
                nested = records.get(key)
                if isinstance(nested, (list, tuple)):
                    return list(nested)
                if isinstance(nested, dict):
                    return [nested]
            return [records]
        try:
            return list(records)
        except TypeError:
            return [records]

    def _exchange_positions(self):
        if self.executor is None:
            return None
        fetch = getattr(self.executor, "positions", None)
        if not callable(fetch):
            return None
        try:
            records = fetch()
        except Exception:
            raise
        if records is None:
            return []
        return self._unwrap(records)

    def _exchange_open_orders(self):
        if self.executor is None:
            return None
        fetch = getattr(self.executor, "open_orders", None)
        if not callable(fetch):
            return None
        try:
            records = fetch()
        except Exception:
            return None
        if records is None:
            return []
        return self._unwrap(records)

    @staticmethod
    def _working(records):
        return [r for r in (records or [])
                if abs(_qty_of(r) or 0.0) > 0]

    # --------------------------------------------------
    # Comparison core
    # --------------------------------------------------

    def _compare_position(self, local, exchange_records, local_order=None,
                          bar=0, timestamp=0):
        working = self._working(exchange_records)
        if local is None and not working:
            if self._in_transit(local_order):
                return {"verdict": IN_FLIGHT,
                        "reason": "routed order not yet an exchange position"}
            if local_order is not None:
                return self._halt(
                    "stale local order with no exchange position or order",
                    {"kind": "ORDER_LOST", "local_order": local_order,
                     "bar": bar, "timestamp": timestamp})
            return {"verdict": MATCH, "reason": "both flat"}
        if local is None and working:
            return self._halt(
                "unexpected exchange position while local flat",
                {"kind": "UNEXPECTED_POSITION",
                 "exchange": [self._describe(r) for r in working],
                 "bar": bar, "timestamp": timestamp})
        if local is not None and not working:
            if self._in_transit(local_order):
                return {"verdict": IN_FLIGHT,
                        "reason": "routed order not yet an exchange position"}
            return self._halt(
                "local position missing on exchange",
                {"kind": "MISSING_POSITION", "local": self._describe(local),
                 "bar": bar, "timestamp": timestamp})
        other = working[0]
        lside, eside = _side_of(local), _side_of(other)
        if lside is not None and eside is not None and lside != eside:
            return self._halt(
                "position side mismatch",
                {"kind": "SIDE_MISMATCH", "local_side": lside,
                 "exchange_side": eside, "bar": bar, "timestamp": timestamp})
        lqty, eqty = abs(_qty_of(local) or 0.0), abs(_qty_of(other) or 0.0)
        if lqty != eqty:
            kind = ("PARTIAL_FILL_QTY" if lside == eside and 0 < eqty < lqty
                    else "QTY_MISMATCH")
            return self._halt(
                "position quantity mismatch",
                {"kind": kind, "local_quantity": lqty,
                 "exchange_quantity": eqty, "bar": bar,
                 "timestamp": timestamp})
        le, ee = _entry_of(local), _entry_of(other)
        if le is not None and ee is not None and le != 0:
            if abs(le - ee) > max(1e-8, abs(le) * self.entry_tolerance):
                return self._halt(
                    "position entry mismatch",
                    {"kind": "ENTRY_MISMATCH", "local_entry": le,
                     "exchange_entry": ee, "bar": bar,
                     "timestamp": timestamp})
        if len(working) > 1:
            return self._halt(
                "multiple exchange positions for one local mirror",
                {"kind": "EXTRA_POSITIONS",
                 "count": len(working), "bar": bar, "timestamp": timestamp})
        return {"verdict": MATCH, "reason": "position mirrors exchange"}

    def _in_transit(self, local_order):
        if local_order is None:
            return False
        if isinstance(local_order, dict):
            status = str(local_order.get("status", "")).upper()
            age = local_order.get("age_bars", 0)
        else:
            status = str(getattr(local_order, "status", "")).upper()
            age = getattr(local_order, "age_bars",
                          getattr(local_order, "bars_pending", 0)) or 0
        try:
            age = int(age)
        except (TypeError, ValueError):
            age = 0
        return status in TRANSIT_ORDER_STATES and age <= self.max_transit_bars

    @staticmethod
    def _describe(record):
        return {"side": _side_of(record), "quantity": _qty_of(record),
                "entry": _entry_of(record)}

    # --------------------------------------------------
    # Entry points
    # --------------------------------------------------

    def startup_check(self, dry_run, local_in_position=False,
                      local_open_order_id=None):
        """Boot-time gate. Paper/dry-run has no exchange authority: SKIP."""
        if dry_run:
            return {"verdict": SKIP, "reason": "paper mode has no exchange"}
        snapshot = self.load_snapshot()
        try:
            records = self._exchange_positions()
        except Exception as exc:  # noqa: BLE001 (fail closed)
            return self._halt("exchange positions unreadable at startup: %s" % exc,
                              {"kind": "EXECUTOR_ERROR"})
        if records is None:
            return self._halt("executor exposes no positions feed",
                              {"kind": "EXECUTOR_ERROR"})
        if snapshot is None:
            # Fresh boot with no journal: local is flat by construction.
            if local_in_position or local_open_order_id:
                return self._halt(
                    "local state without snapshot journal",
                    {"kind": "STALE_SNAPSHOT"})
            return self._compare_position(
                None, records, None, bar=0, timestamp=0)
        snap_pos = snapshot.get("live_trade") if snapshot.get("in_position") else None
        if snap_pos is not None:
            snap_pos = dict(snap_pos)
        return self._compare_position(snap_pos, records, None, bar=0,
                                      timestamp=snapshot.get("timestamp", 0))

    def runtime_check(self, bar, timestamp, local_position=None,
                      local_order=None):
        """Periodic in-session check (caller throttles by interval)."""
        self.checks_run += 1
        try:
            records = self._exchange_positions()
        except Exception as exc:  # noqa: BLE001 (fail closed)
            return self._halt("exchange positions unreadable: %s" % exc,
                              {"kind": "EXECUTOR_ERROR", "bar": bar,
                               "timestamp": timestamp})
        if records is None:
            return self._halt("executor exposes no positions feed",
                              {"kind": "EXECUTOR_ERROR", "bar": bar,
                               "timestamp": timestamp})
        return self._compare_position(local_position, records, local_order,
                                      bar=bar, timestamp=timestamp)
