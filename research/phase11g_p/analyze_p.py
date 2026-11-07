"""11G-P accumulation readiness analysis (research-only, descriptive).

Read-only over the N raw store (re-verified immutable) plus UNSEALED
prior files for overlap comparison. NEVER touches sealed D3 (seal
counters asserted 0 before and after). Performs NO economics: no
hypotheses, no signals, no fills, no PnL, no thresholds, no fits.

Pure helpers are reused from the certified O module (no second
implementation); P adds the cutoff discipline, the probe-recorded
availability observation (as metadata, never hashed), and the
readiness verdict. Output readiness_p.json is deterministic (sorted
keys, canonical hashes; no clock/UUID/random).

Cutoffs (deterministic constants):
- PRE_CUTOFF = 1788751380 (oos end; BTC pre-cutoff minutes drop).
- FRESH_START_P = 1788912000 (2026-09-09T00:00Z; strictly after the
  latest exposed research minute 2026-09-08T23:59Z, re-derived from
  artifacts, not assumed). No P minutes reach it: nothing newer was
  acquirable (Vision 404 past 09-08 at observation time).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f import features as F11  # noqa: E402 (certified descriptives)
from research.phase11f import validation as V  # noqa: E402 (certified WF geometry)
from research.phase11g_j.replay import events as REV  # noqa: E402 (certified side map)
from research.phase11g_o.analyze_o import (  # noqa: E402 (certified helpers)
    classify_freshness,
    contiguity,
    overlap_minutes,
    parse_aggtrades,
    minute_bars,
    prior_minute_sets,
)

PDIR = Path(__file__).resolve().parent
NDIR = BASE_DIR / "research" / "phase11g_n"
NRAW = NDIR / "data" / "raw"
PRAW = PDIR / "data" / "raw"
OUT = PDIR / "readiness_p.json"

PRE_CUTOFF = 1788751380
FRESH_START_P = 1788912000

WF_TRAIN_MIN = 2000
WF_TEST = 1000
WF_PURGE = 150
WF_EMBARGO = 25
WF_STEP = 1000
WF_FOLDS = 4
WF_REQUIRED_BARS = 5000 + WF_PURGE + WF_EMBARGO + WF_TEST  # 6175

# Provider availability observation (provenance metadata, NOT hashed
# into deterministic outputs; network state is not deterministic).
# Observed 2026-09-09: Vision daily aggTrades CHECKSUM probes return
# HTTP 404 for 09-09 through 09-16, both BTCUSDT and ETHUSDT.
AVAILABILITY_OBSERVATION = {
    "observed": "2026-09-09",
    "latest_available_day": "2026-09-08",
    "unavailable_days": ["2026-09-09", "2026-09-10", "2026-09-11",
                         "2026-09-12", "2026-09-13", "2026-09-14",
                         "2026-09-15", "2026-09-16"],
    "probe": "HTTP status of daily aggTrades CHECKSUM URLs",
    "result": "DATA_NOT_YET_AVAILABLE",
}


def _sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def _sha256_canonical(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _read_zip(zip_path):
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".csv")]
        assert len(names) == 1, names
        return z.read(names[0])


def _deciles(xs):
    s = sorted(xs)
    if not s:
        return {}
    def q(p):
        return s[min(len(s) - 1, int(p * len(s)))]
    return {"p10": q(0.10), "p25": q(0.25), "p50": q(0.50),
            "p75": q(0.75), "p90": q(0.90),
            "min": s[0], "max": s[-1], "n": len(s)}


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

    # P store must hold only post-cutoff acquisitions; today: empty.
    p_new = sorted(PRAW.glob("*/*/*aggTrades*.zip")) if PRAW.exists() else []
    # N store re-verified immutable against acquisition manifests.
    n_files = sorted(NRAW.glob("*/*/*aggTrades*.zip"))
    assert n_files, "N store missing"
    for zp in n_files:
        man = json.loads((zp.parent / "acquisition_manifest.json").read_text())
        assert _sha256_bytes(zp.read_bytes()) == \
            man["files"]["aggTrades"]["local_sha256"], zp.name

    per_symbol, quality_sum, file_recs = {}, {}, []
    for zp in n_files:
        symbol, date = zp.parent.parent.name, zp.parent.name
        trades, quality = parse_aggtrades(
            _read_zip(zp), symbol)
        bars, minutes = minute_bars(trades)
        clean = sorted(m for m in minutes
                       if not (symbol == "BTCUSDT" and m <= PRE_CUTOFF))
        cleanset = set(clean)
        asset = symbol[:3]
        slot = per_symbol.setdefault(asset, {"minutes": [], "events": 0,
                                             "files": []})
        slot["minutes"].extend(clean)
        slot["events"] += sum(b["trades"] for b in bars if b["time"] in cleanset)
        slot["files"].append("%s/%s" % (symbol, date))
        file_recs.append({"key": "%s/%s" % (symbol, date), "asset": asset,
                          "bars": bars, "clean": cleanset})
        q = quality_sum.setdefault(asset, {"rows": 0, "rejected": 0, "dups": 0,
                                           "ooo": 0})
        q["rows"] += quality["rows"]
        q["rejected"] += quality["rejected"]
        q["dups"] += quality["duplicate_trade_ids"]
        q["ooo"] += quality["out_of_order_events"]
    for asset in per_symbol:
        per_symbol[asset]["minutes"] = sorted(set(per_symbol[asset]["minutes"]))

    priors = prior_minute_sets()
    overlap, overall = {}, "ZERO_OVERLAP"
    for asset, slot in sorted(per_symbol.items()):
        overlap[asset] = {}
        for name, info in sorted(priors.items()):
            if asset not in info["assets"] or name.startswith("11G_N_"):
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
    for asset, slot in sorted(per_symbol.items()):
        minutes = slot["minutes"]
        contig[asset] = contiguity(minutes)
        try:
            folds = V.build_folds(len(minutes), train_bars=WF_TRAIN_MIN,
                                  test_bars=WF_TEST, purge_bars=WF_PURGE,
                                  embargo_bars=WF_EMBARGO, step_bars=WF_STEP,
                                  n_folds=WF_FOLDS)
            feasible = True
            assert V.validate_folds(folds) == []
            assert V.validate_expanding(folds) == []
            fold_rep = [{"fold": fo["fold"],
                         "train": [fo["train_start"], fo["train_end"]],
                         "test": [fo["test_start"], fo["test_end"]],
                         "purge": [fo["purge_start"], fo["purge_end"]],
                         "embargo": [fo["embargo_start"], fo["embargo_end"]]}
                        for fo in folds]
        except ValueError:
            feasible, fold_rep = False, []
        feasible_any |= feasible
        wf_per[asset] = {"available_clean_bars": len(minutes),
                         "feasible_full_wf": feasible, "folds": fold_rep}
        closes, by_day = [], {}
        mset = set(minutes)
        for fr in file_recs:
            if fr["asset"] != asset:
                continue
            for b in fr["bars"]:
                if b["time"] in mset:
                    closes.append(b["close"])
                    by_day.setdefault(b["time"] - (b["time"] % 86400), []).append(b)
        rets = [(c2 - c1) / c1 * 10000.0 for c1, c2 in zip(closes, closes[1:])]
        atr = [a for a in F11.atr14(
            [{"time": b["time"], "open": b["open"], "high": b["high"],
              "low": b["low"], "close": b["close"], "volume": b["volume"]}
             for fr in file_recs for b in fr["bars"] if b["time"] in mset])
            if a is not None]
        up = sum(1 for v in by_day.values() if v[-1]["close"] >= v[0]["open"])
        regimes[asset] = {
            "note": "descriptive only; must not be reused as thresholds",
            "return_bps_deciles": _deciles(rets),
            "up_days": up, "down_days": len(by_day) - up,
            "events_per_minute": round(slot["events"] / max(1, len(minutes)), 1)}
    wf_verdict = "WF_FEASIBLE" if feasible_any else "FULL_WF_INFEASIBLE"

    freshness = {}
    for asset, slot in sorted(per_symbol.items()):
        bad = [n for n, o in overlap[asset].items() if o["verdict"] != "ZERO_OVERLAP"]
        # N/O descriptive exposure (no fits, no economics) => REUSED.
        label = classify_freshness(bool(bad), True, True)
        freshness[asset] = {"classification": label,
                            "basis": ("N/O-store minutes re-verified; descriptive "
                                      "exposure in 11G-N/11G-O, no fits, no economics"),
                            "overlapping_sets": sorted(bad),
                            "d3_overlap": "UNKNOWN_BY_SEAL (never inspected)"}

    seal_after = {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
                  "D3_LOAD": DG.D3_ACCESS["load"],
                  "FR_READ": FR.D3_ACCESS_11GD["read"],
                  "FR_HASH": FR.D3_ACCESS_11GD["hash"],
                  "FR_LOAD": FR.D3_ACCESS_11GD["load"]}
    assert all(v == 0 for v in seal_after.values()), seal_after
    result = {
        "phase": "11G-P",
        "cutoffs": {"pre_cutoff": PRE_CUTOFF, "fresh_start_p": FRESH_START_P,
                    "rule": "P datasets require every event >= fresh_start_p"},
        "availability": AVAILABILITY_OBSERVATION,
        "p_new_files": len(p_new),
        "n_files_reverified": len(n_files),
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
        "events_total": sum(s["events"] for s in per_symbol.values()),
        "seal_counters_before": seal_before,
        "seal_counters_after": seal_after,
        "limitations": [
            "No new days acquirable at observation time (Vision 404 past 09-08).",
            "All minutes carry N/O descriptive exposure (REUSED, not pristine).",
            "D3 era unknowable without opening; D3 status UNKNOWN_BY_SEAL.",
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
                      "walk_forward": r["walk_forward"]["verdict"],
                      "p_new_files": r["p_new_files"]},
                     indent=1, sort_keys=True))
