"""11G-E order-flow truth model (REAL only with source data).

Classification rule: a feature is REAL only when its required source
events exist with the required fields. Candle-derived directional
estimates are PROXY (explicit label, separate claim). Without source
data the feature is UNAVAILABLE — never a silent proxy fallback.

Footprint/delta/CVD/imbalance/absorption builders below operate on
TradeEvents (SYNTHETIC-labeled unit tests today; future REAL feeds).
Passing candle aggregates raises UnavailableData.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11g.events.canonical import TradeEvent

REAL = "REAL"
PROXY = "PROXY"
UNAVAILABLE = "UNAVAILABLE"


class UnavailableData(RuntimeError):
    pass


def classify(feature, available_source):
    """available_source: 'trades' | 'quotes' | 'book' | 'ohlcv' | None."""
    needs = {
        "delta": "trades", "cvd": "trades", "footprint": "trades",
        "absorption": "trades", "imbalance": "quotes",
        "stacked_imbalance": "book", "volume_at_price": "trades",
        "spread": "quotes", "depth_imbalance": "book",
    }
    if feature not in needs:
        raise ValueError("unknown order-flow feature: %r" % feature)
    if available_source is None:
        return UNAVAILABLE
    if available_source == needs[feature]:
        return REAL
    # Only directional-volume-style estimates may be OHLCV proxies;
    # spread/depth/imbalance have no meaningful candle proxy.
    if available_source == "ohlcv" and feature in (
            "delta", "cvd", "footprint", "absorption"):
        return PROXY
    return UNAVAILABLE


def require_trades(events):
    if not events:
        raise UnavailableData("no trade events available")
    for e in events:
        if not isinstance(e, TradeEvent):
            raise UnavailableData("non-trade event in footprint input")
        if e.side not in ("buy", "sell") or e.price is None or e.quantity is None:
            raise UnavailableData("trade missing side/price/quantity")
    return True


def footprint_for_bar(trades, bar_open, bar_close):
    """Per-bar footprint from TradeEvents within [bar_open, bar_close).

    Returns {levels: {price: {buy, sell, total, delta}}, bar_delta,
    bar_volume, provenance}. Prices bucketed at tick 0.01 (documented).
    """
    require_trades(trades)
    window = [t for t in trades if bar_open <= t.event_timestamp < bar_close]
    levels = {}
    for t in window:
        px = round(float(t.price), 2)
        lvl = levels.setdefault(px, {"buy": 0.0, "sell": 0.0})
        lvl[t.side] += float(t.quantity)
    for px, lvl in levels.items():
        lvl["total"] = lvl["buy"] + lvl["sell"]
        lvl["delta"] = lvl["buy"] - lvl["sell"]
    return {"levels": levels,
            "bar_delta": sum(l["delta"] for l in levels.values()),
            "bar_volume": sum(l["total"] for l in levels.values()),
            "n_trades": len(window),
            "provenance": REAL}


def cumulative_delta(bar_footprints):
    out, running = [], 0.0
    for fp in bar_footprints:
        running += fp["bar_delta"]
        out.append(running)
    return out


def diagonal_imbalance(levels, ratio=3.0):
    """Bullish diagonal: bid level volume >= ratio * ask level one tick
    above (classical stacked-diagonal definition, documented). Levels:
    {price: {'buy':, 'sell':}}. Returns list of (price, direction)."""
    prices = sorted(levels)
    out = []
    for i, px in enumerate(prices):
        if i + 1 < len(prices) and levels[px]["buy"] >= ratio * levels[prices[i + 1]]["sell"] \
                and levels[prices[i + 1]]["sell"] > 0:
            out.append((px, "bullish"))
        if i > 0 and levels[px]["sell"] >= ratio * levels[prices[i - 1]]["buy"] \
                and levels[prices[i - 1]]["buy"] > 0:
            out.append((px, "bearish"))
    return out


def absorption_candidates(trades, bar_open, bar_close, vol_mult=3.0,
                          progress_atr=0.5, median_window=20, history_vols=None):
    """Absorption = high aggressive volume + limited price progress.

    Frozen definitional form: bar volume >= vol_mult * trailing median
    AND |close-open| <= progress_atr * bar_range. Requires trades for
    volume and OHLC for prices (mixed REAL measurement, labeled).
    Returns event dict or None. Thresholds are definitional, not tuned.
    """
    require_trades(trades)
    window = [t for t in trades if bar_open <= t.event_timestamp < bar_close]
    vol = sum(float(t.quantity) for t in window)
    base = list(history_vols or []) + [vol]
    base = base[-median_window:]
    med = sorted(base)[len(base) // 2]
    return {"bar_volume": vol, "median": med,
            "high_volume": bool(med > 0 and vol >= vol_mult * med),
            "provenance": REAL if window else UNAVAILABLE}
