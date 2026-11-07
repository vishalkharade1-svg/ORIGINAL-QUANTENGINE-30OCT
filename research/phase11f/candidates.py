"""Phase 11F strategy candidates (research-only).

Each candidate maps a signal bar to LIMIT-touch orders executed
by the production Backtester (touch fills, invalidation,
expiry, SL-first ambiguity — all certified machinery).
LIMIT-at-level is used uniformly (see methodology note on
NBO approximation); candidates never see future bars.

Ablations listed per candidate are strict component removals
(never additions), pre-registered here.
"""

from research.phase11f import features as F


def _atr(bars, cache):
    if "atr" not in cache:
        cache["atr"] = F.atr14(bars)
    return cache["atr"]


class _Base:
    id = "H11F-000"
    params = {}
    # Cross-bar state keys (pending retests, last confirmed swings).
    # Feature arrays are causal prefix-stable (11F-2), so when the
    # harness feeds a growing prefix of the SAME dataset, these must
    # survive feature rebuilds; otherwise armed setups could never
    # trigger. 11F-4 fix (mechanics only; economics/params untouched).
    _STATE_KEYS = ("pend", "last_high", "last_low")

    def __init__(self, **overrides):
        self.cfg = dict(self.params)
        self.cfg.update(overrides)
        self._feat = {}

    def _key(self, bars):
        return (len(bars), bars[0]["time"] if bars else 0,
                tuple(sorted(self.cfg.items())))

    def prepare(self, bars):
        key = self._key(bars)
        if self._feat.get("key") == key:
            return
        old_key = self._feat.get("key")
        continuing = (
            old_key is not None and old_key[1] == key[1]
            and old_key[2] == key[2] and key[0] >= old_key[0])
        saved = {k: self._feat[k] for k in self._STATE_KEYS if k in self._feat}
        self._feat = {"key": key}
        self._build(bars, self._feat)
        if continuing:
            # Same dataset + config, prefix extended: feature values
            # at prior indices are unchanged (causal), so prior state
            # remains valid and must be retained.
            for k, v in saved.items():
                self._feat[k] = v

    def signals(self, idx, bars, ctx):
        self.prepare(bars)
        return self._signals(idx, bars, self._feat) or []

    def ablations(self):
        return [("full", {})]

    @staticmethod
    def _sig(direction, entry, stop, tp, setup_id, confidence=80.0):
        return {"direction": direction, "entry": float(entry),
                "stop": float(stop), "take_profit": float(tp),
                "setup_id": setup_id, "confidence": confidence}


class SweepReversal(_Base):
    """H11F-001: equal-level sweep + close-back-inside reclaim."""

    id = "H11F-001"
    params = {"lookback": 50, "tolerance_atr": 0.1,
              "buffer_atr": 0.25, "rr": 2.0}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        feat["sw"] = F.sweeps(bars, self.cfg["lookback"],
                              self.cfg["tolerance_atr"], atr)

    def _signals(self, idx, bars, feat):
        sw = feat["sw"][idx]
        if sw is None or idx < 1:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        entry = float(bars[idx]["close"])
        buf = self.cfg["buffer_atr"] * atr
        if sw["direction"] == "long":
            stop = sw["extreme"] - buf
            risk = entry - stop
            if risk <= 0:
                return []
            tp = entry + self.cfg["rr"] * risk
            return [self._sig("BULLISH", entry, stop, tp,
                              "%s-%d" % (self.id, idx))]
        stop = sw["extreme"] + buf
        risk = stop - entry
        if risk <= 0:
            return []
        tp = entry - self.cfg["rr"] * risk
        return [self._sig("BEARISH", entry, stop, tp,
                          "%s-%d" % (self.id, idx))]


