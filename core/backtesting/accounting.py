"""
====================================================

QuantEngine — Canonical Financial Accounting

Phase 9Q-4

Single source of truth for every monetary calculation that
every execution mode (Backtest, Paper, Live Broker) must use.

Do NOT reinvent PnL elsewhere.

Definitions (explicit, frozen):

  entry price        Trade.entry (limit price at fill)
  exit price         Trade.exit_price (stop / target / exchange close)
  quantity           Trade.quantity (already rounded + capped by PositionManager)
  side/direction     "BULLISH" (long) / "BEARISH" (short)

  notional           entry * quantity
                     (position value at entry, quote currency)

  gross PnL          (exit - entry) * quantity   if long
                     (entry - exit) * quantity   if short
                     (fees excluded, slippage excluded)

  commission         Trade.commission (round-trip, quote currency)
  slippage           Trade.slippage  (round-trip, quote currency)

  net PnL            gross - commission - slippage
                     (authoritative, stored as Trade.pnl)

  position return %  net / notional * 100
                     (return on the position's own notional)

  portfolio return % net / equity_before * 100
                     (return on the account that funded the trade;
                      equity_before = AccountState.balance at entry)

  equity_before      Account.balance before booking
  equity_after       equity_before + net

  risk amount        OrderIntent.risk_amount / Trade.risk_amount
                     (intended max loss, quote currency)

  realized R         net / risk_amount  (when risk_amount > 0)

  Classification (exact, no tolerance unless documented):
    pnl >  0  → WIN
    pnl <  0  → LOSS
    pnl == 0  → BREAKEVEN   (neither win nor loss)

  Breakeven tolerance: 0.0 exactly. If a tolerance is ever needed
  (e.g. floating dust), it must be an explicit parameter, documented,
  and applied consistently in every consumer.

Fees and slippage are represented separately; net PnL is authoritative
for every downstream metric (PerformanceAnalytics, Account, Portfolio).

====================================================
"""

# Breakeven is exact zero per prompt. Tolerance only if explicitly passed.
_BREAKEVEN_TOL = 0.0

import math


def notional(entry: float, quantity: float) -> float:
    """Position notional at entry (quote currency)."""
    return float(entry) * float(quantity)


def gross_pnl(direction: str, entry: float, exit_price: float, quantity: float) -> float:
    """Gross PnL (fees excluded) for a closed trade."""
    direction = (direction or "").upper()
    if direction == "BULLISH":
        return (float(exit_price) - float(entry)) * float(quantity)
    if direction == "BEARISH":
        return (float(entry) - float(exit_price)) * float(quantity)
    # Unknown direction → 0, caller should never reach here
    return 0.0


def net_pnl(gross: float, commission: float = 0.0, slippage: float = 0.0,
            funding: float = 0.0) -> float:
    """Net PnL = gross - commission - slippage - signed funding."""
    return float(gross) - float(commission) - float(slippage) - float(funding)


def position_return_percent(pnl: float, entry: float, quantity: float) -> float:
    """Position return % = net / notional * 100."""
    notion = notional(entry, quantity)
    if notion == 0:
        return 0.0
    return (float(pnl) / notion) * 100.0


def portfolio_return_percent(pnl: float, equity_before: float) -> float:
    """Portfolio return % = net / equity_before * 100."""
    if equity_before == 0:
        return 0.0
    return (float(pnl) / float(equity_before)) * 100.0


def realized_r(pnl: float, risk_amount: float) -> float:
    """Realized R multiple = net / risk_amount."""
    if risk_amount is None or float(risk_amount) == 0:
        return 0.0
    return float(pnl) / float(risk_amount)


def realized_rr(direction: str, entry: float, stop_loss: float,
                take_profit: float) -> float:
    """Realized reward:risk at an ACTUAL fill price (Stage 4).

    Signed by side so a target on the wrong side of the fill can
    never hide behind an absolute value:

      LONG  -> (take_profit - entry) / |entry - stop_loss|
      SHORT -> (entry - take_profit) / |entry - stop_loss|

    Positive means distance remains toward the plan target;
    NEGATIVE means the fill is already beyond the target (plan
    exceeded at entry — favorable gap-through-target) or the
    target is on the wrong side (plan broken). Zero risk (or any
    non-finite leg) yields exactly 0.0 — never NaN/inf. The runtime
    order-time gates use the active trading-policy bounds (default
    1:1..1:20); this function measures fills and must never gate
    them (a live market fill cannot be un-filled).
    """
    try:
        entry_f = float(entry)
        stop_f = float(stop_loss)
        target_f = float(take_profit)
    except (TypeError, ValueError):
        return 0.0
    if not (math.isfinite(entry_f) and math.isfinite(stop_f)
            and math.isfinite(target_f)):
        return 0.0
    risk = abs(entry_f - stop_f)
    if risk <= 0:
        return 0.0
    side = (direction or "").upper()
    if side == "BEARISH":
        return (entry_f - target_f) / risk
    return (target_f - entry_f) / risk


