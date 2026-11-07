"""Phase 11G-G Tier-1 gap execution driver (evidence only).

Runs the FROZEN 11G-F family (imported, never copied) over the Tier-1
gap datasets (BTC/ETH ~2099 bars, zero overlap vs all in-repo data).
2099 bars cannot host the frozen 4-fold WF (needs 6175): each
hypothesis gets ONE cold-start diagnostic run per symbol per cost
(WF_INFEASIBLE recorded, no folds fabricated). Setup-rate diagnostic
is the evidence core; economics/MC/RB/regimes apply frozen minimums
(INSUFFICIENT below them). No tuning, no selection, no D3.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f import metrics as M
from research.phase11f import validation as V
from research.phase11f.contracts import sha256_canonical
from research.phase11g import datasets as DG
from research.phase11g import execution as EX
from research.phase11g.run_11g import exec_overlays, run_monte_carlo
from research.phase11g_f import candidates as F

RESEARCH_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = RESEARCH_DIR / "results"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
COSTS = ["A", "B", "C", "D"]
BY_ID = {cls.id.replace("H11GF-", "H11GF-"): cls for cls in F.ALL}

SPARSE_BANDS = [(1.0, "VERY_SPARSE"), (5.0, "SPARSE"),
                (20.0, "MODERATE"), (float("inf"), "FREQUENT")]


def sparsity_label(rate_per_1k):
    for bound, label in SPARSE_BANDS:
        if rate_per_1k < bound:
            return label
    return "FREQUENT"


def verify_d3_sealed():
    try:
        DG.load_holdout("seal-check")
    except DG.SealedHoldoutError:
        pass
    else:  # pragma: no cover
        raise AssertionError("D3 seal broken")


def load_gap(symbol):
    code = symbol[0:3].lower()
    doc = json.loads((RESEARCH_DIR / "data" / ("fresh_11gg_gap_%susdt.json" % code)).read_text())
    bars = sorted(doc["candles"], key=lambda r: int(r["time"]))
    assert len(bars) == doc["fetched_count"] == 2099
    assert all(b > 1788175440 and b < 1788301500
               for b in (int(x["time"]) for x in bars)), "gap window violated"
    return bars


def run_all(costs=COSTS):
    fold_results, setup = {}, {}
    for symbol in SYMBOLS:
        bars = load_gap(symbol)
        for hid in sorted(BY_ID):
            per_cost = {}
            for cost in costs:
                out = EX.run_candidate(bars, BY_ID[hid](), symbol, cost_key=cost)
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
            n_fills = len(per_cost["C"]["trades"])
            rate = n_fills / len(bars) * 1000.0
            c0 = per_cost["C"]
            fold_results["%s|%s" % (hid, symbol)] = {
                "hypothesis_id": hid, "symbol": symbol, "bars": len(bars),
                "wf": "WF_INFEASIBLE_2099_lt_6175", "costs": per_cost}
            setup["%s|%s" % (hid, symbol)] = {
                "events": c0["n_signals"], "signals": c0["n_signals"],
                "orders": c0["n_orders"], "expired": c0["n_expired"],
                "invalidated": c0["n_invalidated"], "fills": n_fills,
                "trades": n_fills, "rate_per_1k": rate,
                "sparsity": sparsity_label(rate)}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "gap_fold_results.json").write_text(json.dumps(fold_results, indent=1))
    (RESULTS_DIR / "gap_setup_rates.json").write_text(json.dumps(setup, indent=1))
    return fold_results, setup


def stage_analysis():
    fold_results = json.loads((RESULTS_DIR / "gap_fold_results.json").read_text())
    hypo, costs, mcs, execs = {}, {}, {}, {}
    for hid in sorted(BY_ID):
        pooled_c = [t for k, fr in fold_results.items()
                    if fr["hypothesis_id"] == hid for t in fr["costs"]["C"]["trades"]]
        m_all = {}
        for c in COSTS:
            pooled = [t for k, fr in fold_results.items()
                      if fr["hypothesis_id"] == hid for t in fr["costs"][c]["trades"]]
            m_all[c] = M.research_trade_metrics(pooled)
        costs[hid] = {c: {"gross": m["gross_pnl"], "fees": m["fees"],
                          "slippage": m["slippage"], "net": m["net_pnl"],
                          "expectancy": m["expectancy"], "pf": m["profit_factor"],
                          "wins": m["wins"], "losses": m["losses"],
                          "trades": m["trades"]} for c, m in m_all.items()}
        n = len(pooled_c)
        verdict = "INSUFFICIENT_EVIDENCE" if n < 30 else (
            "PASS" if m_all["C"]["net_pnl"] > 0 else "FAIL")
        hypo[hid] = {"verdict": verdict, "n_pooled": n,
                     "wf": "WF_INFEASIBLE",
                     "metrics_C": {"net": m_all["C"]["net_pnl"],
                                   "expectancy": m_all["C"]["expectancy"],
                                   "pf": m_all["C"]["profit_factor"]}}
        mcs[hid] = {"status": "VACUOUS_INSUFFICIENT"} if n < 30 else None
        if mcs[hid] is None:
            mcs[hid] = run_monte_carlo([t["net"] for t in pooled_c])
        execs[hid] = exec_overlays(pooled_c)
    rbs = {hid: {"status": "INSUFFICIENT"} for hid in sorted(BY_ID)}
    mt = {"bonferroni_reference": 0.00625, "q": 0.10,
          "verdicts": {hid: hypo[hid]["verdict"] for hid in hypo},
          "passes": sum(1 for h in hypo.values() if h["verdict"] == "PASS"),
          "note": "no ranking selection"}
    for name, obj in (("gap_primary_results.json", hypo),
                      ("gap_cost_results.json", costs),
                      ("gap_random_baseline.json", rbs),
                      ("gap_monte_carlo.json", mcs),
                      ("gap_execution_robustness.json", execs),
                      ("gap_multiple_testing.json", mt)):
        (RESULTS_DIR / name).write_text(json.dumps(obj, indent=1, sort_keys=True))
    # Ablations (frozen variants, A+C) — diagnostic setup-rate context.
    abls = {}
    for hid in sorted(BY_ID):
        for name, overrides in BY_ID[hid]().ablations():
            if name == "full":
                continue
            for symbol in SYMBOLS:
                bars = load_gap(symbol)
                for cost in ("A", "C"):
                    out = EX.run_candidate(bars, BY_ID[hid](**overrides),
                                           symbol, cost_key=cost)
                    m = M.research_trade_metrics(out["trades"])
                    abls["%s|%s|%s|%s" % (hid, name, symbol, cost)] = {
                        "removed": name, "trades": m["trades"],
                        "net": m["net_pnl"]}
    (RESULTS_DIR / "gap_ablation_results.json").write_text(
        json.dumps(abls, indent=1, sort_keys=True))
    return hypo


def stage_repro():
    ref = json.loads((RESULTS_DIR / "gap_fold_results.json").read_text())
    rep = {"runs": {}, "identical": True}
    for key, fr in sorted(ref.items()):
        hid, symbol = fr["hypothesis_id"], fr["symbol"]
        bars = load_gap(symbol)
        for cost in COSTS:
            out = EX.run_candidate(bars, BY_ID[hid](), symbol, cost_key=cost)
            same = (sha256_canonical(out["trades"]) ==
                    sha256_canonical(fr["costs"][cost]["trades"]))
            rep["runs"]["%s|%s" % (key, cost)] = same
    # Truncation causality spot-check on gap prefixes.
    trunc = {}
    for hid in sorted(BY_ID):
        bars = load_gap("BTCUSDT")
        a, b = BY_ID[hid](), BY_ID[hid]()
        ok = True
        for idx in (500, 1200, 2000):
            if (a.signals(idx, bars, None) or []) != \
               (b.signals(idx, bars[:idx + 1], None) or []):
                ok = False
        trunc[hid] = ok
    rep["truncation_causality"] = trunc
    rep["truncation_all_pass"] = all(trunc.values())
    rep["identical"] = all(rep["runs"].values()) and rep["truncation_all_pass"]
    (RESULTS_DIR / "gap_reproducibility.json").write_text(
        json.dumps(rep, indent=1, sort_keys=True))
    print("REPRO identical =", rep["identical"])
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["primary", "analysis", "repro", "all"])
    ap.add_argument("--hyp", default=None)
    args = ap.parse_args()
    verify_d3_sealed()
    if args.hyp:
        global BY_ID
        BY_ID = {args.hyp: BY_ID[args.hyp]}
    if args.stage in ("primary", "all"):
        _, setup = run_all()
        print("PRIMARY done")
        print(json.dumps({h: (s["fills"], s["sparsity"]) for h, s in setup.items()}))
    if args.stage in ("analysis", "all"):
        hypo = stage_analysis()
        print(json.dumps({h: hypo[h]["verdict"] for h in hypo}, indent=1))
    if args.stage in ("repro", "all"):
        stage_repro()


if __name__ == "__main__":
    main()
