"""11E-Closure step 7: per-fold random-timing baselines (§14).

Each fold's control uses ONLY that fold's bars: candidate
entries, ATR context, exits, and mark-to-market all stay
inside the fold. No later fold (and never D3 while
evaluating D2) is consulted (11E-Closure Issue 2).

Pre-registered boundary rule (deterministic, fixed before
seeing corrected results): a simulated trade unclosed at
the fold's last bar is marked to market at that bar's
close. Draw count per fold is fixed (500); trades per draw
equal the strategy's fill count in that fold (F3: 0 fills
-> control undefined -> reported INSUFFICIENT, no draws).

Stop = k*ATR14, TP = 2k*ATR14 with k = frozen IS median;
fixed $500 notional; scenario-C costs; touch exits with
SL-first ambiguity (production semantics).
"""
import json
import random
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11e.common import load_raw_bars
from research.phase11e.step2_folds import atr14_list

OUT = Path(__file__).resolve().parent / "data"
N_DRAWS = 500
RATE, BPS = 0.0005, 2.0
TRADE_COST = 500.0 * RATE + 2 * 500.0 * BPS / 10000.0


def load_k():
    return float(json.loads((OUT / "step2_is_stats.json").read_text())["k_median"])


def fold_bars():
    docs = {}
    for name, rel in (("D2", "data/history/BTCUSDT_1m_oos.json"),
                      ("D3", "research/phase11e/data/oos_fresh.json")):
        doc = json.loads((BASE_DIR / rel).read_text())
        bars, _ = load_raw_bars(doc)
        docs[name] = bars
    d2 = docs["D2"]
    return {
        "F1": d2[0:3333], "F2": d2[3333:6666],
        "F3": d2[6666:10000], "F4": docs["D3"],
    }


def fold_strategy_nets(fold):
    trades = json.loads((OUT / ("fold_%s_C_moderate.json" % fold)).read_text())
    return [t["net"] for t in trades]


def simulate_fold(bars, entries, k):
    """Simulate entries confined to one fold's bars.

    entries: list of (index, direction) with index < len(bars)-1.
    Exits scan bars[idx+1:] only; unclosed trades MTM at the
    fold's last close (pre-registered boundary rule). Every
    exit timestamp is <= the fold's last bar by construction.
    """
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    last_ts = int(bars[-1]["time"])
    atr = atr14_list(bars)
    out = []
    for idx, direction in entries:
        assert 0 <= idx < len(bars) - 1, "entry outside fold"
        if atr[idx] is None:
            continue
        entry = closes[idx]
        dist = k * atr[idx]
        if dist <= 0:
            continue
        qty = 500.0 / entry
        if direction == "long":
            stop, tp = entry - dist, entry + 2 * dist
        else:
            stop, tp = entry + dist, entry - 2 * dist
        exit_px = closes[-1]
        exit_ts = last_ts
        for j in range(idx + 1, len(bars)):
            if direction == "long":
                hit_sl = lows[j] <= stop
                hit_tp = highs[j] >= tp
            else:
                hit_sl = highs[j] >= stop
                hit_tp = lows[j] <= tp
            if hit_sl:
                exit_px, exit_ts = stop, int(bars[j]["time"])
                break
            if hit_tp:
                exit_px, exit_ts = tp, int(bars[j]["time"])
                break
        assert exit_ts <= last_ts, "exit crossed fold boundary"
        gross = ((exit_px - entry) * qty if direction == "long"
                 else (entry - exit_px) * qty)
        out.append({"net": gross - TRADE_COST, "exit_ts": exit_ts})
    return out


def run_fold(bars, n, seed_base, k, n_draws=N_DRAWS):
    """500 fixed draws for one fold. Returns distribution + strategy rank."""
    results = []
    for d in range(n_draws):
        rng = random.Random(seed_base + d)
        idxs = rng.sample(range(len(bars) - 1), n)
        entries = [(i, "long" if rng.random() < 0.5 else "short") for i in idxs]
        trades = simulate_fold(bars, entries, k)
        results.append(round(sum(t["net"] for t in trades), 4))
    results.sort()
    return results


def percentiles(results):
    n = len(results)
    return {
        "draws": n,
        "mean": sum(results) / n,
        "p5": results[int(0.05 * n)],
        "p25": results[int(0.25 * n)],
        "p50": results[int(0.50 * n)],
        "p75": results[int(0.75 * n)],
        "p95": results[int(0.95 * n)],
    }


def run_all_folds(folds, fills_by_fold, k, n_draws=N_DRAWS, strat_nets=None):
    """Pure fold isolation core: each fold's control uses only
    that fold's bars. seed bases are fixed per fold name.
    strat_nets overrides file reads (tests); default reads the
    recorded fold strategy nets."""
    seed_bases = {"F1": 1108000, "F2": 1108100, "F3": 1108200, "F4": 1108300}
    if strat_nets is None:
        strat_nets = {f: [t["net"] for t in
                           json.loads((OUT / ("fold_%s_C_moderate.json" % f)).read_text())]
                      for f in folds if fills_by_fold.get(f)}
    report = {}
    for fold, bars in folds.items():
        n = fills_by_fold[fold]
        if n == 0:
            report[fold] = {
                "strategy_n": 0, "strategy_net": 0.0,
                "status": "INSUFFICIENT (no strategy fills; control undefined)",
            }
            continue
        results = run_fold(bars, n, seed_bases[fold], k, n_draws)
        stats = percentiles(results)
        strat_net = round(sum(strat_nets[fold]), 4)
        stats["strategy_net"] = strat_net
        stats["strategy_percentile"] = sum(1 for x in results if x < strat_net) / len(results)
        stats["p_positive"] = sum(1 for x in results if x > 0) / len(results)
        report[fold] = stats
    return report


def main():
    k = load_k()
    folds = fold_bars()
    fills = {f: len(fold_strategy_nets(f)) for f in folds}
    report = {"k_median": k, "draws_per_fold": N_DRAWS,
              "trade_cost": TRADE_COST,
              "folds": run_all_folds(folds, fills, k)}
    for fold, stats in report["folds"].items():
        if "status" in stats:
            print(fold, "no fills -> INSUFFICIENT", flush=True)
        else:
            print("%s n=%d strat=%.4f median=%.4f pct=%.3f" % (
                fold, stats.get("strategy_n", len(fold_strategy_nets(fold))),
                stats["strategy_net"], stats["p50"],
                stats["strategy_percentile"]), flush=True)
    (OUT / "step7_random.json").write_text(json.dumps(report, indent=1))
    print("STEP7-DONE", flush=True)


if __name__ == "__main__":
    main()
