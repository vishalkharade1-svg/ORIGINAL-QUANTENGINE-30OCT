"""
====================================================

QuantEngine

Portfolio Risk & Capital Coordination (core layer)

Phase 8 -- the transition from per-symbol strategy risk to
portfolio-level risk and capital coordination.

WHY THIS LAYER EXISTS
---------------------
Phases 6A-6E gave the engine the ability to discover and
trade a DYNAMIC MULTI-SYMBOL universe. Before that the system
reasoned about:

    one symbol -> one pipeline -> one paper ledger

and the only exposure ceiling (RiskEngine, MAX_TOTAL_EXPOSURE_
PCT) was PER-SYMBOL and PENDING-ONLY -- it cannot see the other
symbols. Now we must reason about a portfolio:

    BTC ----+
    ETH ----+--> Portfolio Risk Gate --> total exposure
    SOL ----+                          |  directional exposure
    ... ----+                          |  correlated exposure
                                        |  concurrent positions
                                        |  portfolio drawdown
                                        |  risk budget
                                        |  capital allocation

THE INVARIANT (carried forward, verbatim)
-----------------------------------------
The portfolio layer MUST NOT silently modify strategy
semantics. The separation stays:

    SymbolPipeline -> Strategy decision -> RiskEngine ->
    OrderIntent -> Portfolio Risk Gate -> Execution

The portfolio layer may say:

    "This otherwise valid trade cannot be accepted because
    portfolio risk is already exhausted."

It must NEVER say:

    "I'll change the setup's entry, stop, target, direction,
    or strategy logic."

So this module ONLY GATES and ONLY BOOKKEEP. `order_allows()`
is a PURE DECISION (it inspects the order and the current
portfolio state and returns True/False); it never mutates the
order, the setup, or any strategy object. `register_open()` /
`release_closed()` are bookkeeping that updates the portfolio
ledger -- never a setup/strategy field. This preserves the
researchability and causality established in Phases 7 / 7E.

The gate consumes the FROZEN OrderIntent fields (symbol,
direction, risk_amount, position_value, expected_loss) and
Trade fields (symbol, direction, risk_amount, pnl) -- it reads
only what the strategy already decided and never rewrites it.

INTERFACE / COMPATIBILITY
-------------------------
`PortfolioRiskManager` implements BOTH:
  * an order-aware surface used by the live/paper and
    canonical wiring (order_allows / register_open /
    release_closed), and
  * the legacy duck-typed surface (can_open / register_trade /
    close_trade / current_risk / open_positions /
    open_by_symbol / equity / reset) so the existing
    PortfolioBacktester adapter keeps working verbatim.

All caps are OPTIONAL and DISABLED by default (None / 0 /
missing = no binding). Adding the gate with no caps configured
changes NOTHING about a default run -- "default neutrality".
Each cap binds only when a positive value is supplied (either
explicitly to the constructor or, where wired, from
config/risk_settings.py).
====================================================
"""

def _fnum(value):
    """Coerce a value to float, treating None and blanks as 0.0."""
    try:
        return float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0


def _finite(value):
    """Stage 1-3 hardening: True only for real finite numbers."""
    import math
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