class SweepDisplacementFVG(_Base):
    """H11F-002: sweep + displacement + FVG-edge retest (LIMIT)."""

    id = "H11F-002"
    params = {"lookback": 50, "tolerance_atr": 0.1,
              "displacement_atr": 2.0, "buffer_atr": 0.25, "rr": 2.0,
              "wait": 5, "use_sweep": True, "use_fvg": True}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        feat["sw"] = F.sweeps(bars, self.cfg["lookback"],
                              self.cfg["tolerance_atr"], atr)
        feat["disp"] = F.displacement(bars, self.cfg["displacement_atr"], atr)
        feat["fvg"] = F.fvg_zones(bars)
        feat["pend"] = {}

    def _signals(self, idx, bars, feat):
        out = []
        # New setup: displacement bar (optionally post-sweep) + FVG.
        if feat["disp"][idx]:
            direction = ("BULLISH" if float(bars[idx]["close"]) >= float(bars[idx]["open"])
                         else "BEARISH")
            side = "long" if direction == "BULLISH" else "short"
            swept = True
            if self.cfg["use_sweep"]:
                swept = any(feat["sw"][j] is not None and feat["sw"][j]["direction"] == side
                            for j in range(max(0, idx - 3), idx + 1))
            fvg = feat["fvg"][idx] if self.cfg["use_fvg"] else None
            ok = (not self.cfg["use_fvg"]) or (
                fvg is not None and fvg["direction"] == side)
            atr = feat["atr"][idx]
            if swept and ok and atr is not None:
                if self.cfg["use_fvg"]:
                    edge = fvg["bottom"] if direction == "BULLISH" else fvg["top"]
                    far = fvg["top"] if direction == "BULLISH" else fvg["bottom"]
                else:
                    edge = float(bars[idx]["close"])
                    far = edge
                buf = self.cfg["buffer_atr"] * atr
                if direction == "BULLISH":
                    stop = far - buf
                    risk = edge - stop
                    tp = edge + self.cfg["rr"] * risk if risk > 0 else None
                else:
                    stop = far + buf
                    risk = stop - edge
                    tp = edge - self.cfg["rr"] * risk if risk > 0 else None
                if tp is not None:
                    feat["pend"][direction] = {
                        "edge": edge, "stop": stop, "tp": tp,
                        "until": idx + self.cfg["wait"], "armed": idx}
        # Retest triggers (LIMIT touch), never on the setup bar itself.
        for direction in ("BULLISH", "BEARISH"):
            pend = feat["pend"].get(direction)
            if pend is None:
                continue
            if idx <= pend["armed"] or idx > pend["until"]:
                if idx > pend["until"]:
                    feat["pend"].pop(direction, None)
                continue
            lo, hi = float(bars[idx]["low"]), float(bars[idx]["high"])
            if lo <= pend["edge"] <= hi:
                out.append(self._sig(
                    direction, pend["edge"], pend["stop"], pend["tp"],
                    "%s-%s-%d" % (self.id, direction[:4], idx)))
                feat["pend"].pop(direction, None)
                break
        return out

    def ablations(self):
        return [("full", {}),
                ("no-sweep", {"use_sweep": False}),
                ("no-fvg", {"use_fvg": False})]


class WyckoffSpring(_Base):
    """H11F-003: range spring + reclaim (mirror H11F-004 upthrust)."""

    id = "H11F-003"
    params = {"range_lookback": 50, "min_hold_bars": 30, "long_only": True}

    def _build(self, bars, feat):
        feat["rng"] = F.range_state(bars, self.cfg["range_lookback"],
                                    self.cfg["min_hold_bars"])

    def _signals(self, idx, bars, feat):
        rng = feat["rng"][idx]
        if rng is None or idx < 1:
            return []
        lo, hi = float(bars[idx]["low"]), float(bars[idx]["high"])
        cl = float(bars[idx]["close"])
        if lo < rng["low"] and cl > rng["low"]:
            entry = cl
            stop = lo
            tp = rng["high"]
            if tp <= entry or entry - stop <= 0:
                return []
            return [self._sig("BULLISH", entry, stop, tp,
                              "%s-%d" % (self.id, idx))]
        return []


