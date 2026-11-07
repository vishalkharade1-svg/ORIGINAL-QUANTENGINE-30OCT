"""11G-L market context builder (frozen-spec inputs, causal only).

Builds ONCE per dataset, BEFORE any signal evaluation:
- 1m OHLCV bars (certified klines raw) with ATR14, swings/BOS state,
  displacement flags, Donchian prior-range state.
- Trade-derived minute aggregates (buy/sell/total/delta per minute),
  prefix sums, per-minute price->volume maps (for 60m POC), CVD series,
  trailing medians. All causal: value[i] uses events with ms in
  minute[i] or earlier only.

No thresholds, no signals, no economics here.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f import features as F11  # noqa: E402


class MarketContext:
    def __init__(self, bars, trades):
        self.bars = list(bars)
        self.n = len(bars)
        self.times = [int(b["time"]) for b in bars]
        self.opens = [float(b["open"]) for b in bars]
        self.highs = [float(b["high"]) for b in bars]
        self.lows = [float(b["low"]) for b in bars]
        self.closes = [float(b["close"]) for b in bars]
        # --- OHLCV-derived (certified calls) ---
        self.atr = F11.atr14(bars)
        self.swings = F11.swings(bars, 3, 3)
        self.disp2 = F11.displacement(bars, 2.0, self.atr)
        self.disp1 = F11.displacement(bars, 1.0, self.atr)
        # --- trade-derived minute aggregates (causal bins) ---
        per_min = {}
        for t in trades:
            m = (int(t.event_ms) // 60000) * 60
            e = per_min.get(m)
            if e is None:
                e = per_min[m] = {"buy": 0.0, "sell": 0.0, "levels": {}}
            if t.aggressor_side == "buy":
                e["buy"] += t.quantity
            else:
                e["sell"] += t.quantity
            px = round(t.price, 2)
            lvl = e["levels"].get(px)
            if lvl is None:
                e["levels"][px] = {"buy": 0.0, "sell": 0.0}
            e["levels"][px][t.aggressor_side] += t.quantity
        self.min_buy = []
        self.min_sell = []
        self.min_total = []
        self.min_levels = []
        for tm in self.times:
            e = per_min.get(tm, {"buy": 0.0, "sell": 0.0, "levels": {}})
            self.min_buy.append(e["buy"])
            self.min_sell.append(e["sell"])
            self.min_total.append(e["buy"] + e["sell"])
            self.min_levels.append(e["levels"])
        # prefix sums for O(1) causal windows
        self._pre_buy, self._pre_sell, s1, s2 = [0.0], [0.0], 0.0, 0.0
        for b, s in zip(self.min_buy, self.min_sell):
            s1 += b
            s2 += s
            self._pre_buy.append(s1)
            self._pre_sell.append(s2)
        # CVD per minute (causal cumulative)
        self.cvd = []
        run = 0.0
        for b, s in zip(self.min_buy, self.min_sell):
            run += b - s
            self.cvd.append(run)

    def window_vol(self, i, minutes):
        """(buy, sell, total, delta) over the `minutes` minutes ending WITH
        bar i (inclusive — all available at bar i close)."""
        lo = max(0, i - minutes + 1)
        b = self._pre_buy[i + 1] - self._pre_buy[lo]
        s = self._pre_sell[i + 1] - self._pre_sell[lo]
        return b, s, b + s, b - s

    def trailing_median(self, series, i, window):
        """Median over strictly-prior bars (excludes i; no self-reference)."""
        lo = max(0, i - window)
        vals = series[lo:i]
        if not vals:
            return None
        s = sorted(vals)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0

    def minute_volumes(self, i, minutes):
        lo = max(0, i - minutes)
        return [self.min_buy[j] + self.min_sell[j] for j in range(lo, i)]

    def minute_ranges(self, i, minutes):
        lo = max(0, i - minutes)
        return [self.highs[j] - self.lows[j] for j in range(lo, i)]

    def cvd_slope(self, i, minutes):
        """CVD[i] - CVD[i-minutes] (per-minute CVD array, both <= i)."""
        j = max(0, i - minutes)
        return self.cvd[i] - self.cvd[j]

    def poc_60m(self, i):
        """POC level of trailing 60 minutes ending at bar i (exclusive of
        future; uses minute price maps). Returns (level, volume) or None."""
        lo = max(0, i - 60)
        agg = {}
        for j in range(lo, i):
            for px, lvl in self.min_levels[j].items():
                agg[px] = agg.get(px, 0.0) + lvl["buy"] + lvl["sell"]
        if not agg:
            return None
        best = max(agg.items(), key=lambda kv: (kv[1], -kv[0]))
        return best