class PortfolioRiskManager:
    """Portfolio-level risk gate + capital-coordination ledger.

    Dimensions enforced (each optional/disabled unless set):
      * concurrent positions        -- max_positions
      * portfolio risk budget       -- max_portfolio_risk (R / $
        budget) vs equity
      * total notional exposure     -- max_total_exposure_pct
        (% of equity) on aggregate open position_value
      * directional exposure        -- max_directional_risk_pct
        (% of equity) per direction on aggregate risk
      * correlated exposure         -- max_correlated_risk_pct
        (% of equity) per correlation group
      * per-symbol capital          -- max_per_symbol_notional
        (currency) on a single symbol's open position_value
      * portfolio drawdown / daily  -- max_daily_loss_pct of
        equity lost today -> gate all new entries
    """

    def __init__(
        self,
        max_portfolio_risk=None,
        max_positions=None,
        max_total_exposure_pct=None,
        max_per_symbol_notional=None,
        max_directional_risk_pct=None,
        max_correlated_risk_pct=None,
        max_daily_loss_pct=None,
        equity=None,
        correlation_groups=None,
    ):

        # ---- caps (None/0 = disabled = default neutral) ----
        self.max_portfolio_risk = (
            _fnum(max_portfolio_risk)
        )
        self.max_positions = (
            int(max_positions) if max_positions is not None else None
        )
        self.max_total_exposure_pct = _fnum(max_total_exposure_pct)
        self.max_per_symbol_notional = _fnum(max_per_symbol_notional)
        self.max_directional_risk_pct = _fnum(max_directional_risk_pct)
        self.max_correlated_risk_pct = _fnum(max_correlated_risk_pct)
        self.max_daily_loss_pct = _fnum(max_daily_loss_pct)

        # 9Q-8: Fail-fast validation per risk_config_contract.md
        # Fractions 0-1, _PCT 0-100, amounts >0
        def _check_pct(name, v):
            if v is not None and v != 0 and not (0 < v <= 100):
                raise ValueError(f"{name} must be 0 (disabled) or 0<intensity> 100, got {v!r}")
        def _check_frac(name, v):
            # Legacy absolute values (e.g., 5.0, 100.0) are allowed for backward compat
            # but fraction (0.03 = 3%) is the canonical contract. Values >1 are treated as absolute.
            if v is not None and v != 0 and v < 0:
                raise ValueError(f"{name} must be >=0, got {v!r}")
        _check_pct("max_total_exposure_pct", self.max_total_exposure_pct)
        _check_pct("max_directional_risk_pct", self.max_directional_risk_pct)
        _check_pct("max_correlated_risk_pct", self.max_correlated_risk_pct)
        _check_pct("max_daily_loss_pct", self.max_daily_loss_pct)
        _check_frac("max_portfolio_risk", self.max_portfolio_risk)
        if self.max_positions is not None and self.max_positions < 0:
            raise ValueError(f"max_positions must be >=0, got {self.max_positions!r}")
        if self.max_portfolio_risk < 0 or self.max_per_symbol_notional < 0:
            raise ValueError("max_portfolio_risk / max_per_symbol_notional must be >=0")

        # starting equity basis (None = a running realized-pnl basis)
        self._equity_basis = (
            _fnum(equity) if equity is not None else None
        )

        # symbol -> correlation group map (optional)
        self.correlation_groups = dict(correlation_groups or {})

        # ---- portfolio ledger ----
        # {symbol: {"risk": float, "notional": float,
        #           "direction": str, "group": str}}
        self.open_by_symbol = {}

        self.realized_pnl = 0.0

        self.peak_equity = None

        self.last_reason = ""

        self._today_realized_pnl = 0.0

        self._reset_initial_equity()

    # --------------------------------------------------
    # Equity basis
    # --------------------------------------------------

    def _reset_initial_equity(self):

        basis = self.equity

        if basis > 0:

            self.peak_equity = basis

    @property
    def equity(self):
        """Portfolio equity = starting basis + realized PnL (or an
        explicitly injected equity base)."""

        if self._equity_basis is not None:

            return self._equity_basis + self.realized_pnl

        return self.realized_pnl

    @property
    def open_positions(self):

        return len(self.open_by_symbol)

    @property
    def current_risk(self):

        return sum(
            e["risk"] for e in self.open_by_symbol.values()
        )

    @property
    def current_notional(self):

        return sum(
            e["notional"] for e in self.open_by_symbol.values()
        )

    @property
    def direction_risk(self):
        """Per-direction aggregate risk. {BULLISH: .., BEARISH: ..}."""

        out = {"BULLISH": 0.0, "BEARISH": 0.0}

        for entry in self.open_by_symbol.values():

            d = (entry.get("direction") or "").upper()

            if d in out:

                out[d] += entry["risk"]

        return out

    @property
    def correlated_risk(self):
        """Per-correlation-group aggregate risk."""

        out = {}

        for entry in self.open_by_symbol.values():

            g = entry.get("group") or ""

            out[g] = out.get(g, 0.0) + entry["risk"]

        return out

    @property
    def drawdown(self):

        peak = self.peak_equity

        if peak is None or peak <= 0:

            return 0.0

        return max(0.0, peak - self.equity)

    @property
    def drawdown_percent(self):

        peak = self.peak_equity

        if peak is None or peak <= 0:

            return 0.0

        return (self.drawdown / peak) * 100.0

    # --------------------------------------------------
    # Dimension normalisers (order-aware OR primitive)
    # --------------------------------------------------

    def _dims(self, obj, risk=None, symbol=None, position_value=None,
             direction=None, correlation_group=None):
        """Normalise a gate/release input to
        (risk, symbol, position_value, direction, group).

        Accepts an OrderIntent/Trade-like object (reads its fields)
        OR explicit primitives. Never mutates obj."""

        if obj is not None and not isinstance(obj, (int, float)):

            risk = _fnum(getattr(obj, "risk_amount", 0.0) or risk)
            symbol = getattr(obj, "symbol", None) or symbol
            position_value = _fnum(
                getattr(obj, "position_value", 0.0) or position_value
            )
            direction = getattr(obj, "direction", None) or direction

        risk = _fnum(risk)
        position_value = _fnum(position_value)

        if risk <= 0:
            # fall back to expected_loss for order intents
            risk = _fnum(getattr(obj, "expected_loss", 0.0) or 0.0)

        group = correlation_group

        if group is None:

            group = self.correlation_groups.get(symbol, "")

        return (risk, symbol, position_value, direction, group)

    # --------------------------------------------------
    # Pure decision (GATES, never mutates)
    # --------------------------------------------------

    def order_allows(self, order, equity=None):
        """Pure portfolio gate decision for an OrderIntent.

        Returns True if the otherwise-valid order may be accepted
        given current portfolio state; False if portfolio risk is
        exhausted. NEVER mutates the order, the setup, or the
        strategy. This is the primary "gates not mutates" entry.

        `last_reason` is set to a short human-readable reason on a
        False verdict (observable, not a strategy change)."""

        risk, symbol, position_value, direction, group = self._dims(
            order
        )

        return self._allows(
            risk=risk,
            symbol=symbol,
            position_value=position_value,
            direction=direction,
            group=group,
            equity=equity,
        )

    def can_open(self, trade_risk, symbol=None, position_value=0.0,
                 direction=None, correlation_group=None, equity=None):
        """Legacy-compatible pure gate (primitives).

        Provided so the existing PortfolioBacktester adapter and the
        legacy test surface keep working verbatim. Pure decision --
        no mutation."""

        return self._allows(
            risk=_fnum(trade_risk),
            symbol=symbol,
            position_value=_fnum(position_value),
            direction=direction,
            group=correlation_group,
            equity=equity,
        )

    def _allows(self, risk, symbol, position_value, direction, group,
                equity=None):

        self.last_reason = ""

        # Stage 1-3 hardening: fail CLOSED on non-finite numerics.
        # A NaN/inf risk, notional, equity, or daily-PnL ledger must
        # block new entries, never coerce to 0 and pass.
        if not _finite(risk) or not _finite(position_value):
            self.last_reason = "non_finite_input"
            return False

        base = self.equity if equity is None else _fnum(equity)

        if not _finite(base):
            self.last_reason = "non_finite_equity"
            return False

        # ---- concurrency ----
        if self.max_positions is not None:
            if self.open_positions >= self.max_positions:
                self.last_reason = "max_positions"
                return False

        if self.max_positions is not None and self.max_positions <= 0:
            self.last_reason = "max_positions_disabled"
            return False

        # ---- portfolio risk budget
        # Canonical contract: fraction 0.03 = 3% of equity (cap = equity * 0.03)
        # Legacy absolute values >1 (e.g., 5.0, 100.0) are still supported for backward compat
        if self.max_portfolio_risk > 0:
            if self.max_portfolio_risk <= 1 and base > 0:
                cap = base * self.max_portfolio_risk
            elif self.max_portfolio_risk <= 1 and base <= 0:
                cap = None  # No equity basis yet — cannot gate on fraction, allow
            else:
                cap = self.max_portfolio_risk  # legacy absolute
            if cap is not None and self.current_risk + risk > cap:
                self.last_reason = "max_portfolio_risk"
                return False

        # ---- total notional exposure ----
        if self.max_total_exposure_pct > 0 and base > 0:

            cap = base * self.max_total_exposure_pct / 100.0

            if self.current_notional + position_value > cap:
                self.last_reason = "max_total_exposure"
                return False

        # ---- per-symbol capital ----
        if self.max_per_symbol_notional > 0:

            current_symbol = 0.0

            entry = self.open_by_symbol.get(symbol)

            if entry is not None:

                current_symbol = entry["notional"]

            if current_symbol + position_value > self.max_per_symbol_notional:
                self.last_reason = "max_per_symbol_notional"
                return False

        # ---- directional exposure ----
        if self.max_directional_risk_pct > 0 and base > 0:

            cap = base * self.max_directional_risk_pct / 100.0

            direction = (direction or "").upper()

            current_dir = self.direction_risk.get(
                direction, 0.0
            )

            if current_dir + risk > cap:
                self.last_reason = "max_directional_risk"
                return False

        # ---- correlated exposure ----
        if self.max_correlated_risk_pct > 0 and base > 0:

            cap = base * self.max_correlated_risk_pct / 100.0

            current_group = self.correlated_risk.get(group or "", 0.0)

            if current_group + risk > cap:
                self.last_reason = "max_correlated_risk"
                return False

        # ---- daily loss guard ----
        if self.max_daily_loss_pct > 0 and base > 0:

            if not _finite(self._today_realized_pnl):
                self.last_reason = "non_finite_daily_pnl"
                return False

            loss_cap = -(base * self.max_daily_loss_pct / 100.0)

            if self._today_realized_pnl <= loss_cap:
                self.last_reason = "max_daily_loss"
                return False

        return True

    # --------------------------------------------------
    # Registration / release (BOOKKEEPING, never strategy)
    # --------------------------------------------------

    def register_open(self, order):
        """Book a freshly-opened trade into the portfolio ledger.

        Bookkeeping only: updates exposure/risk/count state. Never
        touches the order/setup/strategy."""

        risk, symbol, position_value, direction, group = self._dims(
            order
        )

        self._register(
            risk=risk,
            symbol=symbol,
            position_value=position_value,
            direction=direction,
            group=group,
        )

    def register_trade(self, trade_risk, symbol=None, position_value=0.0,
                       direction=None, correlation_group=None):
        """Legacy-compatible bookkeeping (primitives)."""

        self._register(
            risk=_fnum(trade_risk),
            symbol=symbol,
            position_value=_fnum(position_value),
            direction=direction,
            group=correlation_group,
        )

    def _register(self, risk, symbol, position_value, direction, group):

        entry = self.open_by_symbol.get(symbol)

        if entry is None:

            self.open_by_symbol[symbol] = {
                "risk": risk,
                "notional": position_value,
                "direction": (direction or "").upper() if direction
                else "",
                "group": group or "",
            }

        else:

            entry["risk"] += risk
            entry["notional"] += position_value

    # --------------------------------------------------

    def release_closed(self, trade, pnl=None):
        """Release a closed trade's exposure from the ledger.

        Bookkeeping only. Also folds the realized PnL into the
        equity basis and updates peak-equity / daily-loss state."""

        risk, symbol, position_value, _dir, _group = self._dims(trade)

        pnl = _fnum(pnl)
        if pnl == 0 and hasattr(trade, "pnl"):
            pnl = _fnum(getattr(trade, "pnl", 0.0))

        self._release(risk=risk, symbol=symbol, pnl=pnl)

    def close_trade(self, trade_risk, symbol=None, pnl=0.0):
        """Legacy-compatible release (primitives)."""

        self._release(risk=_fnum(trade_risk), symbol=symbol, pnl=_fnum(pnl))

    def _release(self, risk, symbol, pnl):

        # The engine is single-position-per-symbol: when a symbol's
        # trade closes, that symbol's exposure is fully released.
        self.open_by_symbol.pop(symbol, None)

        self.realized_pnl += pnl

        self._today_realized_pnl += pnl

        if self.equity > (self.peak_equity or 0.0):

            self.peak_equity = self.equity

    # --------------------------------------------------

    def snapshot(self):
        """Observable portfolio-state snapshot for diagnostics /
        analytics. Read-only."""

        return {
            "open_positions": self.open_positions,
            "current_risk": self.current_risk,
            "current_notional": self.current_notional,
            "open_by_symbol": dict(self.open_by_symbol),
            "direction_risk": dict(self.direction_risk),
            "correlated_risk": dict(self.correlated_risk),
            "equity": self.equity,
            "realized_pnl": self.realized_pnl,
            "drawdown": self.drawdown,
            "drawdown_percent": self.drawdown_percent,
            "last_reason": self.last_reason,
        }

    # --------------------------------------------------

    def reset(self):
        """Fresh portfolio session: clear ledger + create PnL.
        Called at the start of every backtest run / paper session so
        exposure from a previous run never leaks into the next."""

        self.open_by_symbol = {}

        self.realized_pnl = 0.0

        self._today_realized_pnl = 0.0

        self.last_reason = ""

        self.peak_equity = None

        self._reset_initial_equity()
