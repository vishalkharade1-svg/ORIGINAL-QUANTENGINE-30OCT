"""Deterministic trailing-stop state machine shared by all simulated modes.

The engine is pure: it reads the completed candle close plus the persisted
trade state and returns a decision.  It never mutates the trade, never reads
future bars, and never loosens a stop.  Callers own persistence/audit storage.

Rules
-----
* Activation is measured against the *completed close* in initial-risk R.
* The candidate stop trails the completed close by ``distance_r`` initial-risk
  units.  The new stop becomes active on the next candle (the caller checks
  exits before calling the update).
* Improvements are monotonic and may be gated by ``step_r`` (minimum tightening
  per accepted update).
* When ``tick_size`` is configured the stop is rounded away from the market so
  it can never become more aggressive than the proposal (long: floor, short:
  ceil).  A rounded stop at/through the current close is rejected.
* Only ``R_DISTANCE`` is supported.  Unknown methods fail closed rather than
  silently selecting a different behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


METHOD_R_DISTANCE = "R_DISTANCE"
SUPPORTED_TRAILING_METHODS = (METHOD_R_DISTANCE,)


@dataclass(frozen=True, slots=True)
class TrailingStopConfig:
    activation_r: float
    distance_r: float
    method: str = METHOD_R_DISTANCE
    step_r: float = 0.0
    tick_size: float = 0.0

    def validate(self) -> "TrailingStopConfig":
        values = (self.activation_r, self.distance_r, self.step_r, self.tick_size)
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError("trailing configuration values must be finite")
        if float(self.activation_r) <= 0.0:
            raise ValueError("trailing activation R must be positive")
        if float(self.distance_r) <= 0.0:
            raise ValueError("trailing distance R must be positive")
        if float(self.step_r) < 0.0:
            raise ValueError("trailing step R cannot be negative")
        if float(self.tick_size) < 0.0:
            raise ValueError("tick size cannot be negative")
        if str(self.method or "").strip().upper() not in SUPPORTED_TRAILING_METHODS:
            raise ValueError(
                "unsupported trailing method %r (supported: %s)"
                % (self.method, ", ".join(SUPPORTED_TRAILING_METHODS))
            )
        return self


@dataclass(frozen=True, slots=True)
class TrailingDecision:
    accepted: bool
    reason: str
    old_stop: float
    candidate_stop: float
    new_stop: float
    peak_price: float
    favorable_r: float
    activated: bool
    tick_size: float


def round_stop_to_tick(price: float, tick_size: float, bullish: bool) -> float:
    """Round a proposed protective stop away from the market.

    Long stops round DOWN and short stops round UP, so tick normalisation can
    never tighten the stop beyond the raw proposal.  ``tick_size <= 0`` means
    the instrument tick is unknown and the raw proposal is returned.
    """
    tick = float(tick_size or 0.0)
    if tick <= 0.0:
        return float(price)
    units = float(price) / tick
    if bullish:
        units = math.floor(units + 1e-9)
    else:
        units = math.ceil(units - 1e-9)
    return round(units * tick, 10)


def evaluate_trailing_stop(
    *,
    direction: str,
    entry: float,
    initial_stop: float,
    current_stop: float,
    close: float,
    activated: bool,
    peak_price: float,
    config: TrailingStopConfig,
) -> TrailingDecision:
    """Return the next trailing decision without mutating trade state."""
    bullish = str(direction or "").upper() == "BULLISH"
    bearish = str(direction or "").upper() == "BEARISH"
    old_stop = float(current_stop)
    if not (bullish or bearish):
        return _reject("INVALID_DIRECTION", old_stop, old_stop, old_stop,
                       float(peak_price or 0.0), 0.0, bool(activated),
                       float(config.tick_size or 0.0))
    try:
        entry_f = float(entry)
        initial_f = float(initial_stop)
        old_f = float(current_stop)
        close_f = float(close)
        peak_f = float(peak_price or 0.0) or entry_f
        tick_f = float(config.tick_size or 0.0)
    except (TypeError, ValueError):
        return _reject("NON_FINITE_INPUT", old_stop, old_stop, old_stop,
                       float(peak_price or 0.0), 0.0, bool(activated),
                       float(config.tick_size or 0.0))
    if not all(math.isfinite(v) for v in (entry_f, initial_f, old_f, close_f, peak_f, tick_f)):
        return _reject("NON_FINITE_INPUT", old_f, old_f, old_f, peak_f,
                       0.0, bool(activated), tick_f)
    initial_risk = abs(entry_f - initial_f)
    if initial_risk <= 0.0:
        return _reject("ZERO_INITIAL_RISK", old_f, old_f, old_f, peak_f,
                       0.0, bool(activated), tick_f)
    try:
        config.validate()
    except ValueError:
        return _reject("INVALID_CONFIG", old_f, old_f, old_f, peak_f,
                       0.0, bool(activated), tick_f)

    peak_f = max(peak_f, close_f) if bullish else min(peak_f, close_f)
    favorable = (close_f - entry_f) if bullish else (entry_f - close_f)
    favorable_r = favorable / initial_risk
    now_activated = bool(activated) or favorable >= float(config.activation_r) * initial_risk

    if not now_activated:
        return _reject("NOT_ACTIVATED", old_f, old_f, old_f, peak_f,
                       favorable_r, False, tick_f)

    distance = float(config.distance_r) * initial_risk
    raw_candidate = (close_f - distance) if bullish else (close_f + distance)
    candidate = round_stop_to_tick(raw_candidate, tick_f, bullish)
    if bullish:
        improved = candidate > old_f
        step_delta = candidate - old_f
        too_close = candidate >= close_f
    else:
        improved = candidate < old_f
        step_delta = old_f - candidate
        too_close = candidate <= close_f
    if not improved:
        return _reject("NO_IMPROVEMENT", old_f, candidate, old_f, peak_f,
                       favorable_r, True, tick_f)
    required_step = float(config.step_r) * initial_risk
    if required_step > 0.0 and step_delta + 1e-12 < required_step:
        return _reject("STEP_NOT_MET", old_f, candidate, old_f, peak_f,
                       favorable_r, True, tick_f)
    if too_close:
        return _reject("STOP_AT_OR_THROUGH_PRICE", old_f, candidate, old_f,
                       peak_f, favorable_r, True, tick_f)
    return TrailingDecision(
        accepted=True,
        reason="UPDATED",
        old_stop=old_f,
        candidate_stop=candidate,
        new_stop=candidate,
        peak_price=peak_f,
        favorable_r=favorable_r,
        activated=True,
        tick_size=tick_f,
    )


def _reject(reason, old_stop, candidate, new_stop, peak, favorable_r,
            activated, tick):
    return TrailingDecision(
        accepted=False,
        reason=reason,
        old_stop=float(old_stop),
        candidate_stop=float(candidate),
        new_stop=float(new_stop),
        peak_price=float(peak or 0.0),
        favorable_r=float(favorable_r or 0.0),
        activated=bool(activated),
        tick_size=float(tick or 0.0),
    )
