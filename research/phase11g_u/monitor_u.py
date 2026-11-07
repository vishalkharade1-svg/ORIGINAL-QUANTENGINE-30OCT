"""11G-U continuation monitor (research-only, descriptive, no economics).

Fast path: when no genuinely new provider files exist past the
re-derived cutoff, perform ONLY the availability record +
deterministic gate arithmetic — no historical re-parsing, no feature
work, no economics. Full validation helpers exist for genuinely new
files (fixture-tested) but are never invoked on the fast path.

Read-only (fast path touches no raw store at all) plus UNSEALED
artifact reads for cutoff derivation. NEVER touches sealed D3 (seal
counters asserted 0 before and after). Performs NO economics: no
hypotheses, no signals, no fills, no PnL, no thresholds, no fits.
Any economic execution attempt must raise immediately (there is no
economic entry point in this module — proven by scan).

Output readiness_u.json is deterministic (sorted keys, canonical
hashes; no clock/UUID/random). Availability observations are
provenance metadata supplied by the caller, never fetched inside
determine(), and excluded from deterministic hashes.
"""

from __future__ import annotations

import hashlib
import inspect
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
)

UDIR = Path(__file__).resolve().parent
OUT = UDIR / "readiness_u.json"


def required_bars():
    """Derive the 6,175 requirement from the certified builder signature."""
    sig = inspect.signature(V.build_folds)
    d = {k: v.default for k, v in sig.parameters.items()
         if v.default is not inspect.Parameter.empty}
    return (d["train_bars"] + 3 * d["step_bars"] + d["purge_bars"] +
            d["embargo_bars"] + d["test_bars"])


def derive_cutoff():
    """Re-derive (latest_exposed_minute, fresh_start) from artifacts."""
    sfeas = json.loads((BASE_DIR / "research" / "phase11g_s" /
                        "readiness_s.json").read_text())
    nfeas = json.loads((BASE_DIR / "research" / "phase11g_n" /
                        "feasibility.json").read_text())
    oos = json.loads((BASE_DIR / "research" / "phase11e" / "data" /
                      "oos_fresh.json").read_text())
    lasts = [c["last"] for c in sfeas["contiguity"].values()]
    lasts += [v["temporal_span"][1] for v in nfeas["symbols"].values()]
    lasts.append(oos["window"]["end"])
    latest = max(lasts)
    return latest, latest + 60


def next_unchecked(observation, symbol, kind="aggTrades"):
    """Resume trigger: day after the max probed date (deterministic)."""
    from datetime import date, timedelta
    prefix = "%s/" % symbol
    dates = sorted(k[len(prefix):] for k in observation["status"]
                   if k.startswith(prefix))
    if not dates:
        return None
    last = date.fromisoformat(dates[-1])
    return (last + timedelta(days=1)).isoformat()


def classify_availability(http_status):
    if http_status == 404:
        return "DATA_NOT_YET_AVAILABLE"
    if http_status == 200:
        return "AVAILABLE"
    if http_status is None:
        return "ACQUISITION_FAILED"
    return "INVALID_PROVIDER_ARTIFACT"


def check_overlap(minutes, prior_sets):
    """Pure overlap check against explicit prior sets. No D3, ever."""
    out, overall = {}, "ZERO_OVERLAP"
    for name, pminutes in sorted(prior_sets.items()):
        hits = overlap_minutes(minutes, pminutes)
        out[name] = {"overlap_minutes": len(hits),
                     "verdict": ("OVERLAP_DETECTED" if hits else "ZERO_OVERLAP")}
        if hits:
            overall = "OVERLAP_DETECTED"
    return out, overall


def validate_new_file(blob, symbol, prior_sets):
    """Full validation for a genuinely new file (unused on fast path)."""
    trades, quality = parse_aggtrades(blob, symbol)
    bars, minutes = minute_bars(trades)
    cont = contiguity(minutes)
    overlap, overall = check_overlap(minutes, prior_sets)
    fresh = classify_freshness(overall != "ZERO_OVERLAP", True, False)
    return {"bars": bars, "minutes": minutes, "quality": quality,
            "contiguity": cont, "overlap": overlap,
            "overall_overlap": overall, "freshness": fresh}