def directional_geometry_ok(direction: str, entry: float,
                            stop_loss: float,
                            take_profit: float = 0.0,
                            exit_mode: str = "FIXED_TARGET") -> bool:
    """Validate directional stop geometry and optional fixed target.

    FIXED_TARGET: LONG requires stop < entry < target; SHORT requires
    target < entry < stop.

    TRAILING_STOP: no fixed target is required; the initial stop must be
    strictly protective (LONG stop < entry, SHORT stop > entry).

    Strict inequalities and finite values are mandatory.
    """
    try:
        entry_f = float(entry)
        stop_f = float(stop_loss)
        target_f = float(take_profit)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(entry_f) and math.isfinite(stop_f)
            and math.isfinite(target_f)):
        return False
    side = (direction or "").upper()
    mode = str(exit_mode or "FIXED_TARGET").upper()
    if side == "BULLISH":
        if mode == "TRAILING_STOP":
            return stop_f < entry_f
        return stop_f < entry_f < target_f
    if side == "BEARISH":
        if mode == "TRAILING_STOP":
            return stop_f > entry_f
        return target_f < entry_f < stop_f
    return False


def risk_reward_allowed(
    rr: float,
    exit_mode: str = "FIXED_TARGET",
    symbol: str | None = None,
) -> bool:
    """Return whether a computed R:R satisfies the runtime policy.

    The frozen research threshold is deliberately not consulted here.
    Trading policy resolves globally or by exact instrument override.
    """
    try:
        rr_f = float(rr)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(rr_f):
        return False
    mode = str(exit_mode or "FIXED_TARGET").upper()
    if mode == "TRAILING_STOP":
        return False  # trailing exits must not be admitted through fixed-R:R gates
    if mode != "FIXED_TARGET":
        return False
    from core.risk.trading_policy import trading_policy
    policy = trading_policy(symbol)
    return float(policy.min_rr) <= rr_f <= float(policy.max_rr)


def order_rr(entry: float, stop_loss: float,
             take_profit: float):
    """Unsigned reward:risk or None when unmeasurable.

    Returns reward / risk with risk = |entry - stop|,
    reward = |target - entry|. Returns None (never NaN,
    never inf, never a fabricated ratio) when any leg is
    non-finite or risk <= 0. Callers must check
    directional_geometry_ok FIRST -- a positive ratio alone
    does not prove a valid trade.
    """
    try:
        entry_f = float(entry)
        stop_f = float(stop_loss)
        target_f = float(take_profit)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(entry_f) and math.isfinite(stop_f)
            and math.isfinite(target_f)):
        return None
    risk = abs(entry_f - stop_f)
    if risk <= 0:
        return None
    return abs(target_f - entry_f) / risk


def classify_pnl(pnl: float, tol: float = _BREAKEVEN_TOL) -> str:
    """
    Canonical classification.

    pnl >  tol → "WIN"
    pnl < -tol → "LOSS"
    else       → "BREAKEVEN"

    Non-finite pnl (NaN, +Inf, -Inf) raises ValueError
    (11E-Prep C1-D): a corrupt P&L must never be read as
    WIN, LOSS, or BREAKEVEN — and must never be booked.
    Upstream guards (sizer, audit, simulator) guarantee
    finite P&L in production paths, so this is the
    fail-loud backstop, not a control-flow branch.
    """
    pnl = float(pnl)
    tol = float(tol)
    if not math.isfinite(pnl):
        raise ValueError(
            f"classify_pnl received non-finite pnl={pnl!r}: "
            "refusing to classify corrupt P&L."
        )
    if pnl > tol:
        return "WIN"
    if pnl < -tol:
        return "LOSS"
    return "BREAKEVEN"


def is_win(pnl: float, tol: float = _BREAKEVEN_TOL) -> bool:
    return classify_pnl(pnl, tol) == "WIN"


def is_loss(pnl: float, tol: float = _BREAKEVEN_TOL) -> bool:
    return classify_pnl(pnl, tol) == "LOSS"


def is_breakeven(pnl: float, tol: float = _BREAKEVEN_TOL) -> bool:
    return classify_pnl(pnl, tol) == "BREAKEVEN"
