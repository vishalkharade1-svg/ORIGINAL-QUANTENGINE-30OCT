"""11E step 4: pooled OOS economics, break-even, adequacy, MC, regimes,
execution overlays, decomposition, buy-and-hold. All inputs are frozen
artifacts from steps 1-3 (fold trades + IS stats). Seeded randomness only.
"""
import json
import random
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11e.common import trade_metrics

OUT = Path(__file__).resolve().parent / "data"
FOLDS = ["F1", "F2", "F3", "F4"]
SCEN = ["A_zero", "B_small", "C_moderate", "D_adverse"]


def load_trades(fold, scenario=None):
    if scenario in (None, "A_zero"):
        name = "fold_%s_trades.json" % fold
    else:
        name = "fold_%s_%s.json" % (fold, scenario)
    return json.loads((OUT / name).read_text())


def pooled(scenario):
    all_t = []
    for f in FOLDS:
        all_t.extend(load_trades(f, scenario))
    all_t.sort(key=lambda t: (t["exit_time"], t["entry_time"]))
    return all_t


def mc_shuffle(nets, sims, seed):
    rng = random.Random(seed)
    finals, dds, streaks, neg, dd_gt = [], [], [], 0, 0
    for _ in range(sims):
        order = nets[:]
        rng.shuffle(order)
        run, peak, dd, streak, worst = 0.0, 0.0, 0.0, 0, 0
        for x in order:
            run += x
            peak = max(peak, run)
            dd = max(dd, peak - run)
            streak = streak + 1 if x < 0 else 0
            worst = max(worst, streak)
        finals.append(run)
        dds.append(dd)
        streaks.append(worst)
        if run < 0:
            neg += 1
    finals.sort()
    dds.sort()
    # Observed chronological drawdown for the P(DD>observed) comparison.
    run, peak, obs_dd = 0.0, 0.0, 0.0
    for x in nets:
        run += x
        peak = max(peak, run)
        obs_dd = max(obs_dd, peak - run)
    dd_gt = sum(1 for d in dds if d > obs_dd + 1e-9)
    return {
        "sims": sims, "seed": seed,
        "p_loss": neg / sims,
        "final_p5": finals[int(0.05 * sims)],
        "final_p50": finals[int(0.50 * sims)],
        "final_p95": finals[int(0.95 * sims)],
        "dd_p50": dds[int(0.50 * sims)],
        "dd_p95": dds[int(0.95 * sims)],
        "observed_dd": obs_dd,
        "p_dd_gt_observed": dd_gt / sims,
        "max_streak_p95": sorted(streaks)[int(0.95 * sims)],
    }