class WyckoffUpthrust(_Base):
    """H11F-004."""

    id = "H11F-004"
    params = {"range_lookback": 50, "min_hold_bars": 30}

    def _build(self, bars, feat):
        feat["rng"] = F.range_state(bars, self.cfg["range_lookback"],
                                    self.cfg["min_hold_bars"])

    def _signals(self, idx, bars, feat):
        rng = feat["rng"][idx]
        if rng is None or idx < 1:
            return []
        lo, hi = float(bars[idx]["low"]), float(bars[idx]["high"])
        cl = float(bars[idx]["close"])
        if hi > rng["high"] and cl < rng["high"]:
            entry = cl
            stop = hi
            tp = rng["low"]
            if tp >= entry or stop - entry <= 0:
                return []
            return [self._sig("BEARISH", entry, stop, tp,
                              "%s-%d" % (self.id, idx))]
        return []


class OrderBlockSweep(_Base):
    """H11F-005: sweep + displacement, OB-edge retest (LIMIT)."""

    id = "H11F-005"
    params = {"lookback": 50, "tolerance_atr": 0.1,
              "displacement_atr": 2.0, "buffer_atr": 0.25, "rr": 2.0,
              "wait": 5, "use_sweep": True}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        feat["sw"] = F.sweeps(bars, self.cfg["lookback"],
                              self.cfg["tolerance_atr"], atr)
        feat["disp"] = F.displacement(bars, self.cfg["displacement_atr"], atr)
        feat["pend"] = {}

    def _signals(self, idx, bars, feat):
        out = []
        if feat["disp"][idx]:
            direction = ("BULLISH" if float(bars[idx]["close"]) >= float(bars[idx]["open"])
                         else "BEARISH")
            side = "long" if direction == "BULLISH" else "short"
            swept = True
            if self.cfg["use_sweep"]:
                swept = any(feat["sw"][j] is not None and feat["sw"][j]["direction"] == side
                            for j in range(max(0, idx - 3), idx + 1))
            ob = F.order_block_before(bars, idx, side)
            atr = feat["atr"][idx]
            if swept and ob is not None and atr is not None:
                buf = self.cfg["buffer_atr"] * atr
                if direction == "BULLISH":
                    edge, far = ob["edge"], ob["extreme"]
                    stop = far - buf
                    risk = edge - stop
                    if risk <= 0:
                        return out
                    tp = edge + self.cfg["rr"] * risk
                else:
                    edge, far = ob["edge"], ob["extreme"]
                    stop = far + buf
                    risk = stop - edge
                    if risk <= 0:
                        return out
                    tp = edge - self.cfg["rr"] * risk
                feat["pend"][direction] = {
                    "edge": edge, "stop": stop, "tp": tp,
                    "until": idx + self.cfg["wait"], "armed": idx}
        for direction in ("BULLISH", "BEARISH"):
            pend = feat["pend"].get(direction)
            if pend is None:
                continue
            if idx <= pend["armed"] or idx > pend["until"]:
                if idx > pend["until"]:
                    feat["pend"].pop(direction, None)
                continue
            lo, hi = float(bars[idx]["low"]), float(bars[idx]["high"])
            if lo <= pend["edge"] <= hi:
                out.append(self._sig(
                    direction, pend["edge"], pend["stop"], pend["tp"],
                    "%s-%s-%d" % (self.id, direction[:4], idx)))
                feat["pend"].pop(direction, None)
                break
        return out

    def ablations(self):
        return [("full", {}), ("no-sweep", {"use_sweep": False})]


