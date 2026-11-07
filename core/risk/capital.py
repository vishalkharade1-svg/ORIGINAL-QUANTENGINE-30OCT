"""
====================================================

QuantEngine

Shared Portfolio Capital (Phase 8B)

A single piece of shared, reservation-based capital state
that coordinates how much capital is available to the whole
portfolio versus how much is already RESERVED by open
(accepted) positions, across every symbol.

Conceptually:

                    Portfolio
                       |
          +------------+------------+
          v            v            v
       Equity     Available     Reserved
                   Capital      Capital

    equity            = basis + realized PnL (the whole account)
    reserved_capital  = capital already committed to open positions
    available_capital = allocatable equity still free to deploy

The cardinal invariant carried forward from Phase 8 holds
here too: these are BOOKKEEPING primitives. `can_reserve()`
is a PURE DECISION (it inspects state and returns a bool,
never mutates); `reserve()` / `release()` / `cancel()` are
bookkeeping that moves capital between the three buckets.
Nothing here touches an order / setup / strategy -- this is
the capital envelope the allocator (allocator.py) draws
against.

DISABLED-BY-DEFAULT / DEFAULT NEUTRALITY: with no explicit
equity basis (equity = 0) and no reservation, available
capital is 0 and the state is inert until a basis is
injected. Adding this layer changes nothing about a default
run unless an equity basis is provided.
====================================================
"""


def _fnum(value):
    try:
        return float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0


class SharedCapital:
    """Reservation-based shared capital envelope.

    equity      = starting basis + realized PnL
    reserved    = capital committed to open (accepted) positions
    available   = allocatable equity not yet reserved

    Buckets are reconciled from a single reservations ledger, so
    there is exactly one source of truth: reserved_capital is the
    sum of every live reservation, and available_capital is the
    residual of equity. Releasing / cancelling a reservation
    returns its capital to the available pool.
    """

    def __init__(self, equity=None, max_deployment_pct=100.0):

        # Starting equity basis; None => a running realized-PnL
        # basis (inert until a trade realizes PnL).
        self._equity_basis = _fnum(equity) if equity is not None else None

        # Max fraction of equity that may be deployed at once.
        # 0/None = 100% (no binding). Expressed as a percent value.
        self._max_deployment_pct = _fnum(max_deployment_pct)

        # {reservation_id: {"capital": float}}
        self.reservations = {}

        self.realized_pnl = 0.0

        self.last_reason = ""

    # --------------------------------------------------
    # Equity / capacity
    # --------------------------------------------------

    @property
    def equity(self):
        if self._equity_basis is not None:
            return self._equity_basis + self.realized_pnl
        return self.realized_pnl

    @property
    def deployment_cap(self):
        return self.equity * (self._max_deployment_pct / 100.0)

    @property
    def reserved_capital(self):
        return sum(r["capital"] for r in self.reservations.values())

    @property
    def available_capital(self):
        return max(0.0, self.deployment_cap - self.reserved_capital)

    @property
    def open_reservations(self):
        return len(self.reservations)

    # --------------------------------------------------
    # Pure decision (GATES, never mutates)
    # --------------------------------------------------

    def can_reserve(self, amount):
        """May `amount` of capital be reserved right now?

        Pure decision -- consults current available_capital, sets
        `last_reason` on a False verdict, returns a bool. Never
        mutates state."""

        self.last_reason = ""

        amt = _fnum(amount)

        if amt > self.available_capital:
            self.last_reason = "insufficient_capital"
            return False

        return True

    # --------------------------------------------------
    # Bookkeeping (never strategy)
    # --------------------------------------------------

    def reserve(self, reservation_id, amount):
        """Commit `amount` of capital to a reservation id.

        Assumes can_reserve() already returned True for this
        amount (the allocator gates first). Bookkeeping only."""

        rid = str(reservation_id)

        if rid in self.reservations:
            self.last_reason = "duplicate_reservation"
            return False

        self.reservations[rid] = {"capital": _fnum(amount)}

        return True

    def release(self, reservation_id, pnl=0.0):
        """Release a reservation, returning its capital to the
        available pool and folding realized PnL into equity.

        Bookkeeping only. Idempotent on an unknown id."""

        rid = str(reservation_id)

        self.reservations.pop(rid, None)

        p = _fnum(pnl)

        if p != 0.0:
            self.realized_pnl += p

    def cancel(self, reservation_id):
        """Cancel a reservation after a failed execution -- the
        capital is returned with NO realized PnL.

        Bookkeeping only. This is the "failed execution after
        reservation" path: the reservation never converts into an
        open position's capital, so it must not be treated as a
        drawdown / won't consume available capital."""

        self.release(reservation_id, pnl=0.0)

    # --------------------------------------------------

    def snapshot(self):
        return {
            "equity": self.equity,
            "deployment_cap": self.deployment_cap,
            "reserved_capital": self.reserved_capital,
            "available_capital": self.available_capital,
            "open_reservations": self.open_reservations,
            "realized_pnl": self.realized_pnl,
            "last_reason": self.last_reason,
        }

    def reset(self):
        """Fresh session: clear all reservations and realized PnL."""

        self.reservations = {}

        self.realized_pnl = 0.0

        self.last_reason = ""
