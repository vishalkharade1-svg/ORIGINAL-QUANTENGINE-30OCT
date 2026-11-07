"""Phase 11G-D fresh-data runner (evidence only, no tuning, no D3).

Executes the 8 frozen H11G hypotheses over the authorized fresh BTC
oos_fresh series (2499 bars, chronological) with the frozen NBO
execution, risk, and costs. 2499 bars cannot host the frozen 4-fold
WF (needs 6175) — recorded as INSUFFICIENT_FRESH_SAMPLE; the valid
evidence core is the setup-rate diagnostic plus economics where the
frozen minimums are met. No thresholds move. No winner selected.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f import metrics as M
from research.phase11f import validation as V
from research.phase11f.contracts import sha256_canonical
from research.phase11g import candidates as G
from research.phase11g import execution as EX
from research.phase11g import fresh as FR

RESEARCH_DIR = Path(__file__).resolve().parent
OUT_DIR = RESEARCH_DIR / "results" / "11gd"
COSTS = ["A", "B", "C", "D"]
BY_ID = {cls.id: cls for cls in G.ALL}

SPARSE_BANDS = [(1.0, "VERY SPARSE"), (5.0, "SPARSE"),
                (20.0, "MODERATE"), (float("inf"), "FREQUENT")]


def sparsity_label(rate_per_1k):
    for bound, label in SPARSE_BANDS:
        if rate_per_1k < bound:
            return label
    return "FREQUENT"


def run_all(costs=COSTS):
    assert FR.freshness("oos_fresh") == "FRESH"
    bars = FR.load_fresh_btc()
    feasible, need = FR.wf_feasible(len(bars))
    wf = {"feasible_4fold": feasible, "bars": len(bars), "need": need,
          "verdict": "INSUFFICIENT_FRESH_SAMPLE" if not feasible else "FEASIBLE"}
    fold_results, setup = {}, {}
    for hid in sorted(BY_ID):
        per_cost, n_sig = {}, None
        for cost in costs:
            out = EX.run_candidate(bars, BY_ID[hid](), "BTCUSDT", cost_key=cost)
            for t in out["trades"]:
                assert abs((t["gross"] - t["commission"] - t["slippage"]) - t["net"]) < 1e-9
                trig = int(str(t.get("setup_id", "0")).rsplit("-", 1)[-1])
                t["decision_time"] = int(bars[trig]["time"])
                assert t["decision_time"] <= t["entry_time"] <= t["exit_time"]
            per_cost[cost] = {"trades": out["trades"],
                              "n_signals": out["n_signals"],
                              "n_orders": len(out["orders"]),
                              "n_expired": out["n_expired"],
                              "n_invalidated": out["n_invalidated"]}
            n_sig = out["n_signals"]
        n_fills = len(per_cost["C"]["trades"])
        rate = n_fills / len(bars) * 1000.0
        fold_results[hid] = {"hypothesis_id": hid, "symbol": "BTCUSDT",
                             "bars": len(bars), "costs": per_cost}
        c0 = per_cost["C"]
        setup[hid] = {"events": c0["n_signals"], "signals": c0["n_signals"],
                      "orders": c0["n_orders"], "expired": c0["n_expired"],
                      "invalidated": c0["n_invalidated"],
                      "fills": n_fills, "trades": n_fills,
                      "rate_per_1k": rate, "sparsity": sparsity_label(rate)}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fresh_fold_results.json").write_text(json.dumps(fold_results, indent=1))
    (OUT_DIR / "fresh_setup_rates.json").write_text(json.dumps(setup, indent=1))
    return fold_results, setup, wf


def stage_analysis():
    fold_results = json.loads((OUT_DIR / "fresh_fold_results.json").read_text())
    hypo, costs, regimes, rbs, mcs, execs = {}, {}, {}, {}, {}, {}
    for hid in sorted(BY_ID):
        fr = fold_results[hid]
        pooled_c = fr["costs"]["C"]["trades"]
        m_all = {c: M.research_trade_metrics(fr["costs"][c]["trades"]) for c in COSTS}
        costs[hid] = {c: {"gross": m["gross_pnl"], "fees": m["fees"],
                          "slippage": m["slippage"], "net": m["net_pnl"],
                          "expectancy": m["expectancy"], "pf": m["profit_factor"],
                          "wins": m["wins"], "losses": m["losses"],
                          "trades": m["trades"]} for c, m in m_all.items()}
        n = len(pooled_c)
        verdict = "INSUFFICIENT_EVIDENCE" if n < 30 else (
            "PASS" if m_all["C"]["net_pnl"] > 0 else "FAIL")
        hypo[hid] = {"verdict": verdict, "n": n,
                     "metrics_C": {"net": m_all["C"]["net_pnl"],
                                   "expectancy": m_all["C"]["expectancy"],
                                   "pf": m_all["C"]["profit_factor"],
                                   "sharpe": m_all["C"]["sharpe"],
                                   "sortino": m_all["C"]["sortino"],
                                   "maxdd": m_all["C"]["max_drawdown"]}}
        regimes[hid] = {"status": "INSUFFICIENT_REGIME_EVIDENCE"}
        rbs[hid] = {"status": "INSUFFICIENT"}
        mcs[hid] = {"status": "VACUOUS_INSUFFICIENT"} if n < 30 else None
        if mcs[hid] is None:
            from research.phase11g.run_11g import run_monte_carlo
            mcs[hid] = run_monte_carlo([t["net"] for t in pooled_c])
        from research.phase11g.run_11g import exec_overlays
        execs[hid] = exec_overlays(pooled_c)
    mt = {"bonferroni_reference": 0.00625, "q": 0.10,
          "verdicts": {hid: hypo[hid]["verdict"] for hid in hypo},
          "passes": sum(1 for h in hypo.values() if h["verdict"] == "PASS"),
          "note": "no ranking selection"}
    for name, obj in (("fresh_primary_results.json", hypo),
                      ("fresh_cost_results.json", costs),
                      ("fresh_regime_results.json", regimes),
                      ("fresh_random_baseline_results.json", rbs),
                      ("fresh_monte_carlo_results.json", mcs),
                      ("fresh_execution_robustness.json", execs),
                      ("fresh_multiple_testing.json", mt)):
        (OUT_DIR / name).write_text(json.dumps(obj, indent=1, sort_keys=True))
    return hypo


def stage_ablations():
    from research.phase11f import metrics as M
    bars = FR.load_fresh_btc()
    abls = {}
    for hid in sorted(BY_ID):
        for name, overrides in BY_ID[hid]().ablations():
            if name == "full":
                continue
            for cost in ("A", "C"):
                out = EX.run_candidate(bars, BY_ID[hid](**overrides),
                                       "BTCUSDT", cost_key=cost)
                m = M.research_trade_metrics(out["trades"])
                abls["%s|%s|%s" % (hid, name, cost)] = {
                    "removed": name, "trades": m["trades"],
                    "net": m["net_pnl"], "expectancy": m["expectancy"]}
    (OUT_DIR / "fresh_ablation_results.json").write_text(
        json.dumps(abls, indent=1, sort_keys=True))
    return abls


def stage_repro():
    ref = json.loads((OUT_DIR / "fresh_fold_results.json").read_text())
    rep = {"folds": {}, "identical": True}
    bars = FR.load_fresh_btc()
    for hid in sorted(BY_ID):
        for cost in COSTS:
            out = EX.run_candidate(bars, BY_ID[hid](), "BTCUSDT", cost_key=cost)
            same = (sha256_canonical(out["trades"]) ==
                    sha256_canonical(ref[hid]["costs"][cost]["trades"]))
            rep["folds"]["%s|%s" % (hid, cost)] = same
    rep["identical"] = all(rep["folds"].values())
    (OUT_DIR / "fresh_reproducibility.json").write_text(
        json.dumps(rep, indent=1, sort_keys=True))
    # Truncation causality spot-check on the fresh prefix (no fitting).
    trunc = {}
    for hid in sorted(BY_ID):
        inst_a, inst_b = BY_ID[hid](), BY_ID[hid]()
        ok = True
        for idx in (500, 1200, 2000, 2498):
            if (inst_a.signals(idx, bars, None) or []) != \
               (inst_b.signals(idx, bars[:idx + 1], None) or []):
                ok = False
        trunc[hid] = ok
    rep["truncation_causality"] = trunc
    rep["truncation_all_pass"] = all(trunc.values())
    (OUT_DIR / "fresh_reproducibility.json").write_text(
        json.dumps(rep, indent=1, sort_keys=True))
    print("REPRO identical =", rep["identical"],
          "| truncation =", rep["truncation_all_pass"])
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["primary", "analysis", "ablations", "repro", "all"])
    args = ap.parse_args()
    if args.stage in ("primary", "all"):
        _, setup, wf = run_all()
        print("PRIMARY done; WF:", wf["verdict"])
        print(json.dumps({h: (s["fills"], s["sparsity"]) for h, s in setup.items()}))
    if args.stage in ("analysis", "all"):
        hypo = stage_analysis()
        print(json.dumps(hypo, indent=1))
    if args.stage in ("ablations", "all"):
        abls = stage_ablations()
        print("ABLATIONS done:", len(abls))
    if args.stage in ("repro", "all"):
        stage_repro()


if __name__ == "__main__":
    main()
