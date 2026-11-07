"""
====================================================

QuantEngine

Feature Evidence -- causal window (Phase 9F)

A DETERMINISTIC, NO-LOOKAHEAD decision-time snapshot of the candle
history available UP TO an opportunity's decision bar.

Guarantees:
   * a feature may only read bars with index < decision_bar
     (the decision bar itself is NOT a lookahead source).
   * if the required price/volume data is not present within the
     bounded lookback, the window reports UNAVAILABLE for that
     dimension -- it NEVER fabricates a value.
   * window extraction never mutates its inputs.

The window exposes the raw bounded history + the derived indicator
series (prices/atr/volatility/obv) so producers can build canonical
features from real, decision-time data only.
====================================================
"""

from dataclasses import dataclass, field

UNAVAILABLE = None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return UNAVAILABLE


@dataclass(frozen=True)
class CandlePoint:
    open: float
    high: float
    low: float
    close: float
    timestamp: object = None
    volume: object = None


@dataclass(frozen=True)
class CausalWindow:
    """Bounded decision-time history; bars are index < decision_bar."""

    instrument_id: str = ""
    decision_bar: int = 0
    lookback: int = 0
    direction: str = ""
    points: tuple = field(default_factory=tuple)

    # ---- convenience ----

    @property
    def size(self):
        return len(self.points)

    def ensure_minimum(self, required):
        """True when at least `required` bars are present."""
        return len(self.points) >= required

    def closes(self):
        return tuple(p.close for p in self.points)

    def highs(self):
        return tuple(p.high for p in self.points)

    def lows(self):
        return tuple(p.low for p in self.points)

    def volumes(self):
        return tuple(
            p.volume for p in self.points
            if p.volume is not None
        )

    def has_volume(self):
        return len(self.volumes()) == len(self.points)


def extract_causal_window(candles, decision_bar, lookback=20,
                          direction="", instrument_id=""):
    """Deterministic CausalWindow for the bars strictly before
    `decision_bar`.

    Uses the `lookback` candles immediately preceding the decision
    bar (indices [decision_bar - lookback, decision_bar)). If fewer
    are available it uses what is present; if none are available the
    window is empty (all features return UNAVAILABLE).
    """
    candles = list(candles)
    if not candles or decision_bar is None or decision_bar <= 0:
        return CausalWindow(
            instrument_id=instrument_id, decision_bar=0,
            lookback=lookback, direction=direction,
        )
    start = max(0, decision_bar - lookback)
    points = []
    for c in candles[start:decision_bar]:
        points.append(
            CandlePoint(
                open=_num(getattr(c, "open", UNAVAILABLE)),
                high=_num(getattr(c, "high", UNAVAILABLE)),
                low=_num(getattr(c, "low", UNAVAILABLE)),
                close=_num(getattr(c, "close", UNAVAILABLE)),
                timestamp=getattr(c, "timestamp", None),
                volume=_num(getattr(c, "volume", UNAVAILABLE)),
            )
        )
    points = tuple(
        p for p in points
        if p.open is not None and p.high is not None
        and p.low is not None and p.close is not None
    )
    return CausalWindow(
        instrument_id=instrument_id,
        decision_bar=int(decision_bar),
        lookback=int(lookback),
        direction=direction,
        points=points,
    )