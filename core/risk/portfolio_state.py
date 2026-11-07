"""
====================================================

QuantEngine

Unified Portfolio State (Phase 8B)

A single, unified portfolio state that ties together:

    shared equity / available / reserved capital
                (capital.SharedCapital)
    portfolio risk budget      (max_portfolio_risk, absolute R)
    directional exposure       (per-direction % of equity on risk)
    correlated exposure        (per-group % of equity on risk)
    per-symbol capital         (absolute currency per symbol)
    total notional exposure    (% of equity on aggregate reserved
                               capital)

and owns the RESERVATION LEDGER -- the open positions the
portfolio has committed capital to, keyed by a reservation id
and carrying symbol / direction / correlation group / risk /
capital. This ledger IS the capital lifecycle:

    Candidate A --reserve--> A open
    Candidate B --reserve--> B open
    Candidate A --close / release--> A freed
    Candidate C --now allowed-->

Because a reservation only disappears when its trade CLOSES
(release) or its execution FAILS (cancel), capital is never
silently reused while a position is live.

THE INVARIANT (carried forward): `can_accept()` is a PURE
DECISION (inspects candidate + state, sets last_reason on a
False verdict, NEVER mutates); `reserve()` / `release()` /
`cancel()` are BOOKKEEPING. Nothing here changes an order /
setup / strategy. The allocator (allocator.py) is the only
caller that combines the pure decision with the bookkeeping.

DEFAULT NEUTRALITY: every cap is optional and disabled by
default (None / 0 = no binding); with no equity basis and no
caps the state is inert. Adding this layer changes nothing
about a default run unless caps are supplied.
====================================================
"""

from core.risk.capital import SharedCapital, _fnum


class CapitalCandidate:
    """A portfolio allocation candidate.

    Carries exactly what the state + allocator need to decide:
    symbol, direction, correlation group, the risk the position
    would consume (R), and the capital (position_value / notional)
    it would deploy. Constructible from primitives OR from an
    OrderIntent-like object via from_order().

    Pure data -- never mutated by the gate / allocator."""

    def __init__(self, symbol=None, direction=None,
                 correlation_group=None, risk=0.0, capital=0.0,
                 order=None):

        if order is not None:
            symbol = symbol or getattr(order, "symbol", None)
            direction = direction or getattr(order, "direction", None)
            risk = float(risk or 0.0)
            if risk <= 0:
                risk = float(
                    getattr(order, "risk_amount", 0.0) or 0.0
                )
                if risk <= 0:
                    risk = float(
                        getattr(order, "expected_loss", 0.0) or 0.0
                    )
            capital = float(capital or 0.0)
            if capital <= 0:
                capital = float(
                    getattr(order, "position_value", 0.0) or 0.0
                )

        self.symbol = symbol if symbol is not None else ""
        self.direction = (direction or "").upper()
        self.correlation_group = correlation_group or ""
        self.risk = _fnum(risk)
        self.capital = _fnum(capital)

    @classmethod
    def from_order(cls, order, correlation_group=None):
        return cls(order=order, correlation_group=correlation_group)

    def __repr__(self):
        d = self.direction or "?"
        return (
            f"CapitalCandidate(symbol={self.symbol!r} "
            f"direction={d} risk={self.risk} capital={self.capital})"
        )


