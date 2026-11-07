"""
====================================================

QuantEngine

Order Acknowledgement Classification (Phase 12)

Interprets a raw exchange order acknowledgement into an
EXPLICIT lifecycle state. This module exists to enforce one
invariant:

    executor.execute() returning
        is NEVER equivalent to
    the exchange confirming FILLED.

Every classification is fail-closed: a missing,
unrecognized, or self-contradictory acknowledgement maps to
UNKNOWN (or PARTIAL when partial-fill evidence exists), and
UNKNOWN/PARTIAL must halt new routing until the reconciler
or an operator resolves the true exchange state. Nothing
here fabricates quantity or fill price.

States
------
ACKNOWLEDGED : the exchange accepted a working order
    (open / pending / new / working / live / active /
    placed). Fill evidence is still outstanding.
FILLED      : the exchange reports a terminal filled state
    WITH fill-quantity evidence (or an explicit filled /
    executed label). Only this state may mark FILLED.
PARTIAL     : partial-fill evidence (explicit partial label,
    or 0 < filled < total). Must NEVER become FILLED.
REJECTED    : rejected / failed / invalid.
CANCELLED   : cancelled / canceled.
EXPIRED     : expired.
UNKNOWN     : missing / unrecognized / contradictory
    acknowledgement. Fail closed (halt + resolve via fetch).

Determinism: pure functions of the response dict only. No
wall clock, no UUIDs, no randomness.

====================================================
"""

from __future__ import annotations


ACKNOWLEDGED = "ACKNOWLEDGED"
FILLED = "FILLED"
PARTIAL = "PARTIAL"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"
EXPIRED = "EXPIRED"
UNKNOWN = "UNKNOWN"

ACK_STATES = (
    ACKNOWLEDGED,
    FILLED,
    PARTIAL,
    REJECTED,
    CANCELLED,
    EXPIRED,
    UNKNOWN,
)

TERMINAL_STATES = (FILLED, PARTIAL, REJECTED, CANCELLED, EXPIRED)

# Venue status labels (lowercased, tolerant across venues).
_OPEN_LABELS = frozenset({
    "open",
    "pending",
    "new",
    "working",
    "live",
    "active",
    "placed",
    "untriggered",
    "accepted",
})

_FILLED_LABELS = frozenset({
    "filled",
    "fill",
    "executed",
})

# "closed"/"done"/"complete(d)" are terminal-sounding but do
# NOT prove a fill on every venue (a cancelled-without-fill
# order can also read "closed"): they require fill-quantity
# evidence, otherwise UNKNOWN.
_CLOSED_LABELS = frozenset({
    "closed",
    "done",
    "complete",
    "completed",
})

_PARTIAL_LABELS = frozenset({
    "partial",
    "partially_filled",
    "partially-filled",
    "partial_fill",
    "part_fill",
})

_REJECTED_LABELS = frozenset({
    "rejected",
    "failed",
    "invalid",
    "error",
})

_CANCELLED_LABELS = frozenset({
    "cancelled",
    "canceled",
})

_EXPIRED_LABELS = frozenset({
    "expired",
})

_QTY_EPS = 1e-9


def _unwrap(response):
    """Unwrap a Delta {"result": ...} envelope (one level)."""

    if isinstance(response, dict) and isinstance(
        response.get("result"), dict
    ):
        return response["result"]

    return response


def _first_present(record, keys):
    """First non-None value for any of `keys`, else None."""

    if not isinstance(record, dict):
        return None

    for key in keys:
        value = record.get(key)

        if value is not None:
            return value

    return None


