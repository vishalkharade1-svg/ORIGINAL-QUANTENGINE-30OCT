"""Versioned, venue-explicit execution economics (Phase 6 local track).

INTEGRATION STATUS: execution cost gates are wired through the canonical
fill path; this module's funding schedule is now wired into
``TradeSimulator`` for explicit backtest/paper callers that provide
verified funding evidence. ``recheck_rr()``/``apply_costs()`` remain
non-authoritative helpers and are not evidence of live economics.
(``tests/test_authoritative_path_phase7.py`` pins zero runtime callers;
absence is the fail-closed posture, not an accident). Do NOT cite this
module as order-flow protection. The backtester carries SEPARATE
actual-fill erosion logic (``backtesting/backtester.py`` revalidates
``order_rr()`` at the actual next-bar-open entry and refuses eroded
fills) — that logic guards ENTRY-PRICE erosion only, NOT costs: with
the default zero-cost config, fees/slippage erosion is exactly 0.0 by
construction. Cost-adjusted post-cost R:R protection in ANY live/paper
mode therefore remains UNVERIFIED. Wiring this module into the
executable path (or formally retiring it) is an open remediation item;
either change must update the boundary pins AND add an integration
test proving fills are refused below minimum R:R.

The repository's production defaults are neutral zero-cost
(``config/risk_settings.py``: ``COMMISSION_* = 0.0``, ``SLIPPAGE_BPS = 0.0``,
``PAPER_COST_VENUE_REALISTIC = False``).  A zero-cost simulation must never
be presented as realistic performance or as promotion evidence.

This module makes economics explicit and versioned:

* Every profile carries a name, version, full cost assumptions, and a
  ``venue_realistic`` flag.  Only an operator-provisioned profile whose
  numbers come from venue documentation or measured fills may set that flag.
* ``require_realistic()`` is the promotion gate: paper/backtest results
  computed under a non-realistic profile are refused for any
  performance/promotion path, fail-closed.
* ``apply_costs()`` moves the entry price adversely ( buys up, sells down)
  by spread + slippage and adds commission + funding to the cost ledger.
* ``recheck_rr()`` recomputes risk/reward/R:R from the ACTUAL (post-cost)
  entry and delegates to the runtime trading-policy authority. Execution
  adjustments must never silently bypass the configured instrument/global
  R:R bounds.

No venue fee numbers are invented here: the only built-in profiles are the
explicit zero-neutral baseline (``venue_realistic=False``) and operator-built
custom profiles.  Numeric fee defaults remain EXTERNAL VERIFICATION REQUIRED.

LIVE/PAPER FUNDING BOUNDARY: historical funding can be supplied through
``FundingSchedule`` without synthetic interpolation or zero substitution.
Live exchange-reported realized P&L/funding remains venue-evidence dependent
and is not inferred from historical funding.

PAPER SPLIT-BRAIN WARNING (forensically confirmed 2026-09-22): the paper
cost profile (``core/risk/costs.py::paper_cost_profile``, i.e. the
``PAPER_*`` settings) drives ONLY readiness/certification reporting
(``core/paper_trading/readiness.py``).  Actual paper fills do NOT consume
it: ``PaperTradingEngine`` fills at intent entry adjusted only by its own
``fill_slippage_bps`` argument (default 0.0, never wired to
``PAPER_SLIPPAGE_BPS``) plus the intent commission/slippage minted by
``RiskEngine`` from PRODUCTION settings, and forces
``market.spread = 0.0``.  A normal paper run is therefore FRICTIONLESS
unless the caller explicitly passes ``fill_slippage_bps`` — and even then
commissions/spreads stay at intent values.  Certification cost realism
must never be confused with fill realism; unifying the two models is an
open remediation item.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping
import math


@dataclass(frozen=True, slots=True)
class FundingEvent:
    """One verified venue funding settlement event."""
    timestamp: int
    rate: float
    source: str = ""
    def __post_init__(self) -> None:
        if int(self.timestamp) <= 0 or not math.isfinite(float(self.rate)):
            raise ValueError("funding event requires finite timestamp/rate")
        if not self.source:
            raise ValueError("funding event requires an evidence source")


class FundingSchedule:
    """Timestamped funding evidence; no interpolation or synthetic zero."""
    def __init__(self, events: Iterable[FundingEvent | Mapping[str, object]], *, coverage_start: int | None = None, coverage_end: int | None = None):
        normalized = []
        for event in events:
            if isinstance(event, FundingEvent):
                normalized.append(event)
            elif isinstance(event, Mapping):
                normalized.append(FundingEvent(
                    timestamp=int(event["time"]), rate=float(event["rate"]),
                    source=str(event.get("source", "venue-funding-history"))))
            else:
                raise TypeError("funding events must be FundingEvent or mapping")
        normalized.sort(key=lambda x: x.timestamp)
        if any(a.timestamp == b.timestamp for a,b in zip(normalized, normalized[1:])):
            raise ValueError("duplicate funding settlement timestamp")
        self._events = tuple(normalized)
        self._coverage_start = (int(coverage_start) if coverage_start is not None else (self._events[0].timestamp if self._events else None))
        self._coverage_end = (int(coverage_end) if coverage_end is not None else (self._events[-1].timestamp if self._events else None))
        if self._coverage_start is not None and self._coverage_end is not None and self._coverage_end < self._coverage_start:
            raise ValueError("invalid funding evidence coverage interval")

    @property
    def events(self):
        return self._events

    def covers(self, start_timestamp: int, end_timestamp: int) -> bool:
        """Return whether the evidence query window covers an OOS interval.

        This is a data-coverage gate, not a claim that every bar has a
        funding settlement. Settlement events are sparse and are applied only
        when their timestamps fall inside an actual holding interval.
        """
        start = int(start_timestamp)
        end = int(end_timestamp)
        if start <= 0 or end < start:
            raise ValueError("invalid coverage interval")
        if not self._events:
            return False
        return (self._coverage_start is not None and self._coverage_end is not None
                and self._coverage_start <= start <= end <= self._coverage_end)

    def cost(self, *, entry_time: int, exit_time: int, direction: str,
             entry: float, quantity: float) -> tuple[float, int]:
        if int(exit_time) < int(entry_time) or float(entry) <= 0 or float(quantity) <= 0:
            raise ValueError("invalid funding holding interval or position")
        side = str(direction).upper()
        if side not in ("BULLISH", "BEARISH"):
            raise ValueError("direction must be BULLISH or BEARISH")
        notional = float(entry) * float(quantity)
        total = 0.0; count = 0
        for event in self._events:
            if int(entry_time) < event.timestamp <= int(exit_time):
                signed = notional * event.rate
                total += signed if side == "BULLISH" else -signed
                count += 1
        return total, count


TRADING_MIN_RISK_REWARD = 1.0
TRADING_MAX_RISK_REWARD = 20.0


@dataclass(frozen=True, slots=True)
class EconomicsProfile:
    """One versioned execution-economics assumption set."""

    name: str
    version: str
    commission_per_trade: float = 0.0
    commission_rate: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    funding_rate_per_bar: float = 0.0
    latency_ms: float = 0.0
    max_participation: float = 1.0
    partial_fill_model: str = "full_or_reject"
    venue_realistic: bool = False
    venue_source: str = ""
    verified_at: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            raise ValueError("economics profile requires name and version")
        for field_name in ("commission_per_trade", "commission_rate",
                           "spread_bps", "slippage_bps",
                           "funding_rate_per_bar", "latency_ms"):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or value != value:
                raise ValueError("%s must be a finite number" % field_name)
            if value < 0:
                raise ValueError("%s must not be negative" % field_name)
        if not 0 < self.max_participation <= 1.0:
            raise ValueError("max_participation must be in (0, 1]")
        if self.venue_realistic and not self.venue_source:
            raise ValueError(
                "a venue-realistic profile must cite its venue source")


ZERO_NEUTRAL = EconomicsProfile(
    name="explicit-zero-neutral", version="1",
    venue_realistic=False,
    venue_source="",
)


@dataclass(frozen=True, slots=True)
class CostedEntry:
    actual_entry: float
    spread_cost: float
    slippage_cost: float
    commission_cost: float
    funding_cost: float
    total_cost: float


@dataclass(frozen=True, slots=True)
class RiskRewardRecheck:
    risk: float
    reward: float
    rr: float
    allowed: bool
    reason: str


def require_realistic(profile: EconomicsProfile) -> EconomicsProfile:
    """Promotion gate: refuse non-realistic economics for performance claims."""
    if not isinstance(profile, EconomicsProfile):
        raise TypeError("economics profile is required")
    if not profile.venue_realistic:
        raise PermissionError(
            "economics profile %r v%s is not venue-realistic; it must never "
            "back a performance or promotion claim" % (profile.name, profile.version))
    return profile


def apply_costs(*, entry: float, direction: str, quantity: float,
                bars_held: int, profile: EconomicsProfile) -> CostedEntry:
    """Adversely adjust the entry and ledger every cost component."""
    if not isinstance(entry, (int, float)) or entry <= 0 or entry != entry:
        raise ValueError("entry must be a finite positive price")
    if direction not in ("BULLISH", "BEARISH"):
        raise ValueError("direction must be BULLISH or BEARISH")
    if not isinstance(quantity, (int, float)) or quantity <= 0:
        raise ValueError("quantity must be positive")
    if bars_held < 0:
        raise ValueError("bars_held must not be negative")
    notional = entry * quantity
    spread_cost = notional * profile.spread_bps / 10_000.0
    slippage_cost = notional * profile.slippage_bps / 10_000.0
    adverse = spread_cost + slippage_cost
    if direction == "BULLISH":
        actual_entry = entry + adverse / quantity
    else:
        actual_entry = entry - adverse / quantity
        if actual_entry <= 0:
            raise ValueError("adverse costs exceed entry price")
    commission_cost = (profile.commission_per_trade
                       + notional * profile.commission_rate)
    funding_cost = abs(notional) * profile.funding_rate_per_bar * bars_held
    return CostedEntry(
        actual_entry=actual_entry,
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        commission_cost=commission_cost,
        funding_cost=funding_cost,
        total_cost=adverse + commission_cost + funding_cost,
    )


def recheck_rr(*, entry: float, stop: float, target: float,
               actual_entry: float, direction: str,
               exit_mode: str = "FIXED_TARGET",
               symbol: str | None = None) -> RiskRewardRecheck:
    """Recompute R:R from the actual post-cost entry; enforce runtime policy.

    Phase-13 authority repair: this is a ZERO-COST DELEGATE of the
    single mandatory authority ``core.risk.costs.post_cost_rr`` —
    not a second formula.  The actual entry is passed through as
    the quoted entry with zero costs, so the math is identical by
    construction (proven by the cross-authority equivalence test).
    INTEGRATION STATUS remains NOT WIRED: no production, paper,
    backtest, or live caller invokes this function; the executable
    fill paths validate through ``costs.post_cost_rr`` at the
    ``TradeSimulator`` choke point.
    """
    from core.risk.costs import post_cost_rr

    verdict = post_cost_rr(direction=direction, entry=actual_entry,
                           stop=stop, target=target, quantity=1.0,
                           commission=0.0, slippage=0.0,
                           exit_mode=exit_mode, symbol=symbol)
    # NOTE: ``entry`` (pre-cost quote) is kept in the signature for
    # backward compatibility only; the verdict is computed from the
    # actual post-cost entry, exactly as before.
    _ = entry
    return RiskRewardRecheck(risk=verdict.risk, reward=verdict.reward,
                             rr=verdict.rr, allowed=verdict.allowed,
                             reason=verdict.reason)


def annotate_result(profile: EconomicsProfile,
                    extra: dict | None = None) -> dict:
    """Identify the economics profile behind any backtest/paper result."""
    record = {
        "economics_profile": profile.name,
        "economics_version": profile.version,
        "venue_realistic": profile.venue_realistic,
        "venue_source": profile.venue_source or "UNVERIFIED",
        "commission_per_trade": profile.commission_per_trade,
        "commission_rate": profile.commission_rate,
        "spread_bps": profile.spread_bps,
        "slippage_bps": profile.slippage_bps,
        "funding_rate_per_bar": profile.funding_rate_per_bar,
    }
    if extra:
        record.update(extra)
    return record
