"""Phase 11G-F signal candidates (research-only, NBO family).

Fresh implementations of the EIGHT frozen H11GF hypotheses against the
certified 11G-A feature engine + 11F primitives. Base class SUBCLASSED
from the certified-fixed 11F candidate base (state-preserving prepare).
Signals are NBO decisions at bar i (entry at bar i+1 open); candidates
never read past idx (proven by truncation tests). No tuning, no scores.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research.phase11f.candidates import _Base
from research.phase11f import features as F11
from research.phase11g.features import (
    breaker as BRK,
    displacement as DSP,
    liquidity as LIQ,
    mtf as MTF,
    orderblock as OB,
    structure as ST,
    volume as VOL,
    wyckoff as WY,
)
from research.phase11g.features import fvg as FVG


def _atr(bars, cache):
    if "atr" not in cache:
        cache["atr"] = F11.atr14(bars)
    return cache["atr"]


def _sig(direction, entry, stop, tp, setup_id, confidence=80.0):
    return {"direction": direction, "entry": float(entry),
            "stop": float(stop), "take_profit": float(tp),
            "setup_id": setup_id, "confidence": confidence}


class SweepReclaim(_Base):
    """H11GF-001: hierarchy sweep + reclaim (NBO)."""

    id = "H11GF-001"
    params = {"tolerance_atr": 0.1, "buffer_atr": 0.25, "rr": 2.0,
              "use_sweep": True}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        feat["sw"] = F11.sweeps(bars, 50, self.cfg["tolerance_atr"], atr)
        feat["sess"] = LIQ.session_sweep_events(bars, self.cfg["buffer_atr"])
        feat["pool"] = LIQ.reference_pools(bars)

    def _signals(self, idx, bars, feat):
        if idx < 1:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        if self.cfg["use_sweep"]:
            sw = feat["sw"][idx]
            se = feat["sess"][idx]
            hit = sw if sw is not None else (
                {"direction": "long" if se["value"]["direction"] == "long" else "short",
                 "level": se["value"]["level"],
                 "extreme": se["value"]["extreme"]} if se["status"] == "OK" else None)
            if hit is None:
                return []
        else:
            hit = None
            lo, hi = float(bars[idx]["low"]), float(bars[idx]["high"])
            cl = float(bars[idx]["close"])
            for ref in feat["pool"][idx]["value"]:
                lvl = ref["level"]
                if lo < lvl < hi and cl > lvl and ref["type"].endswith("low"):
                    hit = {"direction": "long", "level": lvl, "extreme": lo}
                    break
                if lo < lvl < hi and cl < lvl and ref["type"].endswith("high"):
                    hit = {"direction": "short", "level": lvl, "extreme": hi}
                    break
            if hit is None:
                return []
        entry = float(bars[idx]["close"])
        buf = self.cfg["buffer_atr"] * atr
        if hit["direction"] == "long":
            stop = hit["extreme"] - buf
            risk = entry - stop
            if risk <= 0:
                return []
            return [_sig("BULLISH", entry, stop, entry + self.cfg["rr"] * risk,
                         "%s-%d" % (self.id, idx))]
        stop = hit["extreme"] + buf
        risk = stop - entry
        if risk <= 0:
            return []
        return [_sig("BEARISH", entry, stop, entry - self.cfg["rr"] * risk,
                     "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}), ("no-sweep", {"use_sweep": False})]


class SweepDisplacement(_Base):
    """H11GF-002: sweep within 3 bars + displacement (NBO)."""

    id = "H11GF-002"
    params = {"tolerance_atr": 0.1, "displacement_atr": 2.0,
              "buffer_atr": 0.25, "rr": 2.0, "sweep_lookback_bars": 3,
              "use_sweep": True, "use_disp": True}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        feat["sw"] = F11.sweeps(bars, 50, self.cfg["tolerance_atr"], atr)
        feat["disp"] = F11.displacement(bars, self.cfg["displacement_atr"], atr)

    def _signals(self, idx, bars, feat):
        if not feat["disp"][idx]:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        direction = ("BULLISH" if float(bars[idx]["close"]) >= float(bars[idx]["open"])
                     else "BEARISH")
        side = "long" if direction == "BULLISH" else "short"
        if self.cfg["use_sweep"]:
            swept = any(feat["sw"][j] is not None and feat["sw"][j]["direction"] == side
                        for j in range(max(0, idx - self.cfg["sweep_lookback_bars"] + 1),
                                       idx + 1))
            if not swept:
                return []
        if not self.cfg["use_disp"]:
            return []
        entry = float(bars[idx]["close"])
        buf = self.cfg["buffer_atr"] * atr
        if direction == "BULLISH":
            stop = float(bars[idx]["low"]) - buf
            risk = entry - stop
            tp = entry + self.cfg["rr"] * risk if risk > 0 else None
        else:
            stop = float(bars[idx]["high"]) + buf
            risk = stop - entry
            tp = entry - self.cfg["rr"] * risk if risk > 0 else None
        if tp is None:
            return []
        return [_sig(direction, entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}),
                ("no-sweep", {"use_sweep": False}),
                ("no-displacement", {"use_disp": False})]


class _RetestBase(_Base):
    id = "H11GF-000"
    params = {"wait": 5}

    def _trigger(self, edge, stop, tp, direction, idx):
        return _sig(direction, float(edge), stop, tp,
                    "%s-%s-%d" % (self.id, direction[:4], idx))

    @staticmethod
    def _touch(idx, bars, pend, direction):
        p = pend.get(direction)
        if p is None:
            return None, False
        if idx <= p["armed"] or idx > p["until"]:
            return None, idx > p["until"]
        lo, hi = float(bars[idx]["low"]), float(bars[idx]["high"])
        if lo <= p["edge"] <= hi:
            return p, False
        return None, False


class SweepDisplacementFVG(_RetestBase):
    """H11GF-003: sweep + displacement + same-bar FVG, retest <=5, NBO."""

    id = "H11GF-003"
    params = {"tolerance_atr": 0.1, "displacement_atr": 2.0,
              "buffer_atr": 0.25, "rr": 2.0, "sweep_lookback_bars": 3,
              "wait": 5, "use_sweep": True, "use_disp": True, "use_fvg": True}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        feat["sw"] = F11.sweeps(bars, 50, self.cfg["tolerance_atr"], atr)
        feat["disp"] = F11.displacement(bars, self.cfg["displacement_atr"], atr)
        feat["fvg"] = F11.fvg_zones(bars)
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
                            for j in range(max(0, idx - self.cfg["sweep_lookback_bars"] + 1),
                                           idx + 1))
            fvg = feat["fvg"][idx] if self.cfg["use_fvg"] else None
            disp_ok = feat["disp"][idx] if self.cfg["use_disp"] else True
            ok = disp_ok and (not self.cfg["use_fvg"] or (
                fvg is not None and fvg["direction"] == side))
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
                    stop, risk = far - buf, edge - (far - buf)
                    tp = edge + self.cfg["rr"] * risk if risk > 0 else None
                else:
                    stop, risk = far + buf, (far + buf) - edge
                    tp = edge - self.cfg["rr"] * risk if risk > 0 else None
                if tp is not None:
                    feat["pend"][direction] = {
                        "edge": edge, "stop": stop, "tp": tp,
                        "until": idx + self.cfg["wait"], "armed": idx}
        for direction in ("BULLISH", "BEARISH"):
            pend, expired = self._touch(idx, bars, feat["pend"], direction)
            if expired:
                feat["pend"].pop(direction, None)
                continue
            if pend is not None:
                out.append(self._trigger(pend["edge"], pend["stop"], pend["tp"],
                                         direction, idx))
                feat["pend"].pop(direction, None)
                break
        return out

    def ablations(self):
        return [("full", {}),
                ("no-sweep", {"use_sweep": False}),
                ("no-displacement", {"use_disp": False}),
                ("no-fvg", {"use_fvg": False})]


class OrderBlockBOS(_RetestBase):
    """H11GF-004: BOS + strictly-prior OB, retest <=5, NBO."""

    id = "H11GF-004"
    params = {"swing_left": 3, "swing_right": 3, "buffer_atr": 0.25,
              "rr": 2.0, "wait": 5, "use_bos": True}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        feat["swings"] = F11.swings(bars, self.cfg["swing_left"],
                                    self.cfg["swing_right"])
        feat["closes"] = [float(b["close"]) for b in bars]
        feat["disp"] = F11.displacement(bars, 2.0, atr)
        feat["pend"] = {}

    def _signals(self, idx, bars, feat):
        out = []
        closes = feat["closes"]
        if feat["swings"][idx] is not None:
            s = feat["swings"][idx]
            feat["last_" + s["kind"]] = s
        if idx > 0:
            for direction, key in (("BULLISH", "low"), ("BEARISH", "high")):
                if direction in feat["pend"]:
                    continue
                if not self.cfg["use_bos"]:
                    if not feat["disp"][idx]:
                        continue
                else:
                    last = feat.get("last_" + key)
                    if last is None:
                        continue
                    lvl = last["extreme"]
                    prev, cur = closes[idx - 1], closes[idx]
                    crossed = (prev <= lvl < cur) if direction == "BULLISH" \
                        else (prev >= lvl > cur)
                    if not crossed:
                        continue
                side = "long" if direction == "BULLISH" else "short"
                ob = F11.order_block_before(bars, idx, side)
                atr = feat["atr"][idx]
                if ob is None or atr is None:
                    continue
                buf = self.cfg["buffer_atr"] * atr
                edge, far = ob["edge"], ob["extreme"]
                if direction == "BULLISH":
                    stop, risk = far - buf, edge - (far - buf)
                    tp = edge + self.cfg["rr"] * risk if risk > 0 else None
                else:
                    stop, risk = far + buf, (far + buf) - edge
                    tp = edge - self.cfg["rr"] * risk if risk > 0 else None
                if tp is None:
                    continue
                feat["pend"][direction] = {
                    "edge": edge, "stop": stop, "tp": tp,
                    "until": idx + self.cfg["wait"], "armed": idx}
        for direction in ("BULLISH", "BEARISH"):
            pend, expired = self._touch(idx, bars, feat["pend"], direction)
            if expired:
                feat["pend"].pop(direction, None)
                continue
            if pend is not None:
                out.append(self._trigger(pend["edge"], pend["stop"], pend["tp"],
                                         direction, idx))
                feat["pend"].pop(direction, None)
                break
        return out

    def ablations(self):
        return [("full", {}), ("no-bos", {"use_bos": False})]


class BreakerRetest(_RetestBase):
    """H11GF-005: breaker cross + retest <=5, NBO."""

    id = "H11GF-005"
    params = {"swing_left": 3, "swing_right": 3, "buffer_atr": 0.25,
              "rr": 2.0, "wait": 5, "use_breaker": True}

    def _build(self, bars, feat):
        atr = _atr(bars, feat)
        feat["swings"] = F11.swings(bars, self.cfg["swing_left"],
                                    self.cfg["swing_right"])
        feat["closes"] = [float(b["close"]) for b in bars]
        feat["pend"] = {}

    def _arm(self, idx, feat, direction, lvl):
        atr = feat["atr"][idx]
        if atr is None:
            return
        buf = self.cfg["buffer_atr"] * atr
        if direction == "BULLISH":
            stop, edge, risk = lvl - buf, lvl, buf
            tp = edge + self.cfg["rr"] * risk
        else:
            stop, edge, risk = lvl + buf, lvl, buf
            tp = edge - self.cfg["rr"] * risk
        feat["pend"][direction] = {"edge": edge, "stop": stop, "tp": tp,
                                   "until": idx + self.cfg["wait"], "armed": idx}

    def _signals(self, idx, bars, feat):
        out = []
        closes = feat["closes"]
        if feat["swings"][idx] is not None:
            s = feat["swings"][idx]
            feat["last_" + s["kind"]] = s
        if idx > 0:
            for direction, key in (("BULLISH", "low"), ("BEARISH", "high")):
                last = feat.get("last_" + key)
                if last is None or direction in feat["pend"]:
                    continue
                lvl = last["extreme"]
                if self.cfg["use_breaker"]:
                    prev, cur = closes[idx - 1], closes[idx]
                    crossed = (prev <= lvl < cur) if direction == "BULLISH" \
                        else (prev >= lvl > cur)
                    if crossed:
                        self._arm(idx, feat, direction, lvl)
                else:
                    self._arm(idx, feat, direction, lvl)
        for direction in ("BULLISH", "BEARISH"):
            pend, expired = self._touch(idx, bars, feat["pend"], direction)
            if expired:
                feat["pend"].pop(direction, None)
                continue
            if pend is not None:
                out.append(self._trigger(pend["edge"], pend["stop"], pend["tp"],
                                         direction, idx))
                feat["pend"].pop(direction, None)
                break
        return out

    def ablations(self):
        return [("full", {}), ("no-breaker", {"use_breaker": False})]


class WyckoffSpringVol(_Base):
    """H11GF-006: prior-range spring + rvol>=1.5, NBO."""

    id = "H11GF-006"
    params = {"range_lookback": 50, "min_hold_bars": 30,
              "volume_median_window": 20, "volume_rvol_min": 1.5,
              "use_volume": True}

    def _build(self, bars, feat):
        from research.phase11g.features import wyckoff as WY
        from research.phase11g.features import volume as VOL
        feat["spr"] = WY.springs(bars, self.cfg["range_lookback"],
                                 self.cfg["min_hold_bars"])
        feat["vol"] = VOL.rolling_stats(bars, self.cfg["volume_median_window"])

    def _signals(self, idx, bars, feat):
        spr = feat["spr"][idx]
        vol = feat["vol"][idx]
        if spr["status"] != "OK":
            return []
        if self.cfg["use_volume"]:
            if vol["status"] != "OK":
                return []
            if (vol["value"]["rvol_median"] or 0.0) < self.cfg["volume_rvol_min"]:
                return []
        entry = float(bars[idx]["close"])
        stop = float(bars[idx]["low"])
        tp = spr["value"]["range_high"]
        if tp <= entry or entry - stop <= 0:
            return []
        return [_sig("BULLISH", entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}), ("no-volume", {"use_volume": False})]


class WyckoffUpthrustVol(_Base):
    """H11GF-007: mirror upthrust + volume, NBO."""

    id = "H11GF-007"
    params = {"range_lookback": 50, "min_hold_bars": 30,
              "volume_median_window": 20, "volume_rvol_min": 1.5,
              "use_volume": True}

    def _build(self, bars, feat):
        from research.phase11g.features import wyckoff as WY
        from research.phase11g.features import volume as VOL
        feat["up"] = WY.upthrusts(bars, self.cfg["range_lookback"],
                                  self.cfg["min_hold_bars"])
        feat["vol"] = VOL.rolling_stats(bars, self.cfg["volume_median_window"])

    def _signals(self, idx, bars, feat):
        up = feat["up"][idx]
        vol = feat["vol"][idx]
        if up["status"] != "OK":
            return []
        if self.cfg["use_volume"]:
            if vol["status"] != "OK":
                return []
            if (vol["value"]["rvol_median"] or 0.0) < self.cfg["volume_rvol_min"]:
                return []
        entry = float(bars[idx]["close"])
        stop = float(bars[idx]["high"])
        tp = up["value"]["range_low"]
        if tp >= entry or stop - entry <= 0:
            return []
        return [_sig("BEARISH", entry, stop, tp, "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}), ("no-volume", {"use_volume": False})]


class HTFSweep(_Base):
    """H11GF-008: 1m sweep + closed-15m trend agreement, NBO."""

    id = "H11GF-008"
    params = {"tolerance_atr": 0.1, "buffer_atr": 0.25, "rr": 2.0,
              "htf_trend_lookback": 50, "use_htf": True}

    def _build(self, bars, feat):
        from research.phase11g.features import mtf as MTF
        atr = _atr(bars, feat)
        feat["sw"] = F11.sweeps(bars, 50, self.cfg["tolerance_atr"], atr)
        htf = MTF.resample_15m(bars)
        feat["htf"] = htf
        feat["hctx"] = MTF.htf_context(htf)

    def _htf_trend_at(self, idx, bars, feat):
        t = int(bars[idx]["time"])
        best = None
        for j, h in enumerate(feat["htf"]):
            if h["availability_time"] <= t:
                best = j
            else:
                break
        if best is None or feat["hctx"][best]["status"] != "OK":
            return None
        return feat["hctx"][best]["value"]["trend"]

    def _signals(self, idx, bars, feat):
        sw = feat["sw"][idx]
        if sw is None or idx < 1:
            return []
        atr = feat["atr"][idx]
        if atr is None:
            return []
        if self.cfg["use_htf"]:
            trend = self._htf_trend_at(idx, bars, feat)
            want = "BULLISH" if sw["direction"] == "long" else "BEARISH"
            if trend != want:
                return []
        entry = float(bars[idx]["close"])
        buf = self.cfg["buffer_atr"] * atr
        if sw["direction"] == "long":
            stop = sw["extreme"] - buf
            risk = entry - stop
            if risk <= 0:
                return []
            return [_sig("BULLISH", entry, stop, entry + self.cfg["rr"] * risk,
                         "%s-%d" % (self.id, idx))]
        stop = sw["extreme"] + buf
        risk = stop - entry
        if risk <= 0:
            return []
        return [_sig("BEARISH", entry, stop, entry - self.cfg["rr"] * risk,
                     "%s-%d" % (self.id, idx))]

    def ablations(self):
        return [("full", {}), ("no-htf", {"use_htf": False})]


ALL = [SweepReclaim, SweepDisplacement, SweepDisplacementFVG,
       OrderBlockBOS, BreakerRetest, WyckoffSpringVol,
       WyckoffUpthrustVol, HTFSweep]
