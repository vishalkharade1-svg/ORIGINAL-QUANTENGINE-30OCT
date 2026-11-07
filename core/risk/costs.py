"""Authoritative production cost model (frozen formula, explicit values).

Single source for the production round-trip cost MATH:
    commission = per_trade + position_value * rate
    slippage   = 2 * position_value * slippage_bps / 10000

Cost MODELS in this repository (do not conflate):
  production/paper/backtest defaults (this module via risk_settings):
      per_trade=0.0, rate=0.0, slippage_bps=0.0 — EXPLICIT zero-cost.
      Real venue fees are NOT configured; any live/paper profitability
      claim on defaults is cost-unrealistic by construction.
  preregistered research ladders (11F/11G COST_SCENARIOS_11F A/B/C/D):
      separate, frozen, owned by research — never read production
      globals and never modified here.
  legacy 11B script scenarios (scripts/cost_sensitivity_11b.py):
      script-only exploration, mutates globals at runtime, not used
      by production paths.

Changing the VALUES here retunes economics; changing the FORMULA
here requires re-verification against accounting.net_pnl. Both are
audited behaviors, never silent.

Phase 13 (P0/P1 remediation) — ONE economics authority. This module is
the single mandatory economics/fill authority for every executable
mode (Backtest / Paper / Live Broker dry-run):

  * KNOWN vs UNKNOWN provenance (``known`` / ``venue_source`` /
    ``unknown_costs()`` / ``require_known()`` / ``describe()``):
    an explicitly configured zero is EXPLICIT_ZERO; a missing or
    unprovisioned profile is UNKNOWN and must never be silently
    converted into zero. Only an operator-provisioned profile whose
    numbers come from venue documentation or measured fills may
    carry a ``venue_source`` (VENUE_VERIFIED).
  * Post-cost R:R (``post_cost_rr()``): the mandatory fill-validation
    math shared by every fill choke point. ``core/execution/
    economics.py::recheck_rr`` delegates to it (zero-cost form), so
    there is exactly ONE post-cost formula, not two.
  * Fill consumption: ``TradeSimulator.open_trade`` validates every
    fill through ``post_cost_rr`` using the ACTUAL commission /
    slippage passed by the calling mode, and the entry-point paper
    path (``BrokerEngine`` dry-run) re-mints those costs from
    ``paper_cost_profile()`` — one object, one model, no split brain
    on the canonical path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CostSpec:
    """Immutable round-trip cost specification (quote currency math).

    Provenance (Phase 13 authority requirements):

    * ``known=True`` (default) — the values were explicitly provided
      (settings, overrides, or an explicit constructor). An
      all-zero known spec is EXPLICIT_ZERO, never "no data".
    * ``known=False`` — cost provenance is UNKNOWN (unprovisioned
      path). ``require_known()`` refuses it fail-closed; it must
      never be silently converted into zero. See ``unknown_costs()``.
    * ``venue_source=""`` (default) — no venue verification claimed.
      A non-empty source names the venue document or measured-fill
      evidence the numbers came from (VENUE_VERIFIED). Numeric fee
      defaults remain EXTERNAL VERIFICATION REQUIRED.
    """

    per_trade: float = 0.0
    rate: float = 0.0
    slippage_bps: float = 0.0
    known: bool = True
    venue_source: str = ""

    def __post_init__(self):
        for name in ("per_trade", "rate", "slippage_bps"):
            value = getattr(self, name)
            if (not isinstance(value, (int, float))
                    or not math.isfinite(value)):
                raise ValueError("cost %s must be a finite number, got %r"
                                 % (name, value))
            if value < 0:
                raise ValueError("cost %s must be >= 0, got %r" % (name, value))
        if not isinstance(self.known, bool):
            raise ValueError("cost known must be a bool, got %r"
                             % (self.known,))
        if not isinstance(self.venue_source, str):
            raise ValueError("cost venue_source must be a string, got %r"
                             % (self.venue_source,))

    def compute(self, position_value):
        """(commission, slippage) for a position value. Pure."""
        pv = float(position_value)
        if pv < 0:
            raise ValueError("position_value must be >= 0, got %r" % (position_value,))
        commission = self.per_trade + pv * self.rate
        slippage = 2.0 * pv * (self.slippage_bps / 10000.0)
        return commission, slippage


def from_settings():
    """Production defaults from config (explicit zero-cost unless set)."""
    from config import risk_settings
    return CostSpec(
        per_trade=risk_settings.COMMISSION_PER_TRADE,
        rate=risk_settings.COMMISSION_RATE,
        slippage_bps=risk_settings.SLIPPAGE_BPS,
    )


def paper_cost_profile(overrides=None):
    """Explicit paper venue profile (Stage 4).

    Reads the SEPARATE paper-only settings
    (PAPER_COMMISSION_PER_TRADE / PAPER_COMMISSION_RATE /
    PAPER_SLIPPAGE_BPS), never production defaults and never
    frozen research ladders. `overrides` (explicit dict) wins
    for tests; otherwise config values apply. Every paper
    report must state `profile_name()` alongside the numbers.
    """
    from config import risk_settings
    if overrides is not None:
        return CostSpec(
            per_trade=overrides.get("per_trade", 0.0),
            rate=overrides.get("rate", 0.0),
            slippage_bps=overrides.get("slippage_bps", 0.0),
        )
    return CostSpec(
        per_trade=risk_settings.PAPER_COMMISSION_PER_TRADE,
        rate=risk_settings.PAPER_COMMISSION_RATE,
        slippage_bps=risk_settings.PAPER_SLIPPAGE_BPS,
    )


def paper_profile_name():
    """Configured paper profile label (report verbatim)."""
    from config import risk_settings
    return str(getattr(risk_settings, "PAPER_COST_PROFILE_NAME",
                       "explicit-zero-neutral"))


def paper_venue_realistic():
    """True only when venue-realistic values were provisioned."""
    from config import risk_settings
    return bool(getattr(risk_settings, "PAPER_COST_VENUE_REALISTIC",
                        False))


#: Snapshot of the production defaults at import (explicit zero-cost).
PRODUCTION_DEFAULTS = CostSpec(per_trade=0.0, rate=0.0, slippage_bps=0.0)


# -------------------------------------------------
# Provenance: KNOWN vs UNKNOWN vs VENUE_VERIFIED
# (Phase 13 — never silently convert UNKNOWN into ZERO)
# -------------------------------------------------

UNKNOWN = "UNKNOWN"
EXPLICIT_ZERO = "EXPLICIT_ZERO"
CONFIGURED_SIMULATION = "CONFIGURED_SIMULATION"
VENUE_VERIFIED = "VENUE_VERIFIED"


def unknown_costs() -> "CostSpec":
    """A cost spec with explicitly UNKNOWN provenance.

    All-zero values with ``known=False``: no economics may be assumed
    from it. ``require_known()`` refuses it fail-closed.
    """
    return CostSpec(per_trade=0.0, rate=0.0, slippage_bps=0.0,
                    known=False)


def require_known(spec: "CostSpec") -> "CostSpec":
    """Fail closed on UNKNOWN or missing economics.

    Returns the spec unchanged when its provenance is known
    (including explicit zero). Raises on None, non-CostSpec, or
    ``known=False`` — a missing profile must never flow into fill
    math as a silent zero.
    """
    if spec is None:
        raise ValueError("cost economics are UNKNOWN (missing spec)")
    if not isinstance(spec, CostSpec):
        raise TypeError("cost economics must be a CostSpec, got %r"
                        % type(spec).__name__)
    if not spec.known:
        raise ValueError("cost economics are UNKNOWN (unprovisioned)")
    return spec


def describe(spec: "CostSpec") -> str:
    """Classify one cost spec: UNKNOWN / EXPLICIT_ZERO /
    CONFIGURED_SIMULATION / VENUE_VERIFIED. Pure, deterministic."""
    if spec is None or not isinstance(spec, CostSpec) or not spec.known:
        return UNKNOWN
    if spec.venue_source.strip():
        return VENUE_VERIFIED
    if spec.per_trade == 0 and spec.rate == 0 and spec.slippage_bps == 0:
        return EXPLICIT_ZERO
    return CONFIGURED_SIMULATION


# -------------------------------------------------
# Post-cost R:R — the single mandatory fill-validation
# authority (Phase 13). Every fill choke point validates
# through this function; ``economics.recheck_rr`` is a
# zero-cost delegate of it, not a second formula.
# -------------------------------------------------

@dataclass(frozen=True)
class PostCostRR:
    """Verdict of post-cost R:R validation at an actual fill."""

    risk: float
    reward: float
    rr: float
    actual_entry: float
    allowed: bool
    reason: str



def post_cost_trailing(*, direction: str, entry: float, stop: float,
                       quantity: float, commission: float,
                       slippage: float, target: float = 0.0,
                       symbol: str | None = None) -> PostCostRR:
    """Validate a trailing-managed fill without confusing plan R:R with exit R.

    When an authored target is present, it remains the *qualification
    reference* even though trailing management may close earlier or later.
    The post-cost target R:R must satisfy the active instrument policy at
    entry. This does not promise or enforce a minimum realized R on exit.
    Target-less trailing trades retain the initial-stop-survival check only;
    callers must not treat them as having a planned target R:R.
    """
    from core.backtesting.accounting import directional_geometry_ok
    try:
        entry_f = float(entry); stop_f = float(stop); quantity_f = float(quantity)
        commission_f = float(commission); slippage_f = float(slippage)
    except (TypeError, ValueError):
        return PostCostRR(0.0, 0.0, 0.0, 0.0, False, "non-finite trailing economics")
    if not all(math.isfinite(v) for v in (entry_f, stop_f, quantity_f, commission_f, slippage_f)):
        return PostCostRR(0.0, 0.0, 0.0, 0.0, False, "non-finite trailing economics")
    if quantity_f <= 0 or commission_f < 0 or slippage_f < 0:
        return PostCostRR(0.0, 0.0, 0.0, entry_f, False, "invalid trailing economics")
    side = str(direction or "").upper()
    if not directional_geometry_ok(side, entry_f, stop_f, 0.0, exit_mode="TRAILING_STOP"):
        return PostCostRR(0.0, 0.0, 0.0, entry_f, False, "trailing stop geometry is inverted")
    one_way = (commission_f + slippage_f) / 2.0
    actual_entry = entry_f + one_way / quantity_f if side == "BULLISH" else entry_f - one_way / quantity_f
    risk = actual_entry - stop_f if side == "BULLISH" else stop_f - actual_entry
    if risk <= 0:
        return PostCostRR(risk, 0.0, 0.0, actual_entry, False, "actual entry breaches trailing stop")
    try:
        target_f = float(target)
    except (TypeError, ValueError):
        return PostCostRR(risk, 0.0, 0.0, actual_entry, False, "invalid trailing qualification target")
    if not math.isfinite(target_f):
        return PostCostRR(risk, 0.0, 0.0, actual_entry, False, "non-finite trailing qualification target")
    if target_f != 0.0:
        verdict = post_cost_rr(
            direction=side, entry=entry_f, stop=stop_f, target=target_f,
            quantity=quantity_f, commission=commission_f,
            slippage=slippage_f, exit_mode="FIXED_TARGET", symbol=symbol,
        )
        if not verdict.allowed:
            return PostCostRR(verdict.risk, verdict.reward, verdict.rr,
                              verdict.actual_entry, False,
                              "trailing plan qualification failed: " + verdict.reason)
        return PostCostRR(verdict.risk, verdict.reward, verdict.rr,
                          verdict.actual_entry, True,
                          "post-cost planned-target R:R accepted; realized trailing R is not guaranteed")
    return PostCostRR(risk, 0.0, 0.0, actual_entry, False,
                      "trailing plan has no qualification target; post-cost R:R cannot be certified")

def post_cost_rr(*, direction: str, entry: float, stop: float,
                 target: float, quantity: float, commission: float,
                 slippage: float, exit_mode: str = "FIXED_TARGET",
                 symbol: str | None = None) -> PostCostRR:
    """Validate R:R from the ACTUAL post-cost entry.

    Cost convention (explicit, frozen): ``commission`` + ``slippage``
    are the round-trip quote-currency totals for THIS fill (the same
    numbers the fill books exactly once via ``accounting.net_pnl``).
    Half of the round-trip total is attributed to entry erosion —
    the conservative, side-symmetric convention:

        one_way   = (commission + slippage) / 2
        LONG      actual_entry = entry + one_way / quantity
        SHORT     actual_entry = entry - one_way / quantity

    Gate semantics (mirror the existing inclusive boundary used by
    Decision/Risk/backtest erosion gates: refuse ``rr < MIN``):

    1. Any non-finite leg, cost, or quantity fails closed.
    2. Direction must be BULLISH/BEARISH (case-insensitive); the
       shift is adverse by side, so LONG and SHORT are symmetric.
    3. Directional geometry (stop < entry < target LONG, mirrored
       SHORT) is checked FIRST on the QUOTED legs — an inverted
       plan can never pass on ratio alone.
    4. Quantity must be finite and > 0 (erosion per unit is
       undefined otherwise).
    5. No mutation occurs here: this function is pure and returns
       ``actual_entry`` for the caller to apply AFTER acceptance.
    6. Post-cost ``rr`` below the ACTIVE minimum-R policy
       (``trading_policy()`` for the fill symbol, global or
       exact-instrument override) is REFUSED; exactly at the
       minimum is accepted per the existing inclusive boundary.
    """
    from core.backtesting.accounting import (
        directional_geometry_ok,
        risk_reward_allowed,
    )

    from config import risk_settings

    def _refuse(risk: float, reward: float, rr: float,
                actual: float, reason: str) -> PostCostRR:
        return PostCostRR(risk=risk, reward=reward, rr=rr,
                          actual_entry=actual, allowed=False,
                          reason=reason)

    for label, value in (("entry", entry), ("stop", stop),
                         ("target", target), ("quantity", quantity),
                         ("commission", commission),
                         ("slippage", slippage)):
        if (not isinstance(value, (int, float))
                or not math.isfinite(float(value))):
            return _refuse(0.0, 0.0, 0.0, 0.0,
                           "%s is non-finite" % label)
    entry_f = float(entry)
    stop_f = float(stop)
    target_f = float(target)
    quantity_f = float(quantity)
    commission_f = float(commission)
    slippage_f = float(slippage)

    side = str(direction or "").upper()
    if side not in ("BULLISH", "BEARISH"):
        return _refuse(0.0, 0.0, 0.0, 0.0,
                       "direction must be BULLISH or BEARISH")

    if commission_f < 0 or slippage_f < 0:
        return _refuse(0.0, 0.0, 0.0, 0.0,
                       "costs must not be negative")

    if not directional_geometry_ok(side, entry_f, stop_f, target_f,
                                   exit_mode=exit_mode):
        return _refuse(0.0, 0.0, 0.0, entry_f,
                       "quoted stop/target geometry is inverted")

    if quantity_f <= 0:
        return _refuse(0.0, 0.0, 0.0, entry_f,
                       "quantity must be positive")

    one_way = (commission_f + slippage_f) / 2.0
    if side == "BULLISH":
        actual_entry = entry_f + one_way / quantity_f
        risk = actual_entry - stop_f
        reward = target_f - actual_entry
    else:
        actual_entry = entry_f - one_way / quantity_f
        risk = stop_f - actual_entry
        reward = actual_entry - target_f

    if risk <= 0:
        return _refuse(risk, reward, 0.0, actual_entry,
                       "actual entry breaches stop")
    if reward <= 0:
        return _refuse(risk, reward, 0.0, actual_entry,
                       "actual entry erodes target")

    rr = reward / risk
    if exit_mode == "TRAILING_STOP":
        return _refuse(risk, reward, rr, actual_entry,
                       "trailing-stop mode has no fixed target R:R")
    from core.backtesting.accounting import risk_reward_allowed
    gate_mode = "FIXED_TARGET" if exit_mode == "TRAILING_STOP" else exit_mode
    if not risk_reward_allowed(rr, exit_mode=gate_mode, symbol=symbol):
        from core.risk.trading_policy import trading_policy
        policy = trading_policy(symbol)
        minimum = float(policy.min_rr)
        maximum = float(policy.max_rr)
        if rr < minimum:
            reason = "post-cost R:R %.4f below minimum %.1f" % (rr, minimum)
        elif rr > maximum:
            reason = "post-cost R:R %.4f above maximum %.1f" % (rr, maximum)
        else:
            reason = "fixed-target R:R policy rejected"
        return _refuse(risk, reward, rr, actual_entry, reason)
    return PostCostRR(risk=risk, reward=reward, rr=rr,
                      actual_entry=actual_entry, allowed=True,
                      reason="post-cost R:R accepted")
