"""Phase 11G-F execution driver (evidence only, frozen family).

Reuses certified machinery by import (never modified, never forked):
- folds/geometry/validators: research.phase11f.validation
- NBO pipeline/intent/costs: research.phase11g.execution
- metrics adapter: research.phase11f.metrics
- RB/MC/regime/exec-overlay patterns: research.phase11g.run_11g
  (hypothesis-agnostic pure functions)
- datasets/D3 seal: research.phase11g.datasets + fresh registry

New in 11G-F: candidate signal classes (candidates.py), frozen
registry (hypotheses/), artifact paths (results/), run/results
manifests, research-log entry.

Classification (preregistered): SUFFICIENT (>=30 pooled, >=3 folds,
>=2 active) + pooled net(C) > 0 -> PASS; SUFFICIENT + net(C) <= 0 ->
FAIL; else INSUFFICIENT_EVIDENCE. No ranking. No winner.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f import validation as V
from research.phase11f import metrics as M
from research.phase11f.contracts import sha256_canonical
from research.phase11g import datasets as DG
from research.phase11g import execution as EX
from research.phase11g.run_11g import (
    classify_trade,
    dataset_hash,
    exec_overlays,
    load_series,
    run_monte_carlo,
    run_random_baseline,
    train_regime_context,
    train_signal_stats,
)
from research.phase11g_f import candidates as F

RESEARCH_DIR = Path(__file__).resolve().parent
RESULTS_DIR = RESEARCH_DIR / "results"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
COSTS = ["A", "B", "C", "D"]
BY_ID = {cls.id: cls for cls in F.ALL}


def verify_d3_sealed():
    for p in DG.DATASETS.values():
        DG.assert_not_holdout(p["source"])
    try:
        DG.load_holdout("seal-check")
    except DG.SealedHoldoutError:
        pass
    else:  # pragma: no cover
        raise AssertionError("D3 seal broken")


def run_fold(cls, series, fold, symbol, cost_key, **overrides):
    s0, s1 = fold["test_start"], fold["test_end"]
    inst = cls(**overrides) if overrides else cls()
    out = EX.run_candidate(series[s0:s1], inst, symbol, cost_key=cost_key)
    sl = series[s0:s1]
    for t in out["trades"]:
        try:
            trig = int(str(t.get("setup_id", "0")).rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            trig = None
        t["decision_time"] = int(sl[trig]["time"]) if trig is not None and 0 <= trig < len(sl) else None
    det = {"orders": out["orders"], "n_signals": out["n_signals"],
           "n_expired": out["n_expired"], "n_invalidated": out["n_invalidated"]}
    return out["trades"], det


def _pooled(fold_results, hid, cost):
    out = []
    for key, fr in fold_results.items():
        if fr["hypothesis_id"] == hid:
            out.extend(fr["costs"][cost]["trades"])
    return out


def stage_primary(hyps, symbols):
    hyps_doc = json.loads((RESEARCH_DIR / "hypotheses" / "hypotheses.json").read_text())
    frozen = {h["id"]: h for h in hyps_doc["hypotheses"]}
    fold_results = {}
    for symbol in symbols:
        series, lineage = load_series(symbol)
        assert "D3" not in "".join(lineage)
        folds = V.build_folds(len(series))
        assert V.validate_folds(folds) == []
        assert V.validate_expanding(folds) == []
        dhash = dataset_hash(symbol, series)
        for hid in hyps:
            cls = BY_ID[hid]
            for f in folds:
                key = "%s|%s|F%d" % (hid, symbol, f["fold"])
                per_cost = {}
                for cost in COSTS:
                    trades, det = run_fold(cls, series, f, symbol, cost)
                    for t in trades:
                        assert abs((t["gross"] - t["commission"] - t["slippage"]) - t["net"]) < 1e-9
                        assert t["decision_time"] is not None
                        assert t["decision_time"] <= t["entry_time"] <= t["exit_time"]
                    per_cost[cost] = {"trades": trades,
                                      "n_orders": len(det["orders"]),
                                      "n_signals": det["n_signals"],
                                      "n_expired": det["n_expired"],
                                      "n_invalidated": det["n_invalidated"]}
                fold_results[key] = {
                    "hypothesis_id": hid, "symbol": symbol, "fold": f["fold"],
                    "geometry": f, "lineage": sorted(set(
                        lineage[f["test_start"]:f["test_end"]])),
                    "dataset_hash": dhash,
                    "execution_model": frozen[hid]["entry_model"],
                    "costs": per_cost}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    merged_path = RESULTS_DIR / "fold_results.json"
    if merged_path.exists():
        merged = json.loads(merged_path.read_text())
        merged.update(fold_results)
        fold_results = merged
    merged_path.write_text(json.dumps(fold_results, indent=1))
    return fold_results


def stage_analysis(hyps):
    fold_results = json.loads((RESULTS_DIR / "fold_results.json").read_text())
    hypo, costs, regimes, rbs, mcs, abls, execs = {}, {}, {}, {}, {}, {}, {}
    for hid in hyps:
        pooled_c = _pooled(fold_results, hid, "C")
        m_all = {c: M.research_trade_metrics(_pooled(fold_results, hid, c)) for c in COSTS}
        costs[hid] = {c: {"gross": m["gross_pnl"], "fees": m["fees"],
                          "slippage": m["slippage"], "net": m["net_pnl"],
                          "expectancy": m["expectancy"], "pf": m["profit_factor"],
                          "wins": m["wins"], "losses": m["losses"],
                          "breakevens": m["breakevens"], "trades": m["trades"]}
                      for c, m in m_all.items()}
        n = len(pooled_c)
        folds = sorted({fr["fold"] for fr in fold_results.values()
                        if fr["hypothesis_id"] == hid})
        active = sum(1 for fr in fold_results.values()
                     if fr["hypothesis_id"] == hid and fr["costs"]["C"]["trades"])
        verdict = V.assess_evidence(n, len(folds), active)
        verdict = ("PASS" if m_all["C"]["net_pnl"] > 0 else "FAIL") \
            if verdict == "SUFFICIENT" else "INSUFFICIENT_EVIDENCE"
        hypo[hid] = {"verdict": verdict,
                     "evidence": V.assess_evidence(n, len(folds), active),
                     "n_pooled": n, "n_folds": len(folds), "active_folds": active,
                     "metrics_C": {"net": m_all["C"]["net_pnl"],
                                   "expectancy": m_all["C"]["expectancy"],
                                   "pf": m_all["C"]["profit_factor"],
                                   "sharpe": m_all["C"]["sharpe"],
                                   "sortino": m_all["C"]["sortino"],
                                   "maxdd": m_all["C"]["max_drawdown"],
                                   "wins": m_all["C"]["wins"],
                                   "losses": m_all["C"]["losses"]}}
        reg = {}
        for symbol in SYMBOLS:
            series, _ = load_series(symbol)
            folds = V.build_folds(len(series))
            for f in folds:
                vols, _, _ = train_regime_context(series, f)
                if len(vols) < 3:
                    continue
                terc = V.tercile_thresholds(vols)
                key = "%s|F%d" % (symbol, f["fold"])
                cells = {}
                fr = fold_results["%s|%s|F%d" % (hid, symbol, f["fold"])]
                for t in fr["costs"]["C"]["trades"]:
                    cell = classify_trade(t, series, f, terc)
                    cells.setdefault(cell, []).append(t)
                reg[key] = {}
                for cell, v in cells.items():
                    if len(v) >= 3:
                        m = M.research_trade_metrics(v)
                        reg[key][cell] = {"n": len(v), "net": m["net_pnl"],
                                          "expectancy": m["expectancy"],
                                          "pf": m["profit_factor"]}
                    else:
                        reg[key][cell] = {"n": len(v), "status": "INSUFFICIENT"}
        regimes[hid] = reg
        rb = {}
        for symbol in SYMBOLS:
            series, _ = load_series(symbol)
            folds = V.build_folds(len(series))
            for f in folds:
                fr = fold_results["%s|%s|F%d" % (hid, symbol, f["fold"])]
                n_tr = len(fr["costs"]["C"]["trades"])
                dists, holds = [], []
                for s2 in SYMBOLS:
                    s_bars, _ = load_series(s2)
                    d, h = train_signal_stats(BY_ID[hid], s_bars, f)
                    dists.extend(d)
                    holds.extend(h)
                sd = statistics.median(dists) if len(dists) >= 3 else None
                mh = max(1, int(statistics.median(holds))) if len(holds) >= 3 else None
                res = run_random_baseline(series[f["test_start"]:f["test_end"]],
                                          n_tr, sd, mh)
                if res["status"] == "OK":
                    strat = sum(t["net"] for t in fr["costs"]["C"]["trades"])
                    res["strategy_net"] = strat
                    res["strategy_percentile"] = (
                        sum(1 for d in res["draws"] if d <= strat) / len(res["draws"]))
                    res["train_stop_median"] = sd
                    res["train_hold_median"] = mh
                    del res["draws"]
                rb["%s|F%d" % (symbol, f["fold"])] = res
        rbs[hid] = rb
        mcs[hid] = run_monte_carlo([t["net"] for t in pooled_c])
        execs[hid] = exec_overlays(pooled_c)
    hyps_doc = json.loads((RESEARCH_DIR / "hypotheses" / "hypotheses.json").read_text())
    abl_defs = {h["id"]: [a["name"] for a in h["allowed_ablations"]]
                for h in hyps_doc["hypotheses"]}
    for hid in hyps:
        inst0 = BY_ID[hid]()
        code_names = sorted(n for n, _ in inst0.ablations())
        assert sorted(abl_defs[hid]) == sorted(
            n for n in code_names if n != "full"), hid
        for name, overrides in inst0.ablations():
            if name == "full":
                continue
            for symbol in SYMBOLS:
                series, _ = load_series(symbol)
                for f in V.build_folds(len(series)):
                    for cost in ("A", "C"):
                        out = EX.run_candidate(series[f["test_start"]:f["test_end"]],
                                               BY_ID[hid](**overrides), symbol,
                                               cost_key=cost)
                        m = M.research_trade_metrics(out["trades"])
                        abls["%s|%s|%s|F%d|%s" % (hid, name, symbol, f["fold"], cost)] = {
                            "removed": name, "trades": m["trades"],
                            "net": m["net_pnl"], "expectancy": m["expectancy"],
                            "pf": m["profit_factor"]}
    mt = {"bonferroni_reference": 0.00625, "q": 0.10,
          "verdicts": {hid: hypo[hid]["verdict"] for hid in hyps},
          "note": "no ranking selection; single passes are hypothesis-generating"}
    mt_path = RESULTS_DIR / "multiple_testing_results.json"
    if mt_path.exists():
        prior = json.loads(mt_path.read_text())
        prior.get("verdicts", {}).update(mt["verdicts"])
        mt["verdicts"] = prior["verdicts"]
    mt["passes"] = sum(1 for v in mt["verdicts"].values() if v == "PASS")
    for name, obj in (("primary_results.json", hypo), ("cost_results.json", costs),
                      ("regime_results.json", regimes), ("random_baseline_results.json", rbs),
                      ("monte_carlo_results.json", mcs), ("ablation_results.json", abls),
                      ("execution_robustness_results.json", execs),
                      ("multiple_testing_results.json", mt)):
        path = RESULTS_DIR / name
        if path.exists() and name != "multiple_testing_results.json":
            merged = json.loads(path.read_text())
            merged.update(obj)
            obj = merged
        path.write_text(json.dumps(obj, indent=1, sort_keys=True))
    return hypo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="primary",
                    choices=["primary", "analysis", "all", "repro"])
    ap.add_argument("--hyp", default=None)
    ap.add_argument("--symbol", default=None)
    args = ap.parse_args()
    verify_d3_sealed()
    hyps = [args.hyp] if args.hyp else sorted(BY_ID)
    symbols = [args.symbol] if args.symbol else SYMBOLS
    if args.stage in ("primary", "all"):
        stage_primary(hyps, symbols)
        print("PRIMARY done")
    if args.stage in ("analysis", "all"):
        hypo = stage_analysis(hyps)
        print(json.dumps({h: hypo[h]["verdict"] for h in hypo}, indent=1))
    if args.stage == "repro":
        rep = {"folds": {}, "metrics": {}}
        fold_results = json.loads((RESULTS_DIR / "fold_results.json").read_text())
        for symbol in symbols:
            series, _ = load_series(symbol)
            for hid in hyps:
                for f in V.build_folds(len(series)):
                    key = "%s|%s|F%d" % (hid, symbol, f["fold"])
                    for cost in COSTS:
                        ckey = "%s|%s" % (key, cost)
                        trades, _ = run_fold(BY_ID[hid], series, f, symbol, cost)
                        ref = fold_results[key]["costs"][cost]["trades"]
                        rep["folds"][ckey] = (
                            sha256_canonical(trades) == sha256_canonical(ref))
                        rep["metrics"][ckey] = (
                            M.research_trade_metrics(trades) == M.research_trade_metrics(ref))
        rep_path = RESULTS_DIR / "reproducibility_results.json"
        if rep_path.exists():
            prior = json.loads(rep_path.read_text())
            prior.get("folds", {}).update(rep["folds"])
            prior.get("metrics", {}).update(rep["metrics"])
            rep["folds"], rep["metrics"] = prior["folds"], prior["metrics"]
        rep["identical"] = all(rep["folds"].values()) and all(rep["metrics"].values())
        rep_path.write_text(json.dumps(rep, indent=1, sort_keys=True))
        print("REPRO identical =", rep["identical"])


if __name__ == "__main__":
    main()
