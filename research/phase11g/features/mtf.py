"""11G-A multi-timeframe resampler + HTF context (REAL derived data).

15m candles are EXACTLY resampled from closed 1m bars (REAL derived,
not estimated, not proxy). A 15m bucket [T, T+900) becomes available
only at T+900: partially formed buckets NEVER influence decisions.
Each HTF candle records source_start/source_end/closed/
availability_timestamp. Gaps yield shorter buckets flagged partial
(deterministic); the incomplete terminal bucket is excluded.

HTF context (trend/range/BOS/volatility/liquidity) is computed over
CLOSED HTF candles only, then mapped onto 1m bars by availability.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from research.phase11f import features as F11
from research.phase11g.features import common as C

BUCKET = 900


def resample_15m(bars):
    """1m bars -> closed 15m candles (list of dicts). Deterministic."""
    buckets = {}
    order = []
    for b in bars:
        key = int(b["time"]) // BUCKET
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(b)
    out = []
    for n, key in enumerate(order):
        members = buckets[key]
        is_terminal = (n == len(order) - 1)
        # A bucket is closed only if a LATER bucket exists (its first
        # bar proves the boundary passed) — the terminal bucket is
        # incomplete by construction and excluded.
        if is_terminal:
            continue
        nxt = buckets[order[n + 1]][0]["time"]
        end = (key + 1) * BUCKET
        out.append({
            "time": key * BUCKET,
            "open": float(members[0]["open"]),
            "high": max(float(m["high"]) for m in members),
            "low": min(float(m["low"]) for m in members),
            "close": float(members[-1]["close"]),
            "volume": sum(float(m["volume"]) for m in members),
            "source_start": int(members[0]["time"]),
            "source_end": int(members[-1]["time"]),
            "n_source_bars": len(members),
            "partial": len(members) < 15,
            "closed": True,
            "availability_time": end,
            "availability_proof_bar": int(nxt),
        })
    return out


def htf_context(htf_bars):
    """Trend/range/volatility state per CLOSED HTF candle (past-only)."""
    closes = [c["close"] for c in htf_bars]
    out = []
    for i in range(len(htf_bars)):
        if i < 50:
            out.append(C.empty("htf_context", i, htf_bars, "11g.mtf",
                               reason="INSUFFICIENT_HISTORY"))
            continue
        window = closes[i - 50:i + 1]
        sma = sum(window[:-1]) / 50.0
        hi = max(c["high"] for c in htf_bars[i - 50:i + 1])
        lo = min(c["low"] for c in htf_bars[i - 50:i + 1])
        rng = hi - lo
        atr_like = sum(abs(htf_bars[j]["high"] - htf_bars[j]["low"])
                       for j in range(i - 14, i + 1)) / 15.0
        trend = "BULLISH" if closes[i] >= sma else "BEARISH"
        out.append(C.event(
            "htf_context",
            {"trend": trend, "range_high": hi, "range_low": lo,
             "range_size": rng, "volatility": atr_like},
            i, htf_bars, "11g.mtf", formation=i, confirmation=i,
            metadata={"lookback_htf": 50}))
    return out


def map_to_ltf(bars, htf_bars, htf_states):
    """For each 1m bar, the latest HTF state with
    availability_time <= bar time (else NO_EVENT)."""
    out = []
    for i, b in enumerate(bars):
        best = None
        for j, h in enumerate(htf_bars):
            if h["availability_time"] <= int(b["time"]):
                best = j
            else:
                break
        if best is None or htf_states[best]["status"] != "OK":
            out.append(C.empty("mtf_context", i, bars, "11g.mtf",
                               reason="NO_EVENT"))
            continue
        st = htf_states[best]
        out.append(C.event("mtf_context", st["value"], i, bars, "11g.mtf",
                           formation=i, confirmation=i,
                           metadata={"htf_index": best,
                                     "htf_time": htf_bars[best]["time"],
                                     "htf_availability": htf_bars[best]["availability_time"]}))
    return out
