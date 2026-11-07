"""11G-N fresh-data feasibility analysis (research-only, descriptive).

Reads ONLY the N raw store (data/raw/**) plus UNSEALED prior research
files for timestamp-overlap comparison. NEVER touches sealed D3
(no read/hash/load of holdout contents; seal counters asserted 0
before and after). Performs NO economics: no signals, no fills, no
PnL, no thresholds, no fits, no hypothesis evaluation.

Outputs feasibility.json (fully deterministic: sorted keys, stable
order, canonical hashes; no clock, no UUID, no random, no hash()).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f import features as F11  # noqa: E402 (certified descriptives)
from research.phase11f import validation as V  # noqa: E402 (certified WF geometry)
from research.phase11g_j.replay import events as REV  # noqa: E402 (certified side map)

NDIR = Path(__file__).resolve().parent
RAW = NDIR / "data" / "raw"
OUT = NDIR / "feasibility.json"

VENUE = "Binance"
MARKET = "UM futures (linear, USDT-margined)"
# Clean-minute rule (deterministic, overlap-driven): BTC minutes at or
# before the oos_fresh end (2026-09-07T03:23Z) are excluded as
# OVERLAPPING; everything kept is post-every-known-exposure.
BTC_CUTOFF_MINUTE = 1788751380 + 60  # first clean BTC minute (epoch seconds)

WF_TRAIN_MIN = 2000
WF_TEST = 1000
WF_PURGE = 150
WF_EMBARGO = 25
WF_STEP = 1000
WF_FOLDS = 4
WF_REQUIRED_BARS = 5000 + WF_PURGE + WF_EMBARGO + WF_TEST  # 6175


def _sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def _sha256_canonical(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _read_zip(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        assert len(names) == 1, names
        return z.read(names[0])


def parse_aggtrades(blob, symbol):
    """Returns (trades, quality). Rejects stay observable; never silent."""
    text = blob.decode()
    reader = csv.DictReader(io.StringIO(text))
    trades, rejects = [], []
    seen_ids, dup_ids = set(), 0
    out_of_order, bad_precision = 0, 0
    prev_ms = -1
    for i, row in enumerate(reader):
        try:
            t = REV.from_csv_row(row, i, symbol=symbol)
        except Exception as exc:
            rejects.append({"row": i, "reason": type(exc).__name__,
                            "detail": str(exc)[:120]})
            continue
        if t.price <= 0:
            rejects.append({"row": i, "reason": "impossible_price",
                            "detail": str(t.price)})
            continue
        if t.quantity <= 0:
            rejects.append({"row": i, "reason": "zero_or_negative_quantity",
                            "detail": str(t.quantity)})
            continue
        # Note: aggTrades CSVs carry no symbol column (the parser stamps
        # the caller-supplied symbol); symbol binding lives at file level
        # (manifest == directory == dataset key), pinned by test.
        if not (10 ** 12 <= t.transact_raw < 10 ** 14):
            bad_precision += 1
        if t.trade_id in seen_ids:
            dup_ids += 1
        else:
            seen_ids.add(t.trade_id)
        if t.event_ms < prev_ms:
            out_of_order += 1
        prev_ms = max(prev_ms, t.event_ms)
        trades.append(t)
    quality = {"rows": i + 1, "parsed": len(trades),
               "rejected": len(rejects),
               "rejects_by_reason": {},
               "duplicate_trade_ids": dup_ids,
               "out_of_order_events": out_of_order,
               "bad_precision_events": bad_precision,
               "reject_samples": rejects[:10]}
    for r in rejects:
        quality["rejects_by_reason"][r["reason"]] = \
            quality["rejects_by_reason"].get(r["reason"], 0) + 1
    return trades, quality


def parse_klines(blob):
    rows = list(csv.DictReader(io.StringIO(blob.decode())))
    out, bad = [], 0
    for r in rows:
        try:
            rec = {"open_time": int(r["open_time"]), "open": float(r["open"]),
                   "high": float(r["high"]), "low": float(r["low"]),
                   "close": float(r["close"]), "volume": float(r["volume"])}
        except (KeyError, ValueError):
            bad += 1
            continue
        if not (rec["low"] <= min(rec["open"], rec["close"]) and
                rec["high"] >= max(rec["open"], rec["close"])):
            bad += 1
            continue
        out.append(rec)
    return out, {"rows": len(rows), "parsed": len(out), "rejected": bad}


def minute_bars(trades):
    per_min = {}
    for t in trades:
        m = (int(t.event_ms) // 60000) * 60
        b = per_min.get(m)
        if b is None:
            b = per_min[m] = {"o": t.price, "h": t.price, "l": t.price,
                              "c": t.price, "v": 0.0, "n": 0}
        if t.price > b["h"]:
            b["h"] = t.price
        if t.price < b["l"]:
            b["l"] = t.price
        b["c"] = t.price
        b["v"] += t.quantity
        b["n"] += 1
    minutes = sorted(per_min)
    bars = [{"time": m, "open": per_min[m]["o"], "high": per_min[m]["h"],
             "low": per_min[m]["l"], "close": per_min[m]["c"],
             "volume": per_min[m]["v"], "trades": per_min[m]["n"]}
            for m in minutes]
    missing = [a + 60 for a, b in zip(minutes, minutes[1:]) for _ in range((b - a) // 60 - 1)]
    return bars, minutes, missing


def _deciles(xs):
    s = sorted(xs)
    if not s:
        return {}
    def q(p):
        i = min(len(s) - 1, int(p * len(s)))
        return s[i]
    return {"p10": q(0.10), "p25": q(0.25), "p50": q(0.50),
            "p75": q(0.75), "p90": q(0.90),
            "min": s[0], "max": s[-1], "n": len(s)}


def prior_minute_sets():
    """Minute sets of UNSEALED prior datasets (read-only). No D3."""
    sets = {}
    raw = json.loads((BASE_DIR / "docs" / "audit" /
                      "baseline_9s_delta_5000_raw.json").read_text())
    sets["gateA_snapshot_BTC"] = {"minutes": sorted(r["time"] for r in raw["raw"]),
                                  "venue": "UNKNOWN", "assets": ("BTC",)}
    for sym in ("BTC", "ETH"):
        for ds in ("D1", "D2"):
            p = BASE_DIR / "research" / "phase11f" / "data" / \
                ("universe_%s_%s.json" % (ds, sym))
            j = json.loads(p.read_text())
            sets["11F_%s_%s" % (ds, sym)] = {
                "minutes": sorted(b["time"] for b in j["candles"]),
                "venue": "UNKNOWN", "assets": (sym,)}
    for sym, fn in (("BTC", "fresh_11gg_gap_btcusdt.json"),
                    ("ETH", "fresh_11gg_gap_ethusdt.json")):
        j = json.loads((BASE_DIR / "research" / "phase11g_g" / "data" / fn).read_text())
        sets["11G_G_gap_%s" % sym] = {
            "minutes": sorted(b["time"] for b in j["candles"]),
            "venue": str(j.get("source", "UNKNOWN")), "assets": (sym,)}
    dev_blob = _read_zip(BASE_DIR / "research" / "phase11g_i" / "acquisition" /
                         "raw" / "BTCUSDT" / "2026-09-05" /
                         "BTCUSDT-aggTrades-2026-09-05.zip")
    dev_trades, _ = parse_aggtrades(dev_blob, "BTCUSDT")
    sets["11G_I_dev_BTC_trades"] = {
        "minutes": sorted(set((int(t.event_ms) // 60000) * 60 for t in dev_trades)),
        "venue": "Binance", "assets": ("BTC",)}
    oos = json.loads((BASE_DIR / "research" / "phase11e" / "data" /
                      "oos_fresh.json").read_text())
    sets["oos_fresh_BTC"] = {"minutes": sorted(b["time"] for b in oos["candles"]),
                             "venue": "Delta", "assets": ("BTC",)}
    return sets


def analyze():
    from research.phase11g import datasets as DG
    from research.phase11g import fresh as FR
    seal_before = {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
                   "D3_LOAD": DG.D3_ACCESS["load"],
                   "FR_READ": FR.D3_ACCESS_11GD["read"],
                   "FR_HASH": FR.D3_ACCESS_11GD["hash"],
                   "FR_LOAD": FR.D3_ACCESS_11GD["load"]}
    assert all(v == 0 for v in seal_before.values()), seal_before
    assert REV.FEATURE_VERSION == "real-trade-features-v1"

    day_files = sorted(list(RAW.glob("*/*/BTCUSDT-*.zip")) +
                       list(RAW.glob("*/*/ETHUSDT-*.zip")))
    assert day_files, "no N raw data; run acquire.py first"
    datasets, all_clean = {}, {}
    for zp in day_files:
        symbol = zp.parent.parent.name
        date = zp.parent.name
        manifest = json.loads((zp.parent / "acquisition_manifest.json").read_text())
        blob = zp.read_bytes()
        kind = "aggTrades" if "aggTrades" in zp.name else "klines"
        assert _sha256_bytes(blob) == manifest["files"][kind]["local_sha256"], zp.name
        key = "%s/%s" % (symbol, date)
        entry = datasets.setdefault(key, {
            "provider": "Binance", "venue": VENUE, "market": MARKET,
            "endpoint": manifest["files"].get(kind, {}).get("url", ""),
            "symbol": symbol, "date": date, "interval": "1m",
            "source_sha256": manifest["files"][kind]["local_sha256"],
            "provider_sha256": manifest["files"][kind]["provider_sha256"],
            "bytes": manifest["files"][kind]["bytes"]})
        if kind == "aggTrades":
            trades, quality = parse_aggtrades(_read_zip(zp), symbol)
            entry["aggtrades"] = {
                "rows": quality["rows"], "parsed": quality["parsed"],
                "quality": quality,
                "normalized_sha256": _sha256_canonical(
                    [[t.event_ms, t.source_index, t.price, t.quantity,
                      t.aggressor_side, t.trade_id] for t in trades]),
                "precision": "milliseconds (13-digit transact_time verified)",
                "aggressor_side": "REAL (provider is_buyer_maker mapping)",
                "event_model": "aggregate events (aggTrade != individual fill)"}
            bars, minutes, missing = minute_bars(trades)
            entry["bars"] = {"n_minutes": len(minutes),
                             "first_minute": minutes[0] if minutes else None,
                             "last_minute": minutes[-1] if minutes else None,
                             "missing_minutes": missing}
            entry["_minutes"] = minutes
            entry["_bars"] = bars
        else:
            klines, kq = parse_klines(_read_zip(zp))
            entry["klines"] = {"rows": kq["rows"], "parsed": kq["parsed"],
                               "rejected": kq["rejected"]}
            entry["_klines"] = klines
    # Kline cross-check + clean-minute filter (deterministic rule).
    for key, entry in datasets.items():
        symbol = entry["symbol"]
        tb = {b["time"]: b["close"] for b in entry["_bars"]}
        kb = {k["open_time"] // 1000: k["close"] for k in entry["_klines"]}
        both = sorted(set(tb) & set(kb))
        entry["kline_crosscheck"] = {
            "matched_minutes": len(both),
            "max_abs_close_diff": max([abs(tb[m] - kb[m]) for m in both] or [0.0])}
        keep, dropped = [], 0
        for m in entry["_minutes"]:
            if symbol == "BTCUSDT" and m < BTC_CUTOFF_MINUTE:
                dropped += 1
                continue
            keep.append(m)
        entry["clean_filter"] = {
            "rule": ("BTC minutes < 2026-09-07T03:24Z dropped (oos overlap); "
                     "ETH whole days kept (no post-08-31 ETH exposure)"
                     if symbol == "BTCUSDT" else
                     "whole days kept (no post-2026-08-31 ETH exposure)"),
            "kept_minutes": len(keep), "dropped_minutes": dropped}
        entry["_clean"] = keep
        all_clean.setdefault(symbol, []).extend(keep)
    for symbol in all_clean:
        all_clean[symbol] = sorted(set(all_clean[symbol]))

    priors = prior_minute_sets()
    overlap, overall = {}, "ZERO_OVERLAP"
    asset_of = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
    for symbol, minutes in sorted(all_clean.items()):
        mset = set(minutes)
        overlap[symbol] = {}
        for name, info in sorted(priors.items()):
            # Same-asset comparison only: shared timestamps across
            # different assets are different data, never overlap.
            if asset_of[symbol] not in info["assets"]:
                continue
            hit = sorted(mset & set(info["minutes"]))
            overlap[symbol][name] = {"venue": info["venue"],
                                     "overlap_minutes": len(hit),
                                     "verdict": ("OVERLAP_DETECTED" if hit
                                                 else "ZERO_OVERLAP")}
            if hit:
                overall = "OVERLAP_DETECTED"
                overlap[symbol][name]["first_overlap"] = hit[0]
                overlap[symbol][name]["last_overlap"] = hit[-1]
    freshness = {}
    for symbol, minutes in sorted(all_clean.items()):
        bad = [n for n, o in overlap[symbol].items()
               if o["verdict"] != "ZERO_OVERLAP"]
        freshness[symbol] = {
            "classification": ("FRESH" if not bad else "OVERLAPPING"),
            "basis": ("zero timestamp overlap vs all checkable prior sets; "
                      "new acquisition lineage; no analysis exposure"),
            "overlapping_sets": sorted(bad),
            "d3_overlap": "UNKNOWN (sealed; limitation recorded)"}

    wf = {"geometry": {"train_min": WF_TRAIN_MIN, "test": WF_TEST,
                       "purge": WF_PURGE, "embargo": WF_EMBARGO,
                       "step": WF_STEP, "folds": WF_FOLDS},
          "required_bars": WF_REQUIRED_BARS, "per_symbol": {}}
    feasible_any = False
    for symbol, minutes in sorted(all_clean.items()):
        n = len(minutes)
        try:
            V.build_folds(n, train_bars=WF_TRAIN_MIN, test_bars=WF_TEST,
                          purge_bars=WF_PURGE, embargo_bars=WF_EMBARGO,
                          step_bars=WF_STEP, n_folds=WF_FOLDS)
            feasible = True
        except ValueError:
            feasible = False
        feasible_any |= feasible
        wf["per_symbol"][symbol] = {"available_clean_bars": n,
                                    "feasible_full_wf": feasible}
    wf["verdict"] = "WF_FEASIBLE" if feasible_any else "FULL_WF_INFEASIBLE"

    regimes, symbols = {}, {}
    for symbol, minutes in sorted(all_clean.items()):
        day_keys = sorted(k for k in datasets if k.startswith(symbol + "/"))
        day_entries = [datasets[k] for k in day_keys]
        bar_by_time = {}
        for e in day_entries:
            for b in e["_bars"]:
                bar_by_time[b["time"]] = b
        bars = [bar_by_time[m] for m in minutes]
        closes = [b["close"] for b in bars]
        rets = [(c2 - c1) / c1 * 10000.0 for c1, c2 in zip(closes, closes[1:])]
        atr = [a for a in F11.atr14(
            [{"time": b["time"], "open": b["open"], "high": b["high"],
              "low": b["low"], "close": b["close"], "volume": b["volume"]}
             for b in bars]) if a is not None]
        ratio = [a / c for a, c in zip(atr, closes[-len(atr):])] if atr else []
        by_day = {}
        for b in bars:
            day = b["time"] - (b["time"] % 86400)
            by_day.setdefault(day, []).append(b)
        up = sum(1 for v in by_day.values() if v[-1]["close"] >= v[0]["open"])
        regimes[symbol] = {
            "note": "descriptive only; deciles must not be reused as thresholds",
            "return_bps_deciles": _deciles(rets),
            "atr14_close_ratio_deciles": _deciles(ratio),
            "up_days": up, "down_days": len(by_day) - up}
        tq = [e["aggtrades"] for e in day_entries if "aggtrades" in e]
        n_days = len(set(k.split("/")[1] for k in day_keys))
        span_full = (minutes[-1] - minutes[0]) // 60 + 1 if minutes else 0
        symbols[symbol] = {
            "days": sorted(set(k.split("/")[1] for k in day_keys)),
            "clean_bars": len(minutes),
            "clean_events": sum(t["parsed"] for t in tq),
            "temporal_span": [minutes[0], minutes[-1]] if minutes else [],
            "events_per_day": round(sum(t["parsed"] for t in tq) / max(1, n_days), 1),
            "missing_clean_minutes": span_full - len(minutes),
            "rejected_records": sum(t["quality"]["rejected"] for t in tq),
            "duplicate_trade_ids": sum(t["quality"]["duplicate_trade_ids"] for t in tq),
            "out_of_order_events": sum(t["quality"]["out_of_order_events"] for t in tq)}

    seal_after = {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
                  "D3_LOAD": DG.D3_ACCESS["load"],
                  "FR_READ": FR.D3_ACCESS_11GD["read"],
                  "FR_HASH": FR.D3_ACCESS_11GD["hash"],
                  "FR_LOAD": FR.D3_ACCESS_11GD["load"]}
    assert all(v == 0 for v in seal_after.values()), seal_after
    result = {
        "phase": "11G-N",
        "venue": "%s %s; Binance != Delta (explicit; never pooled)" % (VENUE, MARKET),
        "datasets": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                     for k, v in sorted(datasets.items())},
        "overlap": overlap,
        "overall_overlap": overall,
        "freshness": freshness,
        "walk_forward": wf,
        "regimes": regimes,
        "symbols": symbols,
        "seal_counters_before": seal_before,
        "seal_counters_after": seal_after,
        "limitations": [
            "D3 era unknowable without opening; D3 overlap recorded UNKNOWN.",
            "Vision daily files lag ~1 day; forward span grows with time.",
            "No historical quotes/L2/funding/OI in the bulk archive.",
            "aggTrade = aggregate event, not individual fill.",
            "Millisecond precision (13-digit transact_time verified).",
            "Regime deciles are descriptive; must not be reused as thresholds."],
    }
    result["code_hash"] = _sha256_bytes(Path(__file__).read_bytes())
    OUT.write_text(json.dumps(result, indent=1, sort_keys=True))
    return result


if __name__ == "__main__":
    r = analyze()
    print(json.dumps({"overall_overlap": r["overall_overlap"],
                      "freshness": {s: v["classification"]
                                    for s, v in r["freshness"].items()},
                      "walk_forward": r["walk_forward"]["verdict"],
                      "symbols": {s: {"bars": v["clean_bars"],
                                      "events": v["clean_events"]}
                                  for s, v in r["symbols"].items()}},
                     indent=1, sort_keys=True))
