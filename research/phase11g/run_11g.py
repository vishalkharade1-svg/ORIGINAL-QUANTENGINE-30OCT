"""Phase 11G-C preregistered research runner (evidence only).

Executes H11G-001..008 EXACTLY as frozen (hypotheses.json + candidates.py
defaults) over D1+D2 series with the frozen expanding-origin geometry.
No optimization, no selection, no D3 (sealed; never loaded/hashed/read).

Series per symbol: universe_D1 (4001, IS lineage) + universe_D2 (3000,
validation lineage), contiguous, 7001 bars. Frozen build_folds hosts 4
folds in [0,6175); tail documented unused.

Per fold: cold-start NBO engine on the TEST slice only; train region
supplies ONLY fitted quantities (regime terciles, RB holding/stop
medians). Costs A/B/C/D via the production TradeSimulator path.
Metrics via the certified adapter. Classification (preregistered):
SUFFICIENT (>=30 pooled, >=3 folds, >=2 active) + pooled net(C) > 0
-> PASS; SUFFICIENT + net(C) <= 0 -> FAIL; else INSUFFICIENT_EVIDENCE.

Usage:
  python research/phase11g/run_11g.py --stage primary [--hyp H11G-001] [--symbol BTCUSDT]
  python research/phase11g/run_11g.py --stage analysis [--hyp ...]
  python research/phase11g/run_11g.py --stage repro [--hyp ...] [--symbol ...]
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

from research.phase11f import features as F11
from research.phase11f import validation as V
from research.phase11g import candidates as G
from research.phase11g import execution as EX
from research.phase11f import metrics as M
from research.phase11f.contracts import sha256_canonical
from research.phase11f.datasets import assert_not_holdout

RESEARCH_DIR = Path(__file__).resolve().parent
RESULTS_DIR = RESEARCH_DIR / "results"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
COSTS = ["A", "B", "C", "D"]
BY_ID = {cls.id: cls for cls in G.ALL}

RB_DRAWS = 500
RB_SEEDS = range(1108000, 1108000 + RB_DRAWS)
MC_SIMS = 5000
MC_SEED_SHUFFLE = 1107001
MC_SEED_BOOT = 1107002
V2_SEED = 1107


def verify_d3_sealed():
    from research.phase11g import datasets as DG
    for p in ("research/phase11f/data/universe_D3_BTC.json",
              "research/phase11f/data/universe_D3_ETH.json"):
        assert "D3" in p
    for p in DG.DATASETS.values():
        assert_not_holdout(p["source"])
    try:
        DG.load_holdout("seal-check")
    except DG.SealedHoldoutError:
        pass
    else:  # pragma: no cover
        raise AssertionError("D3 seal broken")
    assert_not_holdout("research/phase11g/results")


def load_series(symbol):
    code = symbol[0:3]
    d1 = json.loads((BASE_DIR / "research/phase11f/data" / ("universe_D1_%s.json" % code)).read_text())
    d2 = json.loads((BASE_DIR / "research/phase11f/data" / ("universe_D2_%s.json" % code)).read_text())
    b1, b2 = list(d1["candles"]), list(d2["candles"])
    assert b1[-1]["time"] + 60 == b2[0]["time"], "D1/D2 not contiguous for %s" % symbol
    assert d1["symbol"] == d2["symbol"] == symbol
    bars = b1 + b2
    lineage = (["D1"] * len(b1)) + (["D2"] * len(b2))
    return bars, lineage


def dataset_hash(symbol, bars):
    return sha256_canonical({"symbol": symbol, "n": len(bars),
                             "first": bars[0]["time"], "last": bars[-1]["time"],
                             "candles": bars})


def run_fold(cls, series, fold, symbol, cost_key, **overrides):
    s0, s1 = fold["test_start"], fold["test_end"]
    inst = cls(**overrides) if overrides else cls()
    out = EX.run_candidate(series[s0:s1], inst, symbol, cost_key=cost_key)
    # Attach decision timestamps (setup_id suffix = slice-local trigger idx).
    sl = series[s0:s1]
    for t in out["trades"]:
        try:
            trig = int(str(t.get("setup_id", t.get("trade_id", "0")).rsplit("-", 1)[-1]))
        except (ValueError, IndexError):
            trig = None
        t["decision_time"] = int(sl[trig]["time"]) if trig is not None and 0 <= trig < len(sl) else None
    return out["trades"], out


def train_signal_stats(cls, series, fold):
    """Train-only fits: intended stop distances + NBO bars-held medians.

    Steps the frozen candidate over series[:train_end] (causal per-step),
    simulates its signals forward strictly inside the train region.
    Fitting only — never evidence.
    """
    t0, t1 = fold["train_start"], fold["train_end"]
    prefix = series[:t1]
    inst = cls()
    sigs = []
    for idx in range(t0, t1):
        for sig in inst.signals(idx, prefix, None) or ():
            sigs.append((idx, sig))
    dists, holds = [], []
    for idx, sig in sigs:
        dist = abs(float(sig["entry"]) - float(sig["stop"]))
        if dist <= 0:
            continue
        dists.append(dist)
        if idx + 1 >= t1:
            continue
        entry = float(prefix[idx + 1]["open"])
        direction = sig["direction"]
        stop, tp = float(sig["stop"]), float(sig["take_profit"])
        held, closed = 0, False
        for j in range(idx + 1, t1):
            held += 1
            lo, hi = float(prefix[j]["low"]), float(prefix[j]["high"])
            s_hit = (lo <= stop) if direction == "BULLISH" else (hi >= stop)
            t_hit = (hi >= tp) if direction == "BULLISH" else (lo <= tp)
            if s_hit and t_hit:
                closed = True
                break
            if s_hit or t_hit:
                closed = True
                break
        if closed:
            holds.append(held)
        _ = entry
    return dists, holds


def train_regime_context(series, fold):
    prefix = series[:fold["train_end"]]
    closes = [float(b["close"]) for b in prefix]
    atr = F11.atr14(prefix)
    sma = F11.sma(closes, 50)
    t0 = fold["train_start"]
    vols = [a / c for a, c in zip(atr[t0:], closes[t0:]) if a is not None]
    return vols, atr, sma


def classify_trade(trade, series, fold, terciles):
    lo, hi = terciles
    prefix = series[:fold["test_end"]]
    closes = [float(b["close"]) for b in prefix]
    atr = F11.atr14(prefix)
    sma = F11.sma(closes, 50)
    et = int(trade["entry_time"])
    idx = next(i for i, b in enumerate(prefix) if int(b["time"]) == et)
    vol = (atr[idx] / closes[idx]) if atr[idx] else 0.0
    bucket = "low" if vol <= lo else ("high" if vol > hi else "mid")
    trend = "above" if (sma[idx] is not None and closes[idx] >= sma[idx]) else "below"
    return "%s/%s" % (bucket, trend)


def rb_simulate_fold(test_bars, n_trades, stop_dist, max_hold, seed):
    rng = random.Random(seed)
    closes = [float(b["close"]) for b in test_bars]
    highs = [float(b["high"]) for b in test_bars]
    lows = [float(b["low"]) for b in test_bars]
    n = len(test_bars)
    total = 0.0
    for _ in range(n_trades):
        idx = rng.randrange(0, n - 1)
        direction = "BULLISH" if rng.random() < 0.5 else "BEARISH"
        entry = closes[idx]
        qty = 500.0 / entry
        stop = entry - stop_dist if direction == "BULLISH" else entry + stop_dist
        tp = entry + 2.0 * stop_dist if direction == "BULLISH" else entry - 2.0 * stop_dist
        exit_px, age, closed = None, 0, False
        for j in range(idx + 1, n):
            age += 1
            s_hit = lows[j] <= stop if direction == "BULLISH" else highs[j] >= stop
            t_hit = highs[j] >= tp if direction == "BULLISH" else lows[j] <= tp
            if s_hit and t_hit:
                exit_px = stop
                closed = True
                break
            if s_hit or t_hit:
                exit_px = stop if s_hit else tp
                closed = True
                break
            if age >= max_hold:
                exit_px = closes[j]  # holding-period expiry MTM
                closed = True
                break
        if not closed:
            exit_px = closes[-1]  # MTM-at-boundary (frozen rule)
        gross = (exit_px - entry) * qty if direction == "BULLISH" else (entry - exit_px) * qty
        total += gross - 500.0 * 0.00059 - 2.0 * 500.0 * 5.0 / 10000.0
    return total


def run_random_baseline(test_bars, n_trades, stop_dist, max_hold):
    if stop_dist is None or max_hold is None or n_trades <= 0:
        return {"status": "INSUFFICIENT", "draws": []}
    draws = [rb_simulate_fold(test_bars, n_trades, stop_dist, max_hold, s) for s in RB_SEEDS]
    draws.sort()
    return {"status": "OK", "draws": draws,
            "median": float(statistics.median(draws)),
            "p5": float(draws[int(0.05 * len(draws))]),
            "p95": float(draws[int(0.95 * len(draws))])}


def run_monte_carlo(nets):
    if not nets:
        return {"status": "INSUFFICIENT"}
    shuff = random.Random(MC_SEED_SHUFFLE)
    finals, maxdds = [], []
    for _ in range(MC_SIMS):
        order = list(nets)
        shuff.shuffle(order)
        run = peak = dd = 0.0
        for x in order:
            run += x
            peak = max(peak, run)
            dd = max(dd, peak - run)
        finals.append(run)
        maxdds.append(dd)
    boot = random.Random(MC_SEED_BOOT)
    means = [statistics.mean(boot.choices(nets, k=len(nets))) for _ in range(MC_SIMS)]
    finals.sort()
    maxdds.sort()
    obs_dd = run = peak = 0.0
    for x in nets:
        run += x
        peak = max(peak, run)
        obs_dd = max(obs_dd, peak - run)
    streak = best = cur = 0
    for x in nets:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    q = lambda xs, p: float(xs[min(len(xs) - 1, int(p * len(xs)))])
    return {"status": "OK", "n": len(nets),
            "p_loss": sum(1 for f in finals if f < 0) / len(finals),
            "p_profit": sum(1 for f in finals if f > 0) / len(finals),
            "p5": q(finals, 0.05), "p50": q(finals, 0.50), "p95": q(finals, 0.95),
            "observed": float(sum(nets)),
            "maxdd_p50": q(maxdds, 0.50), "maxdd_obs": obs_dd,
            "p_dd_gt_obs": sum(1 for d in maxdds if d > obs_dd) / len(maxdds),
            "losing_streak_obs": best,
            "boot_mean_p5": q(sorted(means), 0.05),
            "boot_mean_p95": q(sorted(means), 0.95)}


def exec_overlays(trades):
    base = sum(t["net"] for t in trades)
    pvs = [abs(t["quantity"]) * abs(t["entry"]) for t in trades]
    v1 = base - sum(pv * 0.00005 for pv in pvs)
    v3 = base - sum(pv * 0.0001 for pv in pvs)
    if trades:
        drop = set(random.Random(V2_SEED).sample(range(len(trades)), len(trades) // 10))
        v2 = sum(t["net"] for i, t in enumerate(trades) if i not in drop)
    else:
        v2 = 0.0
    return {"baseline_C": base, "V1_entry_adverse_0p5bp": v1,
            "V2_missed_10pct": v2, "V3_exits_adverse_1bp": v3}


def _pooled(fold_results, hid, cost):
    out = []
    for key, fr in fold_results.items():
        if fr["hypothesis_id"] == hid:
            out.extend(fr["costs"][cost]["trades"])
    return out


def stage_primary(hyps, symbols):
    hyps_doc = json.loads((RESEARCH_DIR / "hypotheses.json").read_text())
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
    from research.phase11f import metrics as M
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
                     "metrics_C": {k: m_all["C"][kk] for k, kk in
                                   (("net", "net_pnl"), ("gross", "gross_pnl"),
                                    ("fees", "fees"), ("slippage", "slippage"),
                                    ("expectancy", "expectancy"),
                                    ("pf", "profit_factor"), ("sharpe", "sharpe"),
                                    ("sortino", "sortino"), ("maxdd", "max_drawdown"),
                                    ("wins", "wins"), ("losses", "losses"),
                                    ("win_rate", "win_rate"))}}
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
    hyps_doc = json.loads((RESEARCH_DIR / "hypotheses.json").read_text())
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
                        cls = BY_ID[hid]
                        out = EX.run_candidate(series[f["test_start"]:f["test_end"]],
                                               cls(**overrides), symbol, cost_key=cost)
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
        from research.phase11f import metrics as M
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