class PortfolioState:
    """Unified portfolio state + reservation ledger."""

    def __init__(
        self,
        capital=None,
        equity=None,
        max_portfolio_risk=None,
        max_total_exposure_pct=None,
        max_per_symbol_capital=None,
        max_directional_risk_pct=None,
        max_correlated_risk_pct=None,
        correlation_groups=None,
    ):

        self.capital = (
            capital if capital is not None else SharedCapital(equity=equity)
        )

        # caps (None/0 = disabled = default neutral)
        self.max_portfolio_risk = _fnum(max_portfolio_risk)
        self.max_total_exposure_pct = _fnum(max_total_exposure_pct)
        self.max_per_symbol_capital = _fnum(max_per_symbol_capital)
        self.max_directional_risk_pct = _fnum(max_directional_risk_pct)
        self.max_correlated_risk_pct = _fnum(max_correlated_risk_pct)

        self.correlation_groups = dict(correlation_groups or {})

        # reservation ledger: rid -> {
        #   symbol, direction, group, risk, capital
        # }
        self.open = {}

        self.last_reason = ""

        self._seq = 0

    # --------------------------------------------------
    # Derived state
    # --------------------------------------------------

    @property
    def equity(self):
        return self.capital.equity

    @property
    def reserved_capital(self):
        return self.capital.reserved_capital

    @property
    def available_capital(self):
        return self.capital.available_capital

    @property
    def total_risk(self):
        return sum(r["risk"] for r in self.open.values())

    @property
    def remaining_budget(self):
        return max(0.0, self.max_portfolio_risk - self.total_risk)

    @property
    def open_positions(self):
        return len(self.open)

    def _group_of(self, symbol, explicit_group):
        if explicit_group is not None and explicit_group != "":
            return explicit_group
        return self.correlation_groups.get(symbol, "")

    def _direction_risk(self, direction):
        return sum(
            r["risk"] for r in self.open.values()
            if (r["direction"] == direction)
        )

    def _group_risk(self, group):
        return sum(
            r["risk"] for r in self.open.values()
            if (r["group"] == group)
        )

    def _symbol_capital(self, symbol):
        return sum(
            r["capital"] for r in self.open.values()
            if (r["symbol"] == symbol)
        )

    # --------------------------------------------------
    # Pure decision (GATES, never mutates)
    # --------------------------------------------------

    def can_accept(self, candidate):
        """May this candidate be accepted (reserved) right now?

        Pure decision -- inspects the candidate + current state.
        Sets `last_reason` on a False verdict. NEVER mutates."""

        self.last_reason = ""

        c = candidate if isinstance(candidate, CapitalCandidate) \
            else CapitalCandidate(**candidate) if isinstance(candidate, dict) \
            else CapitalCandidate(order=candidate)

        group = self._group_of(c.symbol, c.correlation_group)

        # ---- portfolio risk budget (absolute R) ----
        if self.max_portfolio_risk > 0:
            if self.total_risk + c.risk > self.max_portfolio_risk:
                self.last_reason = "risk_budget"
                return False

        # ---- total notional exposure (% of equity) ----
        if self.max_total_exposure_pct > 0 and self.equity > 0:
            cap = self.equity * self.max_total_exposure_pct / 100.0
            if self.reserved_capital + c.capital > cap:
                self.last_reason = "total_exposure"
                return False

        # ---- per-symbol capital (absolute currency) ----
        if self.max_per_symbol_capital > 0:
            if self._symbol_capital(c.symbol) + c.capital \
                    > self.max_per_symbol_capital:
                self.last_reason = "per_symbol_capital"
                return False

        # ---- directional exposure (% of equity on risk) ----
        if self.max_directional_risk_pct > 0 and self.equity > 0:
            cap = self.equity * self.max_directional_risk_pct / 100.0
            if self._direction_risk(c.direction) + c.risk > cap:
                self.last_reason = "directional_limit"
                return False

        # ---- correlated exposure (% of equity on risk) ----
        if self.max_correlated_risk_pct > 0 and self.equity > 0:
            cap = self.equity * self.max_correlated_risk_pct / 100.0
            if self._group_risk(group) + c.risk > cap:
                self.last_reason = "correlation_limit"
                return False

        # ---- shared capital (available capital) ----
        if not self.capital.can_reserve(c.capital):
            self.last_reason = self.capital.last_reason
            return False

        return True

    # --------------------------------------------------
    # Bookkeeping (never strategy)
    # --------------------------------------------------

    def reserve(self, candidate):
        """Accept + reserve a candidate, returning its reservation id.

        Assumes can_accept() already returned True (the allocator
        gates first). Bookkeeping only: books into the shared
        capital envelope AND the state ledger."""

        c = candidate if isinstance(candidate, CapitalCandidate) \
            else CapitalCandidate(**candidate) if isinstance(candidate, dict) \
            else CapitalCandidate(order=candidate)

        self._seq += 1
        rid = f"res-{self._seq}"

        self.capital.reserve(rid, c.capital)

        self.open[rid] = {
            "symbol": c.symbol,
            "direction": c.direction,
            "group": self._group_of(c.symbol, c.correlation_group),
            "risk": c.risk,
            "capital": c.capital,
        }

        return rid

    def release(self, reservation_id, pnl=0.0):
        """Release a closed reservation (frees its capital + risk).

        Bookkeeping only. Removes the reservation from both the
        capital envelope and the state ledger, folding realized PnL
        into shared equity."""

        rid = str(reservation_id)

        self.capital.release(rid, pnl=pnl)

        self.open.pop(rid, None)

    def cancel(self, reservation_id):
        """Cancel a reservation after a failed execution.

        Bookkeeping only -- capital returns to the pool with NO
        realized PnL (execution never converted into a position).
        "Rejected order does not consume capital" / "failed
        execution after reservation" are this path."""

        rid = str(reservation_id)

        self.capital.cancel(rid)

        self.open.pop(rid, None)

    # --------------------------------------------------

    def snapshot(self):
        return {
            "equity": self.equity,
            "reserved_capital": self.reserved_capital,
            "available_capital": self.available_capital,
            "total_risk": self.total_risk,
            "remaining_budget": self.remaining_budget,
            "open_positions": self.open_positions,
            "open": dict(self.open),
            "last_reason": self.last_reason,
        }

    def reset(self):
        """Fresh portfolio session (start of a run / paper pass)."""

        self.capital.reset()

        self.open = {}

        self.last_reason = ""

        self._seq = 0