def bootstrap_mean(nets, sims, seed):
    rng = random.Random(seed)
    means = []
    n = len(nets)
    for _ in range(sims):
        sample = [nets[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    return {
        "sims": sims, "seed": seed,
        "mean_p5": means[int(0.05 * sims)],
        "mean_p50": means[int(0.50 * sims)],
        "mean_p95": means[int(0.95 * sims)],
    }


def main():
    ev = {}
    # Pooled economics per scenario (production-booked reruns).
    ev["pooled"] = {s: trade_metrics(pooled(s)) for s in SCEN}
    for s in SCEN:
        m = ev["pooled"][s]
        print("pooled %s: n=%d W/L=%d/%d net=%.4f exp=%.4f pf=%s dd=%.4f" % (
            s, m["trades"], m["wins"], m["losses"], m["net_pnl"],
            m["expectancy"], m["profit_factor"], m["max_drawdown"]), flush=True)

    # Break-even (§8): pooled gross edge vs modeled cost per trade.
    a = ev["pooled"]["A_zero"]
    c = ev["pooled"]["C_moderate"]
    n = a["trades"]
    gross_edge = a["net_pnl"] / n if n else 0.0
    modeled_cost = (a["net_pnl"] - c["net_pnl"]) / n if n else 0.0
    ev["breakeven"] = {
        "gross_edge_per_trade": gross_edge,
        "modeled_cost_per_trade_C": modeled_cost,
        "breakeven_cost_per_trade": gross_edge,
        "safety_margin": gross_edge - modeled_cost,
        "interpretation": ("NEGATIVE break-even: strategy needs a per-trade "
                           "subsidy; no non-negative cost clears zero."
                           if gross_edge <= 0 else
                           "positive break-even cost (see margin)"),
    }
    print("breakeven:", ev["breakeven"], flush=True)

    # Sample adequacy (§9).
    nets_c = [t["net"] for t in pooled("C_moderate")]
    import statistics
    ev["adequacy"] = {
        "n": n,
        "per_fold": {f: len(load_trades(f)) for f in FOLDS},
        "wins": a["wins"], "losses": a["losses"],
        "win_rate": a["win_rate"],
        "mean": (sum(nets_c) / len(nets_c)) if nets_c else 0.0,
        "median": sorted(nets_c)[len(nets_c) // 2] if nets_c else 0.0,
        "stdev": (statistics.pstdev(nets_c)) if len(nets_c) > 1 else 0.0,
        "bootstrap_expectancy_ci": bootstrap_mean(nets_c, 5000, 1107002),
        "n_ge_30": n >= 30,
    }
    print("adequacy n=%d ci=%s" % (n, ev["adequacy"]["bootstrap_expectancy_ci"]), flush=True)

    # Monte Carlo on pooled scenario-C nets (§10).
    ev["monte_carlo"] = mc_shuffle(nets_c, 5000, 1107001)
    print("MC:", {k: v for k, v in ev["monte_carlo"].items() if k != "seed"}, flush=True)

    # Buy-and-hold baselines (§14): per contiguous dataset window.
    bh = {}
    for name, rel in (("D2", "data/history/BTCUSDT_1m_oos.json"),
                      ("D3", "research/phase11e/data/oos_fresh.json")):
        doc = json.loads((BASE_DIR / rel).read_text())
        bars = sorted(doc.get("candles", doc.get("raw", [])),
                      key=lambda b: int(b["time"]))
        if "raw" in doc:
            bars = list(reversed(bars))
            bars = sorted(bars, key=lambda b: int(b["time"]))
        start, end = float(bars[0]["close"]), float(bars[-1]["close"])
        qty = 2000.0 / start
        gross = qty * (end - start)
        fee = 2000.0 * 0.0005
        bh[name] = {"start": start, "end": end, "gross": gross,
                    "net_one_round_trip": gross - 2 * fee,
                    "return_pct": 100.0 * (end - start) / start}
    ev["buy_hold"] = bh
    print("B&H:", bh, flush=True)

    # Execution overlays V1/V3 (final-PV basis, documented) + V2 drop.
    # Overlays adjust the slippage COMPONENT (metrics recompute
    # net = gross - fees - slippage), so the economics stay exact.
    def _extra(trades, bps):
        return [dict(t, slippage=t.get("slippage", 0.0)
                     + abs(t["quantity"]) * abs(t["entry"]) * bps)
                for t in trades]
    base = pooled("C_moderate")
    v1 = _extra(base, 0.00005)
    v3 = _extra(base, 0.0001)
    drop = set(random.Random(1107).sample(range(len(base)), max(0, int(0.1 * len(base)))))
    v2 = [t for i, t in enumerate(base) if i not in drop]
    ev["execution"] = {
        "V1_entry_adverse_0p5bp": trade_metrics(v1)["net_pnl"],
        "V2_missed_10pct_dropped": sorted(drop),
        "V2_net": trade_metrics(v2)["net_pnl"],
        "V3_exits_adverse_1bp": trade_metrics(v3)["net_pnl"],
        "baseline_C_net": trade_metrics(base)["net_pnl"],
    }
    print("execution:", ev["execution"], flush=True)

    # Decomposition + leave-one-out (§15) on zero-cost pooled (gross shape).
    pa = pooled("A_zero")
    nets_a = sorted([t["net"] for t in pa])
    gross_pos = sum(x for x in nets_a if x > 0)
    loo = []
    for i in range(len(pa)):
        rest = [t["net"] for j, t in enumerate(pa) if j != i]
        loo.append(round(sum(rest), 6))
    ev["decomposition"] = {
        "n": len(pa),
        "top1_share_of_gross_profit": (max(nets_a) / gross_pos) if gross_pos > 0 else 0.0,
        "top2_share_of_gross_profit": (sum(nets_a[-2:]) / gross_pos) if gross_pos > 0 else 0.0,
        "largest_win": max(nets_a) if nets_a else 0.0,
        "largest_loss": min(nets_a) if nets_a else 0.0,
        "leave_one_out_nets": loo,
        "loo_min": min(loo) if loo else 0.0,
        "loo_max": max(loo) if loo else 0.0,
        "payoff_ratio": (sum(x for x in nets_a if x > 0) / max(1, sum(1 for x in nets_a if x > 0))) / (
            -sum(x for x in nets_a if x < 0) / max(1, sum(1 for x in nets_a if x < 0))),
    }
    print("decomp top1 share:", ev["decomposition"]["top1_share_of_gross_profit"], flush=True)

    (OUT / "step4_analysis.json").write_text(json.dumps(ev, indent=1, default=str))
    print("STEP4-DONE", flush=True)


if __name__ == "__main__":
    main()
