"""11G-L signal candidates (research-only; thresholds FROM frozen JSON).

Each class implements exactly one H11GK hypothesis. Frozen numbers
live in params (defaults EXACTLY the JSON thresholds + the frozen
family constants buffer 0.25 ATR / 2.0R, each pinned by a parity
test); code reads them via self.cfg, never literals. Ablation
switches are params too (component removal only).

NBO decisions at bar i (entry i+1 open).

Index discipline: the Backtester feeds TEST-slice bars with slice-local
idx. OHLC-structure features (ATR/swings/BOS/displacement/sweeps/
ranges) are slice-cold-start (11G-C-certified pattern). Trade-flow
quantities (delta/CVD/volumes/footprint/absorption/aggression) come
from the full-day causal MarketContext bundle via GLOBAL index
g = idx + of_offset. The bundle/offset ride on the research candidate
instance (attach(); production PipelineContext is slots-restricted
and is never written). Both legs causal: nothing past the bar.

Ablation IDs match the registry; residue rules (frozen-form first):
a retained level-bearing component keeps its frozen stop reference,
else the signal-bar extreme +- buffer ATR (universal frozen form).
Direction of a residue follows its retained confirmation, else the
signal bar polarity (documented per case). BLOCKED/SKIPPED as written
(never reinterpreted, never invented):
- 006 full has NO displacement (event-literal; displacement_atr is a
  frozen-but-vestigial threshold, accepted and proven unused).
- 006-A1 title-faithful sweep-only (registry residue +displacement
  unimplementable); 006-A2 aggression-only, bar-extreme stop.
- 007-A2 (remove sweep) residue = full event: DEGENERATE, skipped.
- 008-A2 (CVD slope alone) has no bar-level stop anchor: BLOCKED.
- 004-A1 reference = most-recent displacement bar within the trailing
  footprint window (frozen 60m); tolerance band mirrors full.
- 005-A2 direction = absorption-bar polarity (no frozen rule; noted).

Candidates never read past idx (truncation-proven). Base SUBCLASSED
from the certified-fixed 11F base (state-preserving prepare).
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f.candidates import _Base  # noqa: E402 (fixed prepare)
from research.phase11f import features as F11  # noqa: E402

KDIR = Path(__file__).resolve().parent.parent.parent / "phase11g_k" / "hypotheses"


def _sig(direction, entry, stop, tp, setup_id, confidence=80.0):
    return {"direction": direction, "entry": float(entry),
            "stop": float(stop), "take_profit": float(tp),
            "setup_id": setup_id, "confidence": confidence}


class _KBase(_Base):
    id = "H11GK-000"
    hid = "H11GK-000"
    params = {"buffer_atr": 0.25}

    def __init__(self, **overrides):
        self.spec = json.loads((KDIR / (self.hid + ".json")).read_text())
        self.fp = self.spec["thresholds"]
        self._bundle = None
        self._off = 0
        super().__init__(**overrides)

    def attach(self, bundle, offset=0):
        """Bind the full-day causal flow bundle + test-slice global
        offset (runner-owned wiring; production context untouched)."""
        self._bundle = bundle
        self._off = int(offset)
        return self

    def signals(self, idx, bars, context):
        return super().signals(idx, bars, context)

    def _G(self, j):
        """Slice-local bar j -> global day index for bundle (flow) calls."""
        return j + self._off

    def _atr(self, bars, feat):
        if "atr" not in feat:
            feat["atr"] = F11.atr14(bars)
        return feat["atr"]

    def _closes(self, bars, feat):
        if "closes" not in feat:
            feat["closes"] = [float(b["close"]) for b in bars]
        return feat["closes"]

    def _rr(self, direction, entry, stop):
        if direction == "BULLISH":
            risk = entry - stop
            return (entry + 2.0 * risk) if risk > 0 else None
        risk = stop - entry
        return (entry - 2.0 * risk) if risk > 0 else None

    def _bar_stop(self, idx, bars, feat, direction):
        """Generic residue stop: signal-bar extreme +- buffer ATR."""
        atr = feat["atr"][idx]
        if atr is None:
            return None
        buf = self.cfg["buffer_atr"] * atr
        if direction == "BULLISH":
            return float(bars[idx]["low"]) - buf
        return float(bars[idx]["high"]) + buf

    def _polarity(self, idx, bars):
        return ("BULLISH" if float(bars[idx]["close"]) >= float(bars[idx]["open"])
                else "BEARISH")

    def _bos_array(self, bars, feat, left, right):
        """Per-bar BOS direction (or None) + broken level; O(n^2) build."""
        if "bos" not in feat:
            feat["swings"] = F11.swings(bars, left, right)
            closes = self._closes(bars, feat)
            out, last_high, last_low = [], None, None
            for i in range(len(bars)):
                s = feat["swings"][i]
                if s is not None:
                    if s["kind"] == "high":
                        last_high = s["extreme"]
                    else:
                        last_low = s["extreme"]
                direction, lvl = None, None
                if i > 0:
                    if last_high is not None and closes[i - 1] <= last_high < closes[i]:
                        direction, lvl = "BULLISH", last_high
                    elif last_low is not None and closes[i - 1] >= last_low > closes[i]:
                        direction, lvl = "BEARISH", last_low
                out.append((direction, lvl))
            feat["bos"] = out
        return feat["bos"]


class ImbalanceBOS(_KBase):
    """H11GK-001: 5m |DI|>=min at bar j, same-direction 1m BOS at the
    signal bar with idx-j <= confirmation bars. Stop: BOS broken level
    +- buffer ATR (frozen stop text)."""

    hid = "H11GK-001"
    id = "H11GK-001"
    params = {"imbalance_abs_min": 0.6, "confirmation_bars": 10,
              "buffer_atr": 0.25,
              "use_flow": True, "use_bos": True, "agree": True}

    def _build(self, bars, feat):
        self._atr(bars, feat)
        self._bos_array(bars, feat, 3, 3)

    def _flow_dir(self, j):
        b, s, tot, d = self._bundle.window_vol(self._G(j), 5)
        if tot <= 0 or abs(d) / tot < self.cfg["imbalance_abs_min"]:
            return None
        return "BULLISH" if d > 0 else "BEARISH"

    def _signals(self, idx, bars, feat):
        if idx < 1:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        if self.cfg["use_bos"]:
            direction, lvl = feat["bos"][idx]
            if direction is None:
                return []
        else:
            direction, lvl = None, None
        if self.cfg["use_flow"]:
            if self._bundle is None:
                return []
            if self.cfg["use_bos"]:
                lo = max(0, idx - self.cfg["confirmation_bars"])
                if not any(self._flow_dir(j) == direction
                           if self.cfg["agree"]
                           else self._flow_dir(j) is not None
                           for j in range(lo, idx + 1)):
                    return []
            else:
                direction = self._flow_dir(idx)
                if direction is None:
                    return []
        if direction is None:
            return []
        entry = float(bars[idx]["close"])
        buf = self.cfg["buffer_atr"] * atr
        if lvl is not None:
            stop = lvl - buf if direction == "BULLISH" else lvl + buf
        else:
            stop = self._bar_stop(idx, bars, feat, direction)
        if stop is None:
            return []
        tp = self._rr(direction, entry, stop)
        if tp is None:
            return []
        return [_sig(direction, entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}),
                ("A1", {"use_flow": False}),
                ("A2", {"use_bos": False}),
                ("A3", {"agree": False})]


class DeltaReversal(_KBase):
    """H11GK-002: 15m exhaustion (|delta|/vol>=fraction AND vol>=mult
    x median of trailing trail_windows 15m windows) at bar j,
    opposite-direction displacement at the signal bar with idx-j <=
    confirmation bars. Stop: displacement extreme +- buffer ATR."""

    hid = "H11GK-002"
    id = "H11GK-002"
    params = {"delta_fraction_min": 0.4, "volume_mult": 2.0,
              "volume_trail_windows": 20, "confirmation_bars": 5,
              "displacement_atr": 2.0, "buffer_atr": 0.25,
              "use_delta": True, "use_disp": True, "agree": True}

    def _build(self, bars, feat):
        self._atr(bars, feat)
        feat["disp"] = F11.displacement(bars, self.cfg["displacement_atr"],
                                        feat["atr"])

    def _vol_ok(self, j):
        cur = self._bundle.window_vol(self._G(j), 15)[2]
        prior = [self._bundle.window_vol(self._G(k), 15)[2]
                 for k in range(max(0, j - self.cfg["volume_trail_windows"]), j)]
        if not prior:
            return False
        med = statistics.median(prior)
        return bool(med > 0 and cur >= self.cfg["volume_mult"] * med)

    def _exhausted(self, j):
        b, s, tot, d = self._bundle.window_vol(self._G(j), 15)
        if tot <= 0 or abs(d) / tot < self.cfg["delta_fraction_min"]:
            return None
        if not self._vol_ok(j):
            return None
        return "BEARISH" if d > 0 else "BULLISH"

    def _signals(self, idx, bars, feat):
        if idx < 1 or self._bundle is None:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        buf = self.cfg["buffer_atr"] * atr
        if self.cfg["use_disp"] and self.cfg["use_delta"]:
            if not feat["disp"][idx]:
                return []
            direction = self._polarity(idx, bars)
            lo = max(0, idx - self.cfg["confirmation_bars"])
            if not any(((self._exhausted(j) == direction)
                        if self.cfg["agree"]
                        else (self._exhausted(j) is not None))
                       for j in range(lo, idx + 1)):
                return []
            entry = float(bars[idx]["close"])
            stop = (float(bars[idx]["low"]) - buf if direction == "BULLISH"
                    else float(bars[idx]["high"]) + buf)
        elif self.cfg["use_disp"]:
            # A1: displacement + volume only (no delta-sign condition).
            if not feat["disp"][idx]:
                return []
            lo = max(0, idx - self.cfg["confirmation_bars"])
            if not any(self._vol_ok(j) for j in range(lo, idx + 1)):
                return []
            direction = self._polarity(idx, bars)
            entry = float(bars[idx]["close"])
            stop = (float(bars[idx]["low"]) - buf if direction == "BULLISH"
                    else float(bars[idx]["high"]) + buf)
        else:
            # A2: exhaustion alone at the signal bar.
            direction = self._exhausted(idx)
            if direction is None:
                return []
            entry = float(bars[idx]["close"])
            stop = self._bar_stop(idx, bars, feat, direction)
            if stop is None:
                return []
        tp = self._rr(direction, entry, stop)
        if tp is None:
            return []
        return [_sig(direction, entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}),
                ("A1", {"use_delta": False}),
                ("A2", {"use_disp": False}),
                ("A3", {"agree": False})]


class CVDDivergence(_KBase):
    """H11GK-003: 1m close prints a trailing-N-bar lowest low (highest
    high, N = divergence minutes = 1m bars) while 60m CVD slope
    (last-minus-first) is positive (negative), plus agreeing 1m
    displacement within confirmation bars. Stop: the N-bar swing
    extreme +- buffer ATR."""

    hid = "H11GK-003"
    id = "H11GK-003"
    params = {"divergence_lookback_minutes": 60, "confirmation_bars": 5,
              "displacement_atr": 2.0, "buffer_atr": 0.25,
              "use_cvd": True, "use_disp": True, "agree": True}

    def _build(self, bars, feat):
        self._atr(bars, feat)
        self._closes(bars, feat)
        feat["disp"] = F11.displacement(bars, self.cfg["displacement_atr"],
                                        feat["atr"])

    def _extreme(self, j, feat):
        n = self.cfg["divergence_lookback_minutes"]
        if j < n - 1:
            return None
        w = feat["closes"][j - n + 1:j + 1]
        if feat["closes"][j] == min(w):
            return "BULLISH"
        if feat["closes"][j] == max(w):
            return "BEARISH"
        return None

    def _slope_sign(self, j):
        slope = self._bundle.cvd_slope(
            self._G(j), self.cfg["divergence_lookback_minutes"])
        if slope > 0:
            return "BULLISH"
        if slope < 0:
            return "BEARISH"
        return None

    def _divergent(self, j, feat):
        ext = self._extreme(j, feat)
        if ext is None:
            return None
        if self._slope_sign(j) != ext:
            return None
        return ext

    def _signals(self, idx, bars, feat):
        if idx < 1 or self._bundle is None:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        n = self.cfg["divergence_lookback_minutes"]
        buf = self.cfg["buffer_atr"] * atr
        if self.cfg["use_cvd"] and self.cfg["use_disp"]:
            if not feat["disp"][idx]:
                return []
            direction = self._polarity(idx, bars)
            lo = max(0, idx - self.cfg["confirmation_bars"])
            if not any(((self._divergent(j, feat) == direction)
                        if self.cfg["agree"]
                        else (self._divergent(j, feat) is not None))
                       for j in range(lo, idx + 1)):
                return []
            entry = float(bars[idx]["close"])
            lo60 = min(float(bars[k]["low"]) for k in range(max(0, idx - n + 1), idx + 1))
            hi60 = max(float(bars[k]["high"]) for k in range(max(0, idx - n + 1), idx + 1))
            stop = lo60 - buf if direction == "BULLISH" else hi60 + buf
        elif self.cfg["use_disp"]:
            # A1: divergence-less structure (extreme + displacement).
            ext = self._extreme(idx, feat)
            if ext is None or not feat["disp"][idx]:
                return []
            direction = self._polarity(idx, bars)
            if direction != ext:
                return []
            entry = float(bars[idx]["close"])
            lo60 = min(float(bars[k]["low"]) for k in range(max(0, idx - n + 1), idx + 1))
            hi60 = max(float(bars[k]["high"]) for k in range(max(0, idx - n + 1), idx + 1))
            stop = lo60 - buf if direction == "BULLISH" else hi60 + buf
        else:
            # A2: divergence alone at the signal bar.
            direction = self._divergent(idx, feat)
            if direction is None:
                return []
            entry = float(bars[idx]["close"])
            stop = self._bar_stop(idx, bars, feat, direction)
            if stop is None:
                return []
        tp = self._rr(direction, entry, stop)
        if tp is None:
            return []
        return [_sig(direction, entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}),
                ("A1", {"use_cvd": False}),
                ("A2", {"use_disp": False}),
                ("A3", {"agree": False})]


class FootprintPOC(_KBase):
    """H11GK-004: trailing footprint-window-minutes POC exists; the
    signal bar is within touch-tolerance ATR of POC, displaces away
    (range > displacement ATR, close beyond POC). Stop: POC +- buffer."""

    hid = "H11GK-004"
    id = "H11GK-004"
    params = {"poc_touch_tolerance_atr": 0.1, "displacement_atr": 1.0,
              "footprint_window_minutes": 60, "buffer_atr": 0.25,
              "use_poc": True, "use_retest": True}

    def _build(self, bars, feat):
        self._atr(bars, feat)
        feat["disp1"] = F11.displacement(bars, self.cfg["displacement_atr"],
                                         feat["atr"])

    @staticmethod
    def _dist(bar, level):
        lo, hi = float(bar["low"]), float(bar["high"])
        if lo <= level <= hi:
            return 0.0
        return min(abs(hi - level), abs(lo - level))

    def _signals(self, idx, bars, feat):
        if idx < 1 or self._bundle is None:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        bar = bars[idx]
        rng = float(bar["high"]) - float(bar["low"])
        cl = float(bar["close"])
        tol = self.cfg["poc_touch_tolerance_atr"] * atr
        datr = self.cfg["displacement_atr"] * atr
        if self.cfg["use_poc"]:
            poc = self._bundle.poc_60m(self._G(idx))
            if poc is None:
                return []
            level = poc[0]
        else:
            # A1: retest of the most-recent displacement bar's range
            # (midpoint reference) within the trailing footprint
            # window; tolerance band mirrors full.
            level = None
            scan = self.cfg["footprint_window_minutes"]
            for j in range(idx, max(-1, idx - scan), -1):
                if feat["disp1"][j]:
                    level = (float(bars[j]["low"]) + float(bars[j]["high"])) / 2.0
                    break
            if level is None:
                return []
        if self.cfg["use_retest"]:
            if self._dist(bar, level) > tol:
                return []
            if rng < datr or cl == level:
                return []
            direction = "BULLISH" if cl > level else "BEARISH"
        else:
            # A2: displacement close only (POC retained as stop).
            if rng < datr:
                return []
            direction = self._polarity(idx, bars)
        entry = cl
        buf = self.cfg["buffer_atr"] * atr
        stop = level - buf if direction == "BULLISH" else level + buf
        tp = self._rr(direction, entry, stop)
        if tp is None:
            return []
        return [_sig(direction, entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}),
                ("A1", {"use_poc": False}),
                ("A2", {"use_retest": False})]


class AbsorptionDisp(_KBase):
    """H11GK-005: 1m absorption bar (volume >= mult x trailing
    trail_windows 1m median AND range <= progress_ratio x trailing
    median range) at bar j, same-direction displacement at the signal
    bar with idx-j <= confirmation bars. Stop: absorption-bar extreme
    +- buffer ATR (most-recent absorbed bar)."""

    hid = "H11GK-005"
    id = "H11GK-005"
    params = {"volume_mult": 3.0, "trail_windows": 20,
              "progress_ratio": 0.25, "confirmation_bars": 3,
              "displacement_atr": 2.0, "buffer_atr": 0.25,
              "use_abs": True, "use_disp": True}

    def _build(self, bars, feat):
        self._atr(bars, feat)
        feat["disp"] = F11.displacement(bars, self.cfg["displacement_atr"],
                                        feat["atr"])

    def _absorbed(self, j):
        g = self._G(j)
        cur = self._bundle.min_total[g]
        med = self._bundle.trailing_median(
            self._bundle.min_total, g, self.cfg["trail_windows"])
        if med is None or med <= 0 or cur < self.cfg["volume_mult"] * med:
            return False
        rngs = self._bundle.minute_ranges(g, self.cfg["trail_windows"])
        if not rngs:
            return False
        s = sorted(rngs)
        mrange = s[len(s) // 2]
        cur_r = self._bundle.highs[g] - self._bundle.lows[g]
        return bool(mrange > 0 and cur_r <= self.cfg["progress_ratio"] * mrange)

    def _vol_burst(self, j):
        g = self._G(j)
        cur = self._bundle.min_total[g]
        med = self._bundle.trailing_median(
            self._bundle.min_total, g, self.cfg["trail_windows"])
        return bool(med is not None and med > 0
                    and cur >= self.cfg["volume_mult"] * med)

    def _signals(self, idx, bars, feat):
        if idx < 1 or self._bundle is None:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        buf = self.cfg["buffer_atr"] * atr
        span = self.cfg["confirmation_bars"]
        if self.cfg["use_abs"] and self.cfg["use_disp"]:
            if not feat["disp"][idx]:
                return []
            jab = None
            for j in range(idx, max(-1, idx - span), -1):
                if self._absorbed(j):
                    jab = j
                    break
            if jab is None:
                return []
            direction = self._polarity(idx, bars)
            entry = float(bars[idx]["close"])
            stop = (float(bars[jab]["low"]) - buf if direction == "BULLISH"
                    else float(bars[jab]["high"]) + buf)
        elif self.cfg["use_disp"]:
            # A1: displacement + volume only (no range condition).
            if not feat["disp"][idx]:
                return []
            lo = max(0, idx - span)
            if not any(self._vol_burst(j) for j in range(lo, idx + 1)):
                return []
            direction = self._polarity(idx, bars)
            entry = float(bars[idx]["close"])
            stop = (float(bars[idx]["low"]) - buf if direction == "BULLISH"
                    else float(bars[idx]["high"]) + buf)
        else:
            # A2: absorption alone at the signal bar (polarity noted).
            if not self._absorbed(idx):
                return []
            direction = self._polarity(idx, bars)
            entry = float(bars[idx]["close"])
            stop = (float(bars[idx]["low"]) - buf if direction == "BULLISH"
                    else float(bars[idx]["high"]) + buf)
        tp = self._rr(direction, entry, stop)
        if tp is None:
            return []
        return [_sig(direction, entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}),
                ("A1", {"use_abs": False}),
                ("A2", {"use_disp": False})]


class AggressionSweep(_KBase):
    """H11GK-006 (event-literal): equal-level sweep + reclaim (11G-A
    frozen sweep form: tolerance ATR, certified default lookback) with
    a same-direction 1m trade-aggression burst (side volume >= mult x
    trailing trail_windows 1m median) within confirmation bars. No
    displacement in the frozen event (displacement_atr accepted from
    the JSON but vestigial — proven unused by test). Stop: sweep
    extreme +- buffer ATR."""

    hid = "H11GK-006"
    id = "H11GK-006"
    params = {"tolerance_atr": 0.1, "sweep_lookback": 50,
              "aggression_volume_mult": 5.0, "aggression_trail_windows": 20,
              "confirmation_bars": 3, "displacement_atr": 2.0,
              "buffer_atr": 0.25,
              "use_sweep": True, "use_aggr": True}

    def _build(self, bars, feat):
        self._atr(bars, feat)
        feat["sw"] = F11.sweeps(bars, self.cfg["sweep_lookback"],
                                self.cfg["tolerance_atr"], feat["atr"])

    def _burst_side(self, j):
        g = self._G(j)
        trail = self.cfg["aggression_trail_windows"]
        mult = self.cfg["aggression_volume_mult"]
        for side in ("long", "short"):
            cur = (self._bundle.min_buy[g] if side == "long"
                   else self._bundle.min_sell[g])
            hist = [(self._bundle.min_buy[k] if side == "long"
                     else self._bundle.min_sell[k])
                    for k in range(max(0, g - trail), g)]
            if not hist:
                continue
            med = sorted(hist)[len(hist) // 2]
            if med > 0 and cur >= mult * med:
                return side
        return None

    def _signals(self, idx, bars, feat):
        if idx < 1 or self._bundle is None:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        buf = self.cfg["buffer_atr"] * atr
        span = self.cfg["confirmation_bars"]
        if self.cfg["use_sweep"] and self.cfg["use_aggr"]:
            side = self._burst_side(idx)
            if side is None:
                return []
            sw = None
            for j in range(idx, max(-1, idx - span), -1):
                got = feat["sw"][j]
                if got is not None and got["direction"] == side:
                    sw = got
                    break
            if sw is None:
                return []
            direction = "BULLISH" if side == "long" else "BEARISH"
            entry = float(bars[idx]["close"])
            stop = (sw["extreme"] - buf if direction == "BULLISH"
                    else sw["extreme"] + buf)
        elif self.cfg["use_sweep"]:
            # A1: sweep only at the signal bar.
            sw = feat["sw"][idx]
            if sw is None:
                return []
            direction = "BULLISH" if sw["direction"] == "long" else "BEARISH"
            entry = float(bars[idx]["close"])
            stop = (sw["extreme"] - buf if direction == "BULLISH"
                    else sw["extreme"] + buf)
        else:
            # A2: aggression burst alone at the signal bar.
            side = self._burst_side(idx)
            if side is None:
                return []
            direction = "BULLISH" if side == "long" else "BEARISH"
            entry = float(bars[idx]["close"])
            stop = self._bar_stop(idx, bars, feat, direction)
            if stop is None:
                return []
        tp = self._rr(direction, entry, stop)
        if tp is None:
            return []
        return [_sig(direction, entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}),
                ("A1", {"use_aggr": False}),
                ("A2", {"use_sweep": False})]


class BOSDelta(_KBase):
    """H11GK-007: 1m BOS bar (swings left/right) with same-bar 5m trade
    delta of agreeing sign. Stop: BOS broken level +- buffer ATR."""

    hid = "H11GK-007"
    id = "H11GK-007"
    params = {"buffer_atr": 0.25, "swing_left": 3, "swing_right": 3,
              "use_delta": True}

    def _build(self, bars, feat):
        self._atr(bars, feat)
        self._bos_array(bars, feat, self.cfg["swing_left"],
                        self.cfg["swing_right"])

    def _signals(self, idx, bars, feat):
        if idx < 1 or self._bundle is None:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        direction, lvl = feat["bos"][idx]
        if direction is None:
            return []
        if self.cfg["use_delta"]:
            b, s, tot, d = self._bundle.window_vol(self._G(idx), 5)
            if (direction == "BULLISH" and d <= 0) or \
               (direction == "BEARISH" and d >= 0):
                return []
        entry = float(bars[idx]["close"])
        buf = self.cfg["buffer_atr"] * atr
        stop = lvl - buf if direction == "BULLISH" else lvl + buf
        tp = self._rr(direction, entry, stop)
        if tp is None:
            return []
        return [_sig(direction, entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        # 007-A2 (remove sweep) residue = full event: DEGENERATE, skip.
        # 007-A1 below removes delta agreement (BOS-only residue); the
        # registry parenthetical residue (sweep+BOS) is unimplementable
        # — sweep absent from the frozen event, none introduced.
        return [("full", {}),
                ("A1", {"use_delta": False})]


class RangeCVD(_KBase):
    """H11GK-008: prior range_lookback range (min_hold hold,
    strictly-prior bars) boundary touch with rejection + agreeing
    cvd_slope_minutes CVD slope sign. Stop: touched boundary +- buffer."""

    hid = "H11GK-008"
    id = "H11GK-008"
    params = {"range_lookback": 50, "min_hold_bars": 30,
              "cvd_slope_minutes": 60, "buffer_atr": 0.25,
              "use_cvd": True}

    def _build(self, bars, feat):
        from research.phase11g.features import wyckoff as WY
        self._atr(bars, feat)
        feat["pr"] = WY.prior_range_state(bars, self.cfg["range_lookback"],
                                          self.cfg["min_hold_bars"])

    def _signals(self, idx, bars, feat):
        if idx < 1 or self._bundle is None:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        r = feat["pr"][idx]
        if r is None:
            return []
        lo, hi = float(bars[idx]["low"]), float(bars[idx]["high"])
        cl = float(bars[idx]["close"])
        touched_low = lo <= r["low"] and cl > r["low"]
        touched_high = hi >= r["high"] and cl < r["high"]
        if touched_low == touched_high:
            return []
        if self.cfg["use_cvd"]:
            slope = self._bundle.cvd_slope(
                self._G(idx), self.cfg["cvd_slope_minutes"])
            if touched_low and slope <= 0:
                return []
            if touched_high and slope >= 0:
                return []
        direction = "BULLISH" if touched_low else "BEARISH"
        entry = cl
        buf = self.cfg["buffer_atr"] * atr
        stop = r["low"] - buf if direction == "BULLISH" else r["high"] + buf
        tp = self._rr(direction, entry, stop)
        if tp is None:
            return []
        return [_sig(direction, entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        # 008-A2 (CVD slope alone) has no bar-level stop anchor (a new
        # lookback rule would have to be invented): BLOCKED, see report.
        # 008-A1 below removes the CVD filter (range-only residue); the
        # registry parenthetical (+displacement) is unimplementable —
        # displacement absent from the frozen event, none introduced.
        return [("full", {}),
                ("A1", {"use_cvd": False})]


ALL = [ImbalanceBOS, DeltaReversal, CVDDivergence, FootprintPOC,
       AbsorptionDisp, AggressionSweep, BOSDelta, RangeCVD]
