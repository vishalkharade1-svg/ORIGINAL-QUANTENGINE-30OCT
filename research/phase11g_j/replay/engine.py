"""11G-J causal REAL trade replay + feature engine (v1, frozen semantics).

The replay holds an append-only, deterministically ordered event list.
All features are pure functions of an event PREFIX (events with
order_key <= T): appending future events cannot alter past features
(proven by tests). No strategies, no economics, no thresholds-as-
parameters — windows below are feature resolutions, not tuned levels.

Feature classification: delta/CVD/volumes/footprint/imbalance/absorption
indicators here are DERIVED_FROM_REAL (directly observed trades) except
raw price/quantity/side/timestamp which are REAL.
"""

from __future__ import annotations

from research.phase11g_j.replay.events import FEATURE_VERSION

WINDOWS_MS = {
    "prefix": None,
    "1s": 1_000,
    "5s": 5_000,
    "15s": 15_000,
    "30s": 30_000,
    "1m": 60_000,
    "5m": 300_000,
}


class TradeReplay:
    """Append-only causal replay over order_key-sorted RealTrades."""

    def __init__(self, trades):
        ordered = sorted(trades, key=lambda t: t.order_key())
        self._trades = list(ordered)
        self.feature_version = FEATURE_VERSION

    def __len__(self):
        return len(self._trades)

    def prefix(self, n):
        return TradeReplay(self._trades[:n])

    def prefix_before(self, ms):
        return TradeReplay([t for t in self._trades if t.event_ms < ms])

    def prefix_through(self, ms):
        return TradeReplay([t for t in self._trades if t.event_ms <= ms])

    def state_hash(self):
        import hashlib
        import json
        blob = json.dumps(
            [[t.event_ms, t.transact_raw, t.source_index, t.price,
              t.quantity, t.aggressor_side, t.trade_id]
             for t in self._trades], sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()

    def _window(self, end_ms, window_ms):
        if window_ms is None:
            return [t for t in self._trades if t.event_ms <= end_ms]
        start = end_ms - window_ms
        return [t for t in self._trades if start < t.event_ms <= end_ms]

    def delta(self, end_ms, window="1m"):
        """{buy, sell, total, delta, delta_pct} over (end-window, end]."""
        if window not in WINDOWS_MS:
            raise ValueError("unknown window: %r" % window)
        buy = sell = 0.0
        for t in self._window(end_ms, WINDOWS_MS[window]):
            if t.aggressor_side == "buy":
                buy += t.quantity
            else:
                sell += t.quantity
        total = buy + sell
        return {"buy_volume": buy, "sell_volume": sell, "total_volume": total,
                "delta": buy - sell,
                "delta_pct": ((buy - sell) / total) if total > 0 else 0.0,
                "window": window, "end_ms": end_ms,
                "classification": "DERIVED_FROM_REAL",
                "feature_version": FEATURE_VERSION}

    def cvd(self, end_ms=None):
        """ running buy-minus-sell over the replayed prefix.

        NOTE: full-prefix scan per call is O(n); the certified runner
        below (cvd_series) accumulates in one pass. Values identical.
        """
        running, out = 0.0, []
        for t in self._trades:
            if end_ms is not None and t.event_ms > end_ms:
                break
            running += t.quantity if t.aggressor_side == "buy" else -t.quantity
            out.append((t.event_ms, running))
        return out

    def footprint(self, bucket_start_ms, bucket_end_ms, tick=0.01):
        """{price: {buy, sell, total, delta}} for trades in [start, end)."""
        levels = {}
        n = 0
        for t in self._trades:
            if not (bucket_start_ms <= t.event_ms < bucket_end_ms):
                continue
            px = round(t.price / tick) * tick
            px = round(px, 8)
            lvl = levels.setdefault(px, {"buy": 0.0, "sell": 0.0})
            lvl[t.aggressor_side] += t.quantity
            n += 1
        for lvl in levels.values():
            lvl["total"] = lvl["buy"] + lvl["sell"]
            lvl["delta"] = lvl["buy"] - lvl["sell"]
        return {"levels": levels, "n_trades": n,
                "classification": "DERIVED_FROM_REAL",
                "feature_version": FEATURE_VERSION}

    def imbalance(self, end_ms, window="1m"):
        """Trade imbalance (aggressor-side). NEVER 'order-book imbalance'."""
        d = self.delta(end_ms, window)
        total = d["total_volume"]
        return {"trade_imbalance": (d["delta"] / total) if total > 0 else 0.0,
                "buy_volume": d["buy_volume"], "sell_volume": d["sell_volume"],
                "window": window, "end_ms": end_ms,
                "classification": "DERIVED_FROM_REAL",
                "feature_version": FEATURE_VERSION}

    def absorption(self, end_ms, window="1m", vol_mult=3.0,
                   progress_ratio=0.25, trail_windows=20):
        """TRADE-BASED absorption indicator (not proof of resting orders).

        Frozen definitional form: window volume >= vol_mult * median of
        the previous trail_windows same-length windows AND price range
        over the window <= progress_ratio * median window range.
        Returns dict with evidence fields or {'present': False}.
        """
        if window not in WINDOWS_MS or WINDOWS_MS[window] is None:
            raise ValueError("absorption needs a fixed window")
        w = WINDOWS_MS[window]
        vols, ranges = [], []
        for k in range(trail_windows + 1):
            e = end_ms - k * w
            ts = self._window(e, w)
            vols.append(sum(t.quantity for t in ts))
            px = [t.price for t in ts]
            ranges.append((max(px) - min(px)) if px else 0.0)
        vols.reverse()
        ranges.reverse()
        cur_v, cur_r = vols[-1], ranges[-1]
        med_v = sorted(vols[:-1])[len(vols[:-1]) // 2]
        med_r = sorted(ranges[:-1])[len(ranges[:-1]) // 2]
        present = bool(med_v > 0 and cur_v >= vol_mult * med_v
                       and (med_r <= 0 or cur_r <= progress_ratio * med_r))
        return {"present": present, "window_volume": cur_v,
                "median_volume": med_v, "window_range": cur_r,
                "median_range": med_r, "end_ms": end_ms,
                "classification": "DERIVED_FROM_REAL",
                "note": "trade-based indicator, not resting-order proof",
                "feature_version": FEATURE_VERSION}

    def aggression_event(self, end_ms, window="1m", vol_mult=5.0,
                         trail_windows=20):
        """TRADE_AGGRESSION_EVENT: window buy-or-sell volume >= vol_mult
        times its trailing median (per side). Directional, no liquidity
        claim (never labeled a liquidity sweep)."""
        if window not in WINDOWS_MS or WINDOWS_MS[window] is None:
            raise ValueError("aggression needs a fixed window")
        w = WINDOWS_MS[window]
        buys, sells = [], []
        for k in range(trail_windows + 1):
            e = end_ms - k * w
            b = sum(t.quantity for t in self._window(e, w)
                    if t.aggressor_side == "buy")
            s = sum(t.quantity for t in self._window(e, w)
                    if t.aggressor_side == "sell")
            buys.append(b)
            sells.append(s)
        buys.reverse()
        sells.reverse()
        med_b = sorted(buys[:-1])[len(buys[:-1]) // 2]
        med_s = sorted(sells[:-1])[len(sells[:-1]) // 2]
        up = bool(med_b > 0 and buys[-1] >= vol_mult * med_b)
        dn = bool(med_s > 0 and sells[-1] >= vol_mult * med_s)
        direction = "up" if up and not dn else ("down" if dn and not up else None)
        return {"present": direction is not None, "direction": direction,
                "buy_volume": buys[-1], "sell_volume": sells[-1],
                "end_ms": end_ms, "classification": "DERIVED_FROM_REAL",
                "feature_version": FEATURE_VERSION}


def cvd_series(trades):
    """One-pass CVD accumulation (identical to per-call cvd())."""
    running, out = 0.0, []
    for t in sorted(trades, key=lambda x: x.order_key()):
        running += t.quantity if t.aggressor_side == "buy" else -t.quantity
        out.append((t.event_ms, running))
    return out