def _finite_nonneg_number(value):
    """Finite float >= 0, else None (fail-closed parsing)."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:
        return None

    if number in (float("inf"), float("-inf")):
        return None

    if number < 0:
        return None

    return number


def _fill_quantities(record):
    """(filled_qty, total_qty) with None for unreadable legs."""

    filled = _finite_nonneg_number(
        _first_present(
            record,
            (
                "filled_size",
                "filled_quantity",
                "executed_qty",
                "executed_size",
                "cum_qty",
                "cum_quantity",
                "filled",
            ),
        )
    )

    total = _finite_nonneg_number(
        _first_present(
            record,
            (
                "size",
                "quantity",
                "order_size",
                "order_quantity",
                "orig_qty",
            ),
        )
    )

    return filled, total


class AckResult:
    """Immutable acknowledgement verdict (no wall clock)."""

    __slots__ = ("state", "status_raw", "filled_qty",
                 "total_qty", "detail")

    def __init__(self, state, status_raw="", filled_qty=None,
                 total_qty=None, detail=""):
        if state not in ACK_STATES:
            raise ValueError(
                f"unknown ack state {state!r}"
            )
        self.state = state
        self.status_raw = status_raw or ""
        self.filled_qty = filled_qty
        self.total_qty = total_qty
        self.detail = detail or ""

    def as_dict(self):
        return {
            "state": self.state,
            "status_raw": self.status_raw,
            "filled_qty": self.filled_qty,
            "total_qty": self.total_qty,
            "detail": self.detail,
        }

    def __repr__(self):  # pragma: no cover - debugging helper
        return (
            "AckResult(state=%r, status_raw=%r, "
            "filled_qty=%r, total_qty=%r, detail=%r)"
            % (
                self.state,
                self.status_raw,
                self.filled_qty,
                self.total_qty,
                self.detail,
            )
        )


def classify_ack(response):
    """Classify a raw place/fetch acknowledgement.

    Never raises on malformed input: anything unreadable is
    UNKNOWN. Never infers FILLED from a bare success flag --
    callers must pass the exchange's order record (the
    `response` payload), not the executor envelope.
    """

    record = _unwrap(response)

    if not isinstance(record, dict):
        return AckResult(
            UNKNOWN,
            status_raw="",
            detail="acknowledgement is not a mapping",
        )

    raw = _first_present(
        record, ("status", "state", "order_status")
    )

    label = str(raw).strip().lower() if raw is not None else ""

    filled, total = _fill_quantities(record)

    # ---- explicit terminal labels first -------------------

    if label in _REJECTED_LABELS:
        return AckResult(REJECTED, raw, filled, total,
                         detail="explicit rejected label")

    if label in _CANCELLED_LABELS:
        return AckResult(CANCELLED, raw, filled, total,
                         detail="explicit cancelled label")

    if label in _EXPIRED_LABELS:
        return AckResult(EXPIRED, raw, filled, total,
                         detail="explicit expired label")

    if label in _PARTIAL_LABELS:
        return AckResult(PARTIAL, raw, filled, total,
                         detail="explicit partial label")

    # ---- quantity evidence beats ambiguous labels ----------

    if filled is not None and total is not None and total > 0:
        if filled <= _QTY_EPS:
            # Zero fill: not evidence of anything yet. An
            # explicitly filled label with zero quantity is
            # contradictory -> UNKNOWN; otherwise fall through
            # to the label rules below.
            if label in _FILLED_LABELS or label in _CLOSED_LABELS:
                return AckResult(
                    UNKNOWN, raw, filled, total,
                    detail="filled label with zero fill quantity",
                )
        elif filled < total - _QTY_EPS:
            return AckResult(
                PARTIAL, raw, filled, total,
                detail="fill quantity below order quantity",
            )
        else:
            return AckResult(
                FILLED, raw, filled, total,
                detail="fill quantity covers order quantity",
            )

    if label in _FILLED_LABELS:
        # Explicit filled/executed label from the venue: the
        # exchange authority for the terminal state.
        return AckResult(FILLED, raw, filled, total,
                         detail="explicit filled label")

    if label in _CLOSED_LABELS:
        # Terminal-sounding but fill-unproven without quantity
        # evidence (a cancelled-without-fill order can also
        # read "closed" on some venues).
        return AckResult(
            UNKNOWN, raw, filled, total,
            detail="closed-like label without fill evidence",
        )

    if label in _OPEN_LABELS:
        return AckResult(ACKNOWLEDGED, raw, filled, total,
                         detail="explicit working label")

    if not label:
        return AckResult(
            UNKNOWN, raw, filled, total,
            detail="missing order status",
        )

    return AckResult(
        UNKNOWN, raw, filled, total,
        detail=f"unrecognized order status {raw!r}",
    )


def classify_exception(exc):
    """Map an executor exception to a typed UNKNOWN verdict.

    The message is truncated and never trusted as state: an
    exception means the exchange state is unproven, so the
    only safe classification is UNKNOWN (halt + resolve).
    """

    try:
        message = str(exc)[:200]
    except Exception:  # noqa: BLE001 (never fail the classifier)
        message = ""

    name = type(exc).__name__ if exc is not None else ""

    return AckResult(
        UNKNOWN,
        status_raw="",
        detail=f"executor exception {name}: {message}".strip(),
    )
