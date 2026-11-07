"""11E-Closure step 5: causal per-fold regime analysis (§11).

Each fold's regime thresholds are calibrated ONLY on bars with
timestamp strictly before that fold's OOS start, then frozen
and applied to the fold. Later folds, D3, and D1 never inform
earlier-fold thresholds (11E-Closure Issue 1).

Calibration chain (all strictly prior to the fold start):
  F1 <- calib_pre_d2
  F2 <- calib_pre_d2 + F1 bars
  F3 <- calib_pre_d2 + F1 + F2 bars
  F4 <- calib_pre_d2 + F1 + F2 + F3 + D1 bars (D1 Sep 1-5
        precedes D3 Sep 5 09:45, so it is prior, not future)

Volatility buckets from calibration ATR14/close terciles;
trend from close vs SMA50 at the entry bar. Indicators run
over (calibration tail + fold bars), so every value used at
an entry bar derives from bars at or before that bar.
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11e.common import load_raw_bars, trade_metrics
from research.phase11e.step2_folds import atr14_list, sma50_list

OUT = Path(__file__).resolve().parent / "data"


def load_inventory():
    """All bars keyed by source (chronological within each)."""
    inv = {}
    for name, rel in (("calib", "research/phase11e/data/calib_pre_d2.json"),
                      ("D1", "docs/audit/baseline_9s_delta_5000_raw.json"),
                      ("D2", "data/history/BTCUSDT_1m_oos.json"),
                      ("D3", "research/phase11e/data/oos_fresh.json")):
        doc = json.loads((BASE_DIR / rel).read_text())
        bars, _ = load_raw_bars(doc)
        inv[name] = bars
    return inv


def fold_slices(inv):
    d2 = inv["D2"]
    return {
        "F1": d2[0:3333], "F2": d2[3333:6666],
        "F3": d2[6666:10000], "F4": inv["D3"],
    }


def filter_prior(bars, oos_start):
    """Defense-in-depth: keep only bars strictly before OOS start."""
    return [b for b in bars if int(b["time"]) < oos_start]


def calibration_for_fold(fold, inv, fold_starts):
    """Bars available strictly before the fold's OOS start."""
    oos_start = fold_starts[fold]
    pool = list(inv["calib"])
    if fold in ("F2", "F3", "F4"):
        pool.extend(inv["D2"][0:3333])
    if fold in ("F3", "F4"):
        pool.extend(inv["D2"][3333:6666])
    if fold == "F4":
        pool.extend(inv["D2"][6666:10000])
        pool.extend(inv["D1"])
    pool.sort(key=lambda b: b["time"])
    return filter_prior(pool, oos_start)


def vol_thresholds(calib_bars):
    """Tercile cutoffs of ATR14/close over calibration bars only."""
    atr = atr14_list(calib_bars)
    ratios = sorted(
        a / float(b["close"])
        for a, b in zip(atr, calib_bars)
        if a is not None and float(b["close"]) > 0
    )
    if not ratios:
        raise ValueError("empty calibration ratios")
    return {
        "q33": ratios[min(len(ratios) - 1, len(ratios) // 3)],
        "q66": ratios[min(len(ratios) - 1, 2 * len(ratios) // 3)],
        "n": len(ratios),
    }


def classify_fold(trades, calib_bars, fold_bars):
    """Classify fold trades with frozen calibration thresholds.

    Indicators run over (calibration + fold) tape; thresholds
    come from calibration only. Returns (cells, thresholds).
    """
    thresholds = vol_thresholds(calib_bars)
    tape = list(calib_bars) + list(fold_bars)
    atr = atr14_list(tape)
    sma = sma50_list(tape)
    closes = [float(b["close"]) for b in tape]
    offset = len(calib_bars)
    by_ts = {}
    for k, b in enumerate(fold_bars):
        by_ts.setdefault(int(b["time"]), offset + k)
    cells = {}
    for t in trades:
        i = by_ts.get(int(t["entry_time"]))
        if i is None or atr[i] is None or sma[i] is None:
            key = "vol_unknown/trend_unknown"
        else:
            ratio = atr[i] / closes[i]
            vol = ("low" if ratio < thresholds["q33"]
                   else ("mid" if ratio < thresholds["q66"] else "high"))
            trend = "above" if closes[i] >= sma[i] else "below"
            key = "vol_%s/trend_%s" % (vol, trend)
        cells.setdefault(key, []).append(t)
    return cells, thresholds


def main():
    inv = load_inventory()
    folds = fold_slices(inv)
    fold_starts = {f: bars[0]["time"] for f, bars in folds.items() if bars}
    report = {"folds": {}}
    for fold, bars in folds.items():
        calib = calibration_for_fold(fold, inv, fold_starts)
        trades = json.loads((OUT / ("fold_%s_C_moderate.json" % fold)).read_text())
        cells, thresholds = classify_fold(trades, calib, bars)
        table = {}
        for key in sorted(cells):
            m = trade_metrics(cells[key])
            table[key] = {"n": m["trades"], "net": round(m["net_pnl"], 4),
                          "gross": round(m["gross_pnl"], 4),
                          "wins": m["wins"],
                          "expectancy": round(m["expectancy"], 4)}
        report["folds"][fold] = {
            "calibration": {
                "from": calib[0]["time"], "to": calib[-1]["time"],
                "n_bars": len(calib),
                "oos_start": fold_starts[fold],
                "causal": calib[-1]["time"] < fold_starts[fold],
            },
            "oos": {"from": bars[0]["time"] if bars else None,
                    "to": bars[-1]["time"] if bars else None,
                    "n_bars": len(bars)},
            "threshold_source": "calibration-only terciles (this fold)",
            "thresholds": thresholds,
            "cells": table,
        }
        print(fold, "calib_n=%d q33=%.2e q66=%.2e cells=%s" % (
            len(calib), thresholds["q33"], thresholds["q66"],
            {k: v["n"] for k, v in table.items()}), flush=True)
    (OUT / "step5_regimes.json").write_text(json.dumps(report, indent=1))
    print("STEP5-DONE", flush=True)


if __name__ == "__main__":
    main()
