"""11G-Q readiness gate (research-only, descriptive, no economics).

Determines whether the Phase 11G-P readiness trigger is now satisfied:
>= 6,175 contiguous, clean, zero-overlap, genuinely FRESH 1-minute
bars on one symbol, every event >= the re-derived fresh cutoff.

Read-only over the N raw store (re-verified immutable) plus UNSEALED
prior files for overlap comparison. NEVER touches sealed D3 (seal
counters asserted 0 before and after). Performs NO economics: no
hypotheses, no signals, no fills, no PnL, no thresholds, no fits.

Pure helpers are reused from the certified O module (no second
implementation). Output trigger_q.json is deterministic (sorted keys,
canonical hashes; no clock/UUID/random).

Cutoffs (deterministic constants, re-derived from artifacts):
- PRE_CUTOFF = 1788751380 (oos end; BTC pre-cutoff minutes drop).
- FRESH_START_Q = 1788912000 (2026-09-09T00:00Z; strictly after the
  latest exposed research minute 2026-09-08T23:59Z). Nothing newer
  was acquirable (Vision 404 past 09-08 at observation time), so no
  qualifying FRESH minutes exist yet.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

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

QDIR = Path(__file__).resolve().parent
NDIR = BASE_DIR / "research" / "phase11g_n"
NRAW = NDIR / "data" / "raw"
OUT = QDIR / "trigger_q.json"

PRE_CUTOFF = 1788751380
FRESH_START_Q = 1788912000

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
# HTTP 404 for 09-09 through 09-17, both BTCUSDT and ETHUSDT.
AVAILABILITY_OBSERVATION = {
    "observed": "2026-09-09",
    "latest_available_day": "2026-09-08",
    "unavailable_days": ["2026-09-09", "2026-09-10", "2026-09-11",
                         "2026-09-12", "2026-09-13", "2026-09-14",
                         "2026-09-15", "2026-09-16", "2026-09-17"],
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


def determine():
    from research.phase11g import datasets as DG
    from research.phase11g import fresh as FR
    seal_before = {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
                   "D3_LOAD": DG.D3_ACCESS["load"],
                   "FR_READ": FR.D3_ACCESS_11GD["read"],
                   "FR_HASH": FR.D3_ACCESS_11GD["hash"],
                   "FR_LOAD": FR.D3_ACCESS_11GD["load"]}
    assert all(v == 0 for v in seal_before.values()), seal_before
    assert REV.FEATURE_VERSION == "real-trade-features-v1"

    # Inventory: N store re-verified immutable; Q holds no raw store
    # (nothing newer was acquirable).
    n_files = sorted(NRAW.glob("*/*/*aggTrades*.zip"))
    assert n_files, "N store missing"
    for zp in n_files:
        man = json.loads((zp.parent / "acquisition_manifest.json").read_text())
        assert _sha256_bytes(zp.read_bytes()) == \
            man["files"]["aggTrades"]["local_sha256"], zp.name

    per_symbol, quality_sum = {}, {}
    for zp in n_files:
        symbol = zp.parent.parent.name
        trades, quality = parse_aggtrades(_read_zip(zp), symbol)
        bars, minutes = minute_bars(trades)
        clean = sorted(m for m in minutes
                       if not (symbol == "BTCUSDT" and m <= PRE_CUTOFF))
        cleanset = set(clean)
        asset = symbol[:3]
        slot = per_symbol.setdefault(asset, {"minutes": [], "events": 0})
        slot["minutes"].extend(clean)
        slot["events"] += sum(b["trades"] for b in bars if b["time"] in cleanset)
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

    # Trigger: >= 6175 contiguous clean FRESH bars, all events >= cutoff.
    # The N/O minutes carry descriptive exposure (REUSED, never FRESH),
    # and no post-cutoff minutes exist anywhere acquirable.
    symbols = {}
    trigger_met_any = False
    for asset, slot in sorted(per_symbol.items()):
        minutes = slot["minutes"]
        cont = contiguity(minutes)
        fresh_minutes = [m for m in minutes if m >= FRESH_START_Q]
        n_fresh_contig = len(fresh_minutes)  # contiguous: no gaps overall
        meets_scale = cont["unique"] >= WF_REQUIRED_BARS and cont["gap_count"] == 0
        meets_fresh = len(fresh_minutes) >= WF_REQUIRED_BARS
        try:
            V.build_folds(len(minutes), train_bars=WF_TRAIN_MIN,
                          test_bars=WF_TEST, purge_bars=WF_PURGE,
                          embargo_bars=WF_EMBARGO, step_bars=WF_STEP,
                          n_folds=WF_FOLDS)
            builder_ok = True
        except ValueError:
            builder_ok = False
        met = bool(meets_scale and meets_fresh and builder_ok and
                   overall == "ZERO_OVERLAP")
        trigger_met_any |= met
        symbols[asset] = {
            "clean_bars": len(minutes),
            "contiguous_bars": cont["unique"] if cont["gap_count"] == 0 else 0,
            "gap_count": cont["gap_count"],
            "fresh_bars_post_cutoff": len(fresh_minutes),
            "shortfall_vs_6175": max(0, WF_REQUIRED_BARS - len(minutes)),
            "builder_ok": builder_ok,
            "trigger_met": met}
    trigger = {"required_bars": WF_REQUIRED_BARS,
               "fresh_cutoff": FRESH_START_Q,
               "met": trigger_met_any,
               "symbols": symbols}
    decision = ("PROCEED_TO_EXECUTION"
                if trigger_met_any else "FULL_WF_DATA_INSUFFICIENT")

    freshness = {}
    for asset in sorted(per_symbol):
        bad = [n for n, o in overlap[asset].items() if o["verdict"] != "ZERO_OVERLAP"]
        label = classify_freshness(bool(bad), True, True)
        freshness[asset] = {"classification": label,
                            "overlapping_sets": sorted(bad),
                            "d3_overlap": "UNKNOWN_BY_SEAL (never inspected)"}

    seal_after = {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
                  "D3_LOAD": DG.D3_ACCESS["load"],
                  "FR_READ": FR.D3_ACCESS_11GD["read"],
                  "FR_HASH": FR.D3_ACCESS_11GD["hash"],
                  "FR_LOAD": FR.D3_ACCESS_11GD["load"]}
    assert all(v == 0 for v in seal_after.values()), seal_after
    result = {
        "phase": "11G-Q",
        "cutoffs": {"pre_cutoff": PRE_CUTOFF, "fresh_start_q": FRESH_START_Q,
                    "rule": "qualifying events require timestamp >= fresh_start_q"},
        "availability": AVAILABILITY_OBSERVATION,
        "n_files_reverified": len(n_files),
        "contiguity": {a: contiguity(s["minutes"]) for a, s in sorted(per_symbol.items())},
        "overlap": overlap,
        "overall_overlap": overall,
        "freshness": freshness,
        "quality": quality_sum,
        "trigger": trigger,
        "decision": decision,
        "economics_executed": False,
        "seal_counters_before": seal_before,
        "seal_counters_after": seal_after,
        "limitations": [
            "No post-cutoff minutes acquirable at observation time.",
            "All inventoried minutes carry N/O descriptive exposure (REUSED).",
            "D3 era unknowable without opening; D3 status UNKNOWN_BY_SEAL.",
            "aggTrade = aggregate event, not individual fill."],
    }
    result["code_hash"] = _sha256_bytes(Path(__file__).read_bytes())
    OUT.write_text(json.dumps(result, indent=1, sort_keys=True))
    return result


if __name__ == "__main__":
    r = determine()
    print(json.dumps({"trigger_met": r["trigger"]["met"],
                      "decision": r["decision"],
                      "symbols": {s: {"bars": v["clean_bars"] if "clean_bars" in v else None,
                                      "fresh": v["fresh_bars_post_cutoff"],
                                      "shortfall": v["shortfall_vs_6175"]}
                                  for s, v in r["trigger"]["symbols"].items()}},
                     indent=1, sort_keys=True))