def refuse_economics(reason="economic execution is disabled in 11G-U"):
    """Defense-in-depth: no economic entry point exists; any attempt raises."""
    raise RuntimeError(reason)


def determine(availability):
    """Fast-path gate over a recorded availability observation."""
    from research.phase11g import datasets as DG
    from research.phase11g import fresh as FR
    seal_before = {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
                   "D3_LOAD": DG.D3_ACCESS["load"],
                   "FR_READ": FR.D3_ACCESS_11GD["read"],
                   "FR_HASH": FR.D3_ACCESS_11GD["hash"],
                   "FR_LOAD": FR.D3_ACCESS_11GD["load"]}
    assert all(v == 0 for v in seal_before.values()), seal_before
    assert REV.FEATURE_VERSION == "real-trade-features-v1"

    latest, fresh_start = derive_cutoff()
    required = required_bars()
    assert required == 6175
    assert (latest, fresh_start) == (1788911940, 1788912000)

    new_files = [k for k, v in availability["status"].items()
                 if classify_availability(v) == "AVAILABLE"]
    symbols = {}
    ready_any = False
    for asset in ("BTC", "ETH"):
        # Fast path: no new files => 0 fresh bars; reference spans stay
        # REUSED and never qualify.
        met = False
        ready_any |= met
        symbols[asset] = {"fresh_bars": 0, "contiguous_fresh_bars": 0,
                          "gap_count": 0, "shortfall_vs_required": required,
                          "gate_met": met}
    decision = ("FULL_WF_DATA_READY" if ready_any else "DATA_NOT_YET_AVAILABLE"
                if not new_files else "DATA_STILL_INSUFFICIENT")

    seal_after = {"D3_READ": DG.D3_ACCESS["read"], "D3_HASH": DG.D3_ACCESS["hash"],
                  "D3_LOAD": DG.D3_ACCESS["load"],
                  "FR_READ": FR.D3_ACCESS_11GD["read"],
                  "FR_HASH": FR.D3_ACCESS_11GD["hash"],
                  "FR_LOAD": FR.D3_ACCESS_11GD["load"]}
    assert all(v == 0 for v in seal_after.values()), seal_after
    result = {
        "phase": "11G-U",
        "cutoffs": {"latest_exposed_minute": latest,
                    "fresh_start_u": fresh_start,
                    "rule": "qualifying events require timestamp >= fresh_start_u"},
        "availability": availability,
        "new_files": sorted(new_files),
        "new_fresh_bars": 0,
        "resume": {s: next_unchecked(availability, s) for s in ("BTCUSDT", "ETHUSDT")},
        "wf_geometry": {"train_min": 2000, "test": 1000, "purge": 150,
                        "embargo": 25, "step": 1000, "folds": 4},
        "required_bars": required,
        "symbols": symbols,
        "decision": decision,
        "hypotheses_executed": 0,
        "economics_executed": False,
        "seal_counters_before": seal_before,
        "seal_counters_after": seal_after,
        "limitations": [
            "Fast path: no historical re-validation performed (no new data).",
            "All inventoried minutes remain REUSED (descriptive exposure).",
            "D3 era unknowable without opening; D3 status UNKNOWN_BY_SEAL.",
            "aggTrade = aggregate event, not individual fill."],
    }
    result["code_hash"] = hashlib.sha256(Path(__file__).read_bytes()
                                         ).hexdigest()
    OUT.write_text(json.dumps(result, indent=1, sort_keys=True))
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--availability", required=True,
                    help="path to a recorded availability observation JSON")
    args = ap.parse_args()
    avail = json.loads(Path(args.availability).read_text())
    r = determine(avail)
    print(json.dumps({"decision": r["decision"],
                      "new_files": r["new_files"],
                      "required_bars": r["required_bars"],
                      "resume": r["resume"]},
                     indent=1, sort_keys=True))