class BreakerRetest(_Base):
    """H11F-006: support/resistance reclaim cross + retest (LIMIT).

    The most recent confirmed swing extreme acts as the level;
    a close crossing back through it arms a pending retest
    entry (breaker polarity)."""

    id = "H11F-006"
    params = {"swing_left": 3, "swing_right": 3,
              "buffer_atr": 0.25, "rr": 2.0, "wait": 5}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        feat["swings"] = F.swings(bars, self.cfg["swing_left"],
                                  self.cfg["swing_right"])
        feat["closes"] = [float(b["close"]) for b in bars]
        feat["pend"] = {}

    def _signals(self, idx, bars, feat):
        out = []
        closes = feat["closes"]
        # Track most recent confirmed swings; arm on an actual
        # CROSSING through the broken level (prev close on one
        # side, this close on the other) — not on every bar the
        # condition merely holds, which would extend the window
        # indefinitely.
        if feat["swings"][idx] is not None:
            s = feat["swings"][idx]
            feat["last_" + s["kind"]] = s
        if idx > 0:
            for direction, key in (("BULLISH", "low"),
                                   ("BEARISH", "high")):
                last = feat.get("last_" + key)
                if last is None or direction in feat["pend"]:
                    continue
                lvl = last["extreme"]
                prev, cur = closes[idx - 1], closes[idx]
                crossed = (prev <= lvl < cur) if direction == "BULLISH" \
                    else (prev >= lvl > cur)
                if not crossed:
                    continue
                atr = feat["atr"][idx]
                if atr is None:
                    continue
                buf = self.cfg["buffer_atr"] * atr
                if direction == "BULLISH":
                    stop = lvl - buf
                    edge = lvl
                    risk = edge - stop
                    if risk <= 0:
                        continue
                    tp = edge + self.cfg["rr"] * risk
                else:
                    stop = lvl + buf
                    edge = lvl
                    risk = stop - edge
                    if risk <= 0:
                        continue
                    tp = edge - self.cfg["rr"] * risk
                feat["pend"][direction] = {
                    "edge": edge, "stop": stop, "tp": tp,
                    "until": idx + self.cfg["wait"], "armed": idx}
        for direction in ("BULLISH", "BEARISH"):
            pend = feat["pend"].get(direction)
            if pend is None:
                continue
            if idx <= pend["armed"] or idx > pend["until"]:
                if idx > pend["until"]:
                    feat["pend"].pop(direction, None)
                continue
            lo, hi = float(bars[idx]["low"]), float(bars[idx]["high"])
            if lo <= pend["edge"] <= hi:
                out.append(self._sig(
                    direction, pend["edge"], pend["stop"], pend["tp"],
                    "%s-%s-%d" % (self.id, direction[:4], idx)))
                feat["pend"].pop(direction, None)
                break
        return out


class TrendFVG(_Base):
    """H11F-007: EMA50 trend + displacement + FVG retest (LIMIT)."""

    id = "H11F-007"
    params = {"ema_period": 50, "displacement_atr": 2.0,
              "buffer_atr": 0.25, "rr": 2.0, "wait": 5,
              "use_trend": True, "use_fvg": True}

    def _build(self, bars, feat):
        from research.phase11f.features import ema as _ema
        closes = [float(b["close"]) for b in bars]
        atr = _atr(bars, feat)
        feat["ema"] = _ema(closes, self.cfg["ema_period"])
        feat["disp"] = F.displacement(bars, self.cfg["displacement_atr"], atr)
        feat["fvg"] = F.fvg_zones(bars)
        feat["pend"] = {}

    def _signals(self, idx, bars, feat):
        out = []
        ema_v = feat["ema"][idx]
        cl = float(bars[idx]["close"])
        # Displacement direction comes from the impulse bar;
        # the trend filter keeps only with-trend impulses (the
        # no-trend ablation takes both).
        if feat["disp"][idx] and ema_v is not None:
            impulse_up = cl >= float(bars[idx]["open"])
            trend_up = cl >= ema_v
            if self.cfg["use_trend"] and impulse_up != trend_up:
                return out
            direction = "BULLISH" if impulse_up else "BEARISH"
            side = "long" if direction == "BULLISH" else "short"
            fvg = feat["fvg"][idx] if self.cfg["use_fvg"] else None
            ok = (not self.cfg["use_fvg"]) or (
                fvg is not None and fvg["direction"] == side)
            atr = feat["atr"][idx]
            if ok and atr is not None:
                if self.cfg["use_fvg"]:
                    edge = fvg["bottom"] if direction == "BULLISH" else fvg["top"]
                    far = fvg["top"] if direction == "BULLISH" else fvg["bottom"]
                else:
                    edge = cl
                    far = edge
                buf = self.cfg["buffer_atr"] * atr
                if direction == "BULLISH":
                    stop = far - buf
                    risk = edge - stop
                    if risk > 0:
                        feat["pend"][direction] = {
                            "edge": edge, "stop": stop,
                            "tp": edge + self.cfg["rr"] * risk,
                            "until": idx + self.cfg["wait"],
                            "armed": idx}
                else:
                    stop = far + buf
                    risk = stop - edge
                    if risk > 0:
                        feat["pend"][direction] = {
                            "edge": edge, "stop": stop,
                            "tp": edge - self.cfg["rr"] * risk,
                            "until": idx + self.cfg["wait"],
                            "armed": idx}
        for direction in ("BULLISH", "BEARISH"):
            pend = feat["pend"].get(direction)
            if pend is None:
                continue
            if idx <= pend["armed"] or idx > pend["until"]:
                if idx > pend["until"]:
                    feat["pend"].pop(direction, None)
                continue
            lo, hi = float(bars[idx]["low"]), float(bars[idx]["high"])
            if lo <= pend["edge"] <= hi:
                out.append(self._sig(
                    direction, pend["edge"], pend["stop"], pend["tp"],
                    "%s-%s-%d" % (self.id, direction[:4], idx)))
                feat["pend"].pop(direction, None)
                break
        return out

    def ablations(self):
        return [("full", {}),
                ("no-trend", {"use_trend": False}),
                ("no-fvg", {"use_fvg": False})]


