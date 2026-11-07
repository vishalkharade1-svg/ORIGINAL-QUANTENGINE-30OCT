"""
====================================================

QuantEngine

Research Journal -- enums (Phase 9A)

Centralised enumerations for the causal research journal.
All values are stable string contracts so records survive
serialisation and are queryable by exact string.

Intent of the enum split (carried forward): SEPARATE
concepts that the engine itself distinguishes --

   * setup eligibility   (is this discovered setup eligible?)
   * order lifecycle     (a created order's status path)

A setup may be DISCOVERED -> REJECTED without ever creating
an order; an order may be CREATED -> EXPIRED without filling;
a filled order may be FILLED -> CLOSED. These are NOT forced
into one field.
====================================================
"""

from enum import Enum


class Provenance(str, Enum):
    """Where an observation was recorded. Explicit, never
    inferred from filenames or runtime environment."""

    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class SetupLifecycle(str, Enum):
    """Setup-level lifecycle (mirrors SetupCandidate.lifecycle
    values: NEW / ACCEPTED / ORDER_CREATED / FILLED / CLOSED /
    INVALIDATED / EXPIRED)."""

    DISCOVERED = "DISCOVERED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ORDER_CREATED = "ORDER_CREATED"
    PENDING = "PENDING"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    CLOSED = "CLOSED"


class OrderLifecycle(str, Enum):
    """Order-status lifecycle (mirrors OrderRegistry status
    constants: PENDING / FILLED / REJECTED / EXPIRED /
    INVALIDATED / CANCELLED)."""

    CREATED = "CREATED"
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    CANCELLED = "CANCELLED"


class Result(str, Enum):
    """Terminal trade outcome. WIN / LOSS follow the canonical
    Trade.result ("WIN" / "LOSS"); UNSETTLED marks a trade that
    did not reach a terminal outcome."""

    WIN = "WIN"
    LOSS = "LOSS"
    UNSETTLED = "UNSETTLED"


class EntryReached(str, Enum):
    """Factual answer to "did the market reach the entry level
    for this opportunity?" -- independent of whether an order
    actually existed to be filled."""

    REACHED = "REACHED"
    NOT_REACHED = "NOT_REACHED"


class EventType(str, Enum):
    """Research event stream types."""

    SETUP_DISCOVERED = "SETUP_DISCOVERED"
    SETUP_ACCEPTED = "SETUP_ACCEPTED"
    SETUP_REJECTED = "SETUP_REJECTED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_PENDING = "ORDER_PENDING"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_EXPIRED = "ORDER_EXPIRED"
    ORDER_INVALIDATED = "ORDER_INVALIDATED"
    ORDER_REJECTED = "ORDER_REJECTED"
    TRADE_OPENED = "TRADE_OPENED"
    TRADE_CLOSED = "TRADE_CLOSED"
