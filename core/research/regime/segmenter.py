"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- segmenter

Turns frozen 9A OpportunityRecords (+ the supplied candle series) into
RegimeObservations segmented by (a) the deterministic 9C opportunity
category and (b) the decision-time MarketRegime.

Only decision-time facts are used: the decision bar comes from the
record's own order/setup fields; the regime window ENDS AT that bar.
An observation without a usable decision bar keeps an empty regime
(honest data-gate) and is never silently assigned a fake one.
====================================================
"""

from core.research.counterfactual.opportunity_categories import (
    classify_opportunity,
)
from core.research.regime.regime_types import (
    RegimeObservation,
    REGIME_DIMENSIONS,
)
from core.research.regime.detector import detect_regime


def _value(record, section, key, default=""):
    data = getattr(record, section, None)
    if not isinstance(data, dict):
        return default
    try:
        return data.get(key, default)
    except AttributeError:
        return default


def _field(record, name, default=""):
    value = getattr(record, name, None)
    return default if value is None else value


def decision_bar(record):
    """Deterministic decision bar of a record (filled bar first, else
    the setup bar; None when neither is present)."""
    filled = _value(record, "order", "filled_bar")
    if filled is not None and filled != "":
        try:
            return int(filled)
        except (TypeError, ValueError):
            pass
    bar = _value(record, "setup", "bar")
    if bar is not None and bar != "":
        try:
            return int(bar)
        except (TypeError, ValueError):
            pass
    return None


def stop_level(record):
    return _value(record, "setup", "stop_loss")


def direction(record):
    d = _field(record, "direction")
    if d in ("BULLISH", "BEARISH"):
        return d
    return d.upper() if isinstance(d, str) else ""


def _trade(record):
    trade = getattr(record, "trade", None) or {}
    if not isinstance(trade, dict):
        return {}
    return trade


def observed_result(record):
    result = (_trade(record).get("result") or "").upper()
    return result if result in ("WIN", "LOSS") else ""


def observed_r(record):
    r = _trade(record).get("r")
    try:
        return float(r) if r is not None else None
    except (TypeError, ValueError):
        return None


def segment_observations(records, candles, lookback=40, atr_period=14):
    """Deterministic list of RegimeObservation (one per record), each
    carrying only its data-gated available regime labels."""
    candles = list(candles or ())
    observations = []
    for rec in records or ():
        cat = classify_opportunity(rec)
        bar = decision_bar(rec)
        regime = {}
        if bar is not None and candles:
            mr = detect_regime(
                candles, bar, lookback=lookback, atr_period=atr_period,
                stop_level=stop_level(rec),
                direction=direction(rec),
            )
            regime = mr.available()
        observations.append(RegimeObservation(
            observation_id=getattr(rec, "canonical_id", "") or "",
            decision_bar=bar,
            category=cat,
            result=observed_result(rec),
            r=observed_r(rec),
            direction=direction(rec),
            symbol=_field(rec, "instrument_id", "UNKNOWN"),
            timeframe=_field(rec, "timeframe"),
            regime=regime,
        ))
    return tuple(observations)


def in_cell(observations, dimension, label):
    """Order-preserving filter of observations inside one regime cell."""
    return tuple(o for o in observations if o.in_regime(dimension, label))


def cell_labels(observations, dimension):
    """Sorted distinct labels observed for one dimension."""
    labels = {o.regime.get(dimension) for o in observations
              if dimension in o.regime}
    return tuple(sorted(str(x) for x in labels))


def regime_coverage(observations):
    """{dimension: {"available": n, "total": n, "rate": float}} over
    every regime dimension + overall observation count."""
    total = len(observations)
    out = {"observations": total}
    for dim in REGIME_DIMENSIONS:
        available = sum(1 for o in observations if dim in o.regime)
        out[dim] = {
            "available": available,
            "total": total,
            "rate": (available / total) if total else 0.0,
        }
    return out


def by_category(observations):
    """Deterministically ordered category counts."""
    counts = {}
    for o in observations:
        counts[o.category] = counts.get(o.category, 0) + 1
    return {k: counts[k] for k in sorted(counts)}