class RangeRSIFade(_Base):
    """H11F-008: Donchian-100 extreme + RSI14 extreme fade to midline."""

    id = "H11F-008"
    params = {"range_lookback": 100, "rsi_period": 14,
              "rsi_low": 25, "rsi_high": 75, "buffer_atr": 0.25}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        hi, lo = F.donchian(bars, self.cfg["range_lookback"])
        feat["dhi"], feat["dlo"] = hi, lo
        # RSI with configured period (Wilder loop, causal).
        closes = [float(b["close"]) for b in bars]
        feat["rsi"] = F.rsi14(bars) if self.cfg["rsi_period"] == 14 else None
        if feat["rsi"] is None:
            feat["rsi"] = _rsi_n(closes, self.cfg["rsi_period"])

    def _signals(self, idx, bars, feat):
        hi, lo = feat["dhi"][idx], feat["dlo"][idx]
        rsi = feat["rsi"][idx]
        atr = feat["atr"][idx]
        if hi is None or rsi is None or atr is None:
            return []
        cl = float(bars[idx]["close"])
        mid = (hi + lo) / 2.0
        buf = self.cfg["buffer_atr"] * atr
        if cl <= lo + buf and rsi <= self.cfg["rsi_low"] and mid > cl:
            return [self._sig("BULLISH", cl, lo - buf, mid,
                              "%s-%d" % (self.id, idx))]
        if cl >= hi - buf and rsi >= self.cfg["rsi_high"] and mid < cl:
            return [self._sig("BEARISH", cl, hi + buf, mid,
                              "%s-%d" % (self.id, idx))]
        return []


def _rsi_n(closes, period):
    n = len(closes)
    out = [None] * n
    if n < period + 1 or period < 1:
        return out
    gains, losses = [], []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    out[period] = 50.0 if (avg_g == 0 and avg_l == 0) else (
        100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l))
    for i in range(period + 1, n):
        avg_g = (avg_g * (period - 1) + gains[i - 1]) / period
        avg_l = (avg_l * (period - 1) + losses[i - 1]) / period
        out[i] = 50.0 if (avg_g == 0 and avg_l == 0) else (
            100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l))
    return out


ALL = [SweepReversal, SweepDisplacementFVG, WyckoffSpring,
       WyckoffUpthrust, OrderBlockSweep, BreakerRetest,
       TrendFVG, RangeRSIFade]
