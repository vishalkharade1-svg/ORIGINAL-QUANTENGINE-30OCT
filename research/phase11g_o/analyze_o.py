"""11G-O expansion analysis (research-only, descriptive, no economics).

Read-only over the N raw store (data verified, never modified) plus
UNSEALED prior files for overlap comparison. NEVER touches sealed D3
(seal counters asserted 0 before and after). Performs NO economics:
no hypotheses, no signals, no fills, no PnL, no thresholds, no fits.

Pure helpers (overlap_minutes, contiguity, classify_freshness) are
unit-testable; the full pipeline writes feasibility_o.json
(deterministic: sorted keys, canonical hashes; no clock/UUID/random).

Temporal cutoffs (deterministic constants, no wall clock):
- PRE_CUTOFF = 1788751380 (oos_fresh end 2026-09-07T03:23Z; N's BTC
  filter boundary, re-verified here).
- FRESH_START_O = 1788912000 (2026-09-09T00:00Z; strictly after the
  latest exposed research minute 2026-09-08T23:59Z). The next
  expansion attempt must acquire only events >= FRESH_START_O.
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

ODIR = Path(__file__).resolve().parent
NDIR = BASE_DIR / "research" / "phase11g_n"
NRAW = NDIR / "data" / "raw"
ORAW = ODIR / "data" / "raw"
OUT = ODIR / "feasibility_o.json"

PRE_CUTOFF = 1788751380
FRESH_START_O = 1788912000

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


def overlap_minutes(a_minutes, b_minutes):
    """Sorted shared minutes (empty = ZERO_OVERLAP). Pure."""
    return sorted(set(a_minutes) & set(b_minutes))


def contiguity(minutes):
    """Span/gap accounting for a minute list. Pure; gaps never hidden."""
    uniq = sorted(set(minutes))
    if not uniq:
        return {"total": len(minutes), "unique": 0, "contiguous": 0,
                "gap_count": 0, "largest_gap_minutes": 0,
                "first": None, "last": None, "expected": 0}
    gaps = [b - a - 60 for a, b in zip(uniq, uniq[1:]) if b - a > 60]
    return {"total": len(minutes), "unique": len(uniq),
            "contiguous": len(uniq) - sum(g // 60 for g in gaps),
            "gap_count": len(gaps),
            "largest_gap_minutes": max([g // 60 for g in gaps] or [0]),
            "first": uniq[0], "last": uniq[-1],
            "expected": (uniq[-1] - uniq[0]) // 60 + 1}


def classify_freshness(has_overlap, lineage_new, exposed):
    """FRESH only with zero overlap, new lineage, and no exposure."""
    if has_overlap:
        return "OVERLAPPING"
    if exposed:
        return "REUSED"
    if not lineage_new:
        return "UNKNOWN"
    return "FRESH"


def _read_zip(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        assert len(names) == 1, names
        return z.read(names[0])


def parse_aggtrades(blob, symbol):
    text = blob.decode()
    reader = csv.DictReader(io.StringIO(text))
    trades, rejects = [], []
    seen_ids, dup_ids = set(), 0
    out_of_order = 0
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
        # Millisecond precision is enforced inside from_csv_row (raises
        # otherwise), so every parsed trade here is 13-digit by
        # construction; no separate counter can trigger.
        if t.trade_id in seen_ids:
            dup_ids += 1
        else:
            seen_ids.add(t.trade_id)
        if t.event_ms < prev_ms:
            out_of_order += 1
        prev_ms = max(prev_ms, t.event_ms)
        trades.append(t)
    quality = {"rows": i + 1, "parsed": len(trades),
               "rejected": len(rejects), "rejects_by_reason": {},
               "duplicate_trade_ids": dup_ids,
               "out_of_order_events": out_of_order,
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
    return ([{"time": m, "open": per_min[m]["o"], "high": per_min[m]["h"],
              "low": per_min[m]["l"], "close": per_min[m]["c"],
              "volume": per_min[m]["v"], "trades": per_min[m]["n"]}
             for m in minutes], minutes)


def _deciles(xs):
    s = sorted(xs)
    if not s:
        return {}
    def q(p):
        return s[min(len(s) - 1, int(p * len(s)))]
    return {"p10": q(0.10), "p25": q(0.25), "p50": q(0.50),
            "p75": q(0.75), "p90": q(0.90),
            "min": s[0], "max": s[-1], "n": len(s)}


def prior_minute_sets():
    """UNSEALED prior minute sets (read-only). No D3, ever."""
    sets = {}
    raw = json.loads((BASE_DIR / "docs" / "audit" /
                      "baseline_9s_delta_5000_raw.json").read_text())
    sets["gateA_snapshot_BTC"] = {"minutes": sorted(r["time"] for r in raw["raw"]),
                                  "assets": ("BTC",)}
    for sym in ("BTC", "ETH"):
        for ds in ("D1", "D2"):
            p = BASE_DIR / "research" / "phase11f" / "data" / \
                ("universe_%s_%s.json" % (ds, sym))
            j = json.loads(p.read_text())
            sets["11F_%s_%s" % (ds, sym)] = {
                "minutes": sorted(b["time"] for b in j["candles"]),
                "assets": (sym,)}
    for sym, fn in (("BTC", "fresh_11gg_gap_btcusdt.json"),
                    ("ETH", "fresh_11gg_gap_ethusdt.json")):
        j = json.loads((BASE_DIR / "research" / "phase11g_g" / "data" / fn).read_text())
        sets["11G_G_gap_%s" % sym] = {
            "minutes": sorted(b["time"] for b in j["candles"]),
            "assets": (sym,)}
    dev_blob = _read_zip(BASE_DIR / "research" / "phase11g_i" / "acquisition" /
                         "raw" / "BTCUSDT" / "2026-09-05" /
                         "BTCUSDT-aggTrades-2026-09-05.zip")
    dev_trades, _ = parse_aggtrades(dev_blob, "BTCUSDT")
    sets["11G_I_dev_BTC_trades"] = {
        "minutes": sorted(set((int(t.event_ms) // 60000) * 60 for t in dev_trades)),
        "assets": ("BTC",)}
    oos = json.loads((BASE_DIR / "research" / "phase11e" / "data" /
                      "oos_fresh.json").read_text())
    sets["oos_fresh_BTC"] = {"minutes": sorted(b["time"] for b in oos["candles"]),
                             "assets": ("BTC",)}
    nfeas = json.loads((NDIR / "feasibility.json").read_text())
    for sym, info in nfeas["symbols"].items():
        a, b = info["temporal_span"]
        sets["11G_N_%s" % sym[:3]] = {"minutes": list(range(a, b + 60, 60)),
                                      "assets": (sym[:3],)}
    return sets


def inventory():
    """All O-scope day-files: N store (re-verified) + O store (new)."""
    files = []
    for root in (NRAW, ORAW):
        if not root.exists():
            continue
        for zp in sorted(root.glob("*/*/*aggTrades*.zip")):
            symbol, date = zp.parent.parent.name, zp.parent.name
            mp = zp.parent / "acquisition_manifest.json"
            man = json.loads(mp.read_text()) if mp.exists() else None
            files.append({"zip": zp, "symbol": symbol, "date": date,
                          "manifest": man,
                          "origin": "11G-N" if root == NRAW else "11G-O"})
    return files


def analyze():
    from research.phase11g import datasets as DG
    from research.phase11g import fresh as FR
    seal_before = {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
                   "D3_LOAD": DG.D3_ACCESS["load"],
                   "FR_READ": FR.D3_ACCESS_11GD["read"],
                   "FR_HASH": FR.D3_ACCESS_11GD["hash"],
                   "FR_LOAD": FR.D3_ACCESS_11GD["load"]}
    assert all(v == 0 for v in seal_before.values()), seal_before

    files = inventory()
    assert files, "no inventory; N store missing"
    # Immutability: every N file re-hashes to its acquisition manifest.
    for f in files:
        if f["manifest"] is None:
            raise ValueError("missing manifest for %s" % f["zip"])
        blob = f["zip"].read_bytes()
        assert _sha256_bytes(blob) == f["manifest"]["files"]["aggTrades"]["local_sha256"], f["zip"].name

    per_symbol_minutes, quality_sum, file_bars = {}, {}, []
    day_records = {}
    for f in files:
        trades, quality = parse_aggtrades(_read_zip(f["zip"]), f["symbol"])
        bars, minutes = minute_bars(trades)
        # BTC pre-cutoff minutes are oos-overlapping by construction.
        cleanset = set(m for m in minutes
                       if not (f["symbol"] == "BTCUSDT" and m <= PRE_CUTOFF))
        clean = sorted(cleanset)
        file_bars.append({"asset": f["symbol"][:3], "bars": bars, "clean": cleanset})
        key = "%s/%s" % (f["symbol"], f["date"])
        klines, kq, xcheck = [], {"rows": 0, "parsed": 0, "rejected": 0}, {}
        kname = f["zip"].name.replace("-aggTrades-", "-1m-")
        kpath = f["zip"].parent / kname
        if kpath.exists():
            klines, kq = parse_klines(_read_zip(kpath))
            tb = {b["time"]: b["close"] for b in bars}
            kb = {k["open_time"] // 1000: k["close"] for k in klines}
            both = sorted(set(tb) & set(kb))
            diffs = [abs(tb[m] - kb[m]) for m in both]
            xcheck = {"matched_minutes": len(both),
                      "max_abs_close_diff": max(diffs or [0.0]),
                      "mismatch_count": sum(1 for d in diffs if d != 0.0)}
        day_records[key] = {
            "provider": "Binance", "venue": "Binance UM futures",
            "symbol": f["symbol"], "date": f["date"], "origin": f["origin"],
            "source_url": f["manifest"]["files"]["aggTrades"]["url"],
            "source_sha256": f["manifest"]["files"]["aggTrades"]["local_sha256"],
            "provider_sha256": f["manifest"]["files"]["aggTrades"]["provider_sha256"],
            "bytes": f["manifest"]["files"]["aggTrades"]["bytes"],
            "normalized_sha256": _sha256_canonical(
                [[t.event_ms, t.source_index, t.price, t.quantity,
                  t.aggressor_side, t.trade_id] for t in trades]),
            "schema_version": "um-aggtrades-csv-v1",
            "feature_version": REV.FEATURE_VERSION,
            "bars_clean": len(clean), "events_clean": sum(
                b["trades"] for b in bars if b["time"] in cleanset),
            "klines": kq, "kline_crosscheck": xcheck}
        asset = f["symbol"][:3]
        slot = per_symbol_minutes.setdefault(asset, {"minutes": [], "events": 0})
        slot["minutes"].extend(clean)
        slot["events"] += sum(b["trades"] for b in bars if b["time"] in cleanset)
        q = quality_sum.setdefault(asset, {"rows": 0, "rejected": 0, "dups": 0,
                                           "ooo": 0})
        q["rows"] += quality["rows"]
        q["rejected"] += quality["rejected"]
        q["dups"] += quality["duplicate_trade_ids"]
        q["ooo"] += quality["out_of_order_events"]
    for asset in per_symbol_minutes:
        per_symbol_minutes[asset]["minutes"] = sorted(
            set(per_symbol_minutes[asset]["minutes"]))

    priors = prior_minute_sets()
    overlap, overall = {}, "ZERO_OVERLAP"
    for asset, slot in sorted(per_symbol_minutes.items()):
        overlap[asset] = {}
        for name, info in sorted(priors.items()):
            if asset not in info["assets"]:
                continue
            if name == "11G_N_%s" % asset:
                # Self-lineage: the same minutes re-verified, not overlap.
                continue
            hits = overlap_minutes(slot["minutes"], info["minutes"])
            overlap[asset][name] = {"overlap_minutes": len(hits),
                                    "verdict": ("OVERLAP_DETECTED" if hits
                                                else "ZERO_OVERLAP")}
            if hits:
                overall = "OVERLAP_DETECTED"
                overlap[asset][name]["first_overlap"] = hits[0]
                overlap[asset][name]["last_overlap"] = hits[-1]

    contig, wf_per, regimes = {}, {}, {}
    feasible_any = False
    for asset, slot in sorted(per_symbol_minutes.items()):
        minutes = slot["minutes"]
        contig[asset] = contiguity(minutes)
        try:
            folds = V.build_folds(len(minutes), train_bars=WF_TRAIN_MIN,
                                  test_bars=WF_TEST, purge_bars=WF_PURGE,
                                  embargo_bars=WF_EMBARGO, step_bars=WF_STEP,
                                  n_folds=WF_FOLDS)
            feasible, fold_rep = True, [
                {"fold": fo["fold"], "train": [fo["train_start"], fo["train_end"]],
                 "purge": [fo["purge_start"], fo["purge_end"]],
                 "embargo": [fo["embargo_start"], fo["embargo_end"]],
                 "test": [fo["test_start"], fo["test_end"]]} for fo in folds]
        except ValueError:
            feasible, fold_rep = False, []
        feasible_any |= feasible
        wf_per[asset] = {"available_clean_bars": len(minutes),
                         "feasible_full_wf": feasible, "folds": fold_rep}
        closes = []
        by_day = {}
        mset = set(minutes)
        for fb in file_bars:
            if fb["asset"] != asset:
                continue
            for b in fb["bars"]:
                if b["time"] in mset:
                    closes.append(b["close"])
                    by_day.setdefault(b["time"] - (b["time"] % 86400), []).append(b)
        rets = [(c2 - c1) / c1 * 10000.0 for c1, c2 in zip(closes, closes[1:])]
        up = sum(1 for v in by_day.values() if v[-1]["close"] >= v[0]["open"])
        regimes[asset] = {
            "note": "descriptive only; must not be reused as thresholds",
            "return_bps_deciles": _deciles(rets),
            "up_days": up, "down_days": len(by_day) - up,
            "events_per_minute": round(slot["events"] / max(1, len(minutes)), 1)}
    wf_verdict = "WF_FEASIBLE" if feasible_any else "FULL_WF_INFEASIBLE"

    freshness = {}
    dropped_events = {}
    for asset, slot in sorted(per_symbol_minutes.items()):
        bad = [n for n, o in overlap[asset].items() if o["verdict"] != "ZERO_OVERLAP"]
        exposed = True  # N descriptively analyzed these minutes (no fits/economics)
        label = classify_freshness(bool(bad), True, exposed)
        freshness[asset] = {"classification": label,
                            "basis": ("N-store minutes re-verified; descriptive "
                                      "exposure in 11G-N, no fits, no economics"),
                            "overlapping_sets": sorted(bad),
                            "d3_overlap": "UNKNOWN (sealed; limitation recorded)"}
        dropped_events[asset] = (quality_sum[asset]["rows"] - slot["events"])

    seal_after = {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
                  "D3_LOAD": DG.D3_ACCESS["load"],
                  "FR_READ": FR.D3_ACCESS_11GD["read"],
                  "FR_HASH": FR.D3_ACCESS_11GD["hash"],
                  "FR_LOAD": FR.D3_ACCESS_11GD["load"]}
    assert all(v == 0 for v in seal_after.values()), seal_after
    result = {
        "phase": "11G-O",
        "cutoffs": {"pre_cutoff": PRE_CUTOFF,
                    "fresh_start_o": FRESH_START_O,
                    "cutoff_rule": "next expansion acquires only events >= fresh_start_o"},
        "inventory_files": len(files),
        "origins": sorted(set(f["origin"] for f in files)),
        "datasets": {k: dict(v, transformation_hash="see code_hash")
                     for k, v in sorted(day_records.items())},
        "contiguity": contig,
        "overlap": overlap,
        "overall_overlap": overall,
        "freshness": freshness,
        "quality": quality_sum,
        "walk_forward": {"geometry": {"train_min": WF_TRAIN_MIN, "test": WF_TEST,
                                      "purge": WF_PURGE, "embargo": WF_EMBARGO,
                                      "step": WF_STEP, "folds": WF_FOLDS},
                         "required_bars": WF_REQUIRED_BARS,
                         "per_symbol": wf_per,
                         "verdict": wf_verdict},
        "regimes": regimes,
        "events_total": sum(s["events"] for s in per_symbol_minutes.values()),
        "dropped_events": dropped_events,
        "seal_counters_before": seal_before,
        "seal_counters_after": seal_after,
        "limitations": [
            "No new days acquirable at analysis time (Vision 404 past 09-08).",
            "N-store minutes carry descriptive exposure (REUSED, not pristine).",
            "D3 era unknowable without opening; D3 overlap UNKNOWN.",
            "aggTrade = aggregate event, not individual fill.",
            "Regime descriptives must not be reused as thresholds."],
    }
    result["code_hash"] = _sha256_bytes(Path(__file__).read_bytes())
    OUT.write_text(json.dumps(result, indent=1, sort_keys=True))
    return result


if __name__ == "__main__":
    r = analyze()
    print(json.dumps({"overall_overlap": r["overall_overlap"],
                      "freshness": {s: v["classification"]
                                    for s, v in r["freshness"].items()},
                      "contiguity": {s: {"bars": v["unique"],
                                         "gaps": v["gap_count"]}
                                     for s, v in r["contiguity"].items()},
                      "walk_forward": r["walk_forward"]["verdict"]},
                     indent=1, sort_keys=True))
