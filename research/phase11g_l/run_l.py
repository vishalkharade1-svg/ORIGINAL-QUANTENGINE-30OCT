"""Phase 11G-L preregistered research runner (evidence only).

Executes H11GK-001..008 EXACTLY as frozen (hypotheses JSON + runner/
signals.py defaults, thresholds FROM the JSONs) on the certified
Binance UM BTCUSDT 2026-09-05 day (410,535 REAL trades -> 1440 1m bars
built from the trades themselves; kline cross-check max|close diff|
0.0). No optimization, no selection, no D3 (sealed), no LIVE.

Fold geometry (L execution design — K freezes evidence minima, not
geometry; 11F-default 2000/1000 needs 6175 bars > 1440 available):
certified V.build_folds with train 300 / step 300 / test 300 /
purge 150 / embargo 25 / 3 folds over 1440 bars:
  F0 train [0,300)   test [475,775)
  F1 train [0,600)   test [775,1075)
  F2 train [0,900)   test [1075,1375)   (tail [1375,1440) unused)
All certified invariants hold (asserted): expanding origin, nested
trains, disjoint chronological tests, purge/embargo gaps.

Per fold: cold-start NBO engine on the TEST slice only (11G-C pattern;
OHLC-structure features slice-cold-start); trade-flow quantities come
from the full-day causal MarketContext bundle (events <= bar close
only — train history is legitimate causal history, thresholds never
fit). Train region supplies ONLY fitted quantities (regime terciles,
RB holding/stop medians). Costs A/B/C/D via production TradeSimulator.
Classification (preregistered): SUFFICIENT (30+/3 folds/2 active) +
pooled net(C) > 0 -> PASS; SUFFICIENT + net(C) <= 0 -> FAIL; else
INSUFFICIENT_EVIDENCE.

Certified-path limitations (shared with 11G-C, disclosed in report):
positions exit on SL/TP only (no 120-bar time-stop in the production
path); no post-exit 30-bar cooldown gate; trades open at a slice
boundary are dropped, never MTM-fabricated.

Usage:
  python research/phase11g_l/run_l.py --stage primary [--hyp H11GK-001]
  python research/phase11g_l/run_l.py --stage analysis [--hyp ...]
  python research/phase11g_l/run_l.py --stage repro [--hyp ...]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import risk_settings  # noqa: E402
from core.backtesting.trade_simulator import TradeSimulator  # noqa: E402
from core.events.event_bus import EventBus  # noqa: E402
from core.market_state import MarketState  # noqa: E402
from core.pipeline.pipeline_context import PipelineContext  # noqa: E402
from core.risk.account import Account  # noqa: E402
from backtesting.backtester import Backtester  # noqa: E402

from research.phase11f import features as F11  # noqa: E402
from research.phase11f import validation as V  # noqa: E402
from research.phase11f import metrics as M  # noqa: E402
from research.phase11f.contracts import sha256_canonical  # noqa: E402
from research.phase11f.datasets import assert_not_holdout  # noqa: E402
from research.phase11f.harness import COST_SCENARIOS_11F, to_candles  # noqa: E402
from research.phase11g import execution as EX  # noqa: E402 (certified NBO path)
from research.phase11g_j.replay import load as LOAD  # noqa: E402
from research.phase11g_l.runner import signals as S  # noqa: E402
from research.phase11g_l.runner.context import MarketContext  # noqa: E402

RESEARCH_DIR = Path(__file__).resolve().parent
RESULTS_DIR = RESEARCH_DIR / "results"
KDIR = BASE_DIR / "research" / "phase11g_k"
SYMBOL = "BTCUSDT"
COSTS = ["A", "B", "C", "D"]
BY_ID = {cls.id: cls for cls in S.ALL}

RB_DRAWS = 500
RB_SEEDS = range(1108000, 1108000 + RB_DRAWS)
MC_SIMS = 5000
MC_SEED_SHUFFLE = 1107001
MC_SEED_BOOT = 1107002
V2_SEED = 1107

N_TRADES_FROZEN = 410535
N_BARS_FROZEN = 1440

# Registry ablation IDs NOT executed, with reason (A-test pins this
# map exactly: code IDs + this map == registry IDs per hypothesis).
BLOCKED_ABLATIONS = {
    "H11GK-007": {"A2": "DEGENERATE_SKIPPED (residue = full event)"},
    "H11GK-008": {"A2": "IMPLEMENTATION_BLOCKER (CVD-alone has no bar-level stop anchor)"},
}


def hard_gate():
    man = json.loads((KDIR / "freeze" / "freeze_manifest.json").read_text())
    assert man["dataset"] == "binance_um_aggtrades_BTCUSDT_2026-09-05"
    assert man["dataset_hash"].startswith("440c9191")
    assert man["feature_version"] == "real-trade-features-v1"
    assert man["family_count"] == 8
    assert man["D3"] == {"hash": 0, "load": 0, "read": 0}
    assert man["live"] == "DISABLED" and man["production"] == "UNMODIFIED"
    fhash = (KDIR / "freeze" / "freeze_hash.txt").read_text().strip()
    assert fhash.startswith("f803fe7d"), fhash
    import hashlib
    for p in sorted((KDIR / "hypotheses").glob("*.json")):
        doc = json.loads(p.read_text())
        assert doc["status"] == "FROZEN" and doc["version"] == "11gk-v1"
        h = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
        assert h == man["hypothesis_hashes"][p.stem], p.stem
    assert len(BY_ID) == 8, sorted(BY_ID)
    # Registry ablation coverage: code + blocked == registry (no drift).
    for cls in S.ALL:
        doc = json.loads((KDIR / "hypotheses" / (cls.id + ".json")).read_text())
        reg = sorted(a["id"] for a in doc["ablations"] if a["id"] != "A0")
        code = sorted(n for n, _ in cls().ablations() if n != "full")
        blocked = sorted(BLOCKED_ABLATIONS.get(cls.id, {}))
        assert sorted(code + blocked) == reg, (cls.id, code, blocked, reg)
    # LIVE disabled (same derivation as config/settings.py, which reads
    # env with false default; settings.py itself needs dotenv, absent
    # here, so derive directly — identical semantics).
    import os
    assert os.getenv("ALLOW_LIVE", "").lower() not in ("1", "true")
    assert os.getenv("LIVE_EXECUTE", "").lower() not in ("1", "true")
    assert abs(risk_settings.RISK_PER_TRADE - 0.01) < 1e-12
    assert risk_settings.MAX_ALLOCATION_PER_TRADE == 500
    assert COST_SCENARIOS_11F["C"]["COMMISSION_RATE"] == 0.00059
    # D3 sealed: no registered dataset may be a holdout source, and the
    # sealed loader must refuse. (No holdout filenames are named or
    # opened anywhere in L code.)
    from research.phase11g import datasets as DG
    for p in DG.DATASETS.values():
        assert_not_holdout(p["source"])
    try:
        DG.load_holdout("seal-check")
    except DG.SealedHoldoutError:
        pass
    else:  # pragma: no cover
        raise AssertionError("D3 seal broken")
    assert_not_holdout("research/phase11g_l/results")


_DATASET_CACHE = {}


def load_dataset():
    if "bars" in _DATASET_CACHE:
        return _DATASET_CACHE["bars"], _DATASET_CACHE["bundle"]
    rev = LOAD.load_trades()
    trades = rev._trades
    assert len(trades) == N_TRADES_FROZEN, len(trades)
    assert rev.feature_version == "real-trade-features-v1"
    per_min = {}
    for t in trades:
        m = (int(t.event_ms) // 60000) * 60
        b = per_min.get(m)
        if b is None:
            b = per_min[m] = {"o": t.price, "h": t.price, "l": t.price,
                              "c": t.price, "v": 0.0}
        if t.price > b["h"]:
            b["h"] = t.price
        if t.price < b["l"]:
            b["l"] = t.price
        b["c"] = t.price
        b["v"] += t.quantity
    minutes = sorted(per_min)
    assert len(minutes) == N_BARS_FROZEN, len(minutes)
    assert all(b - a == 60 for a, b in zip(minutes, minutes[1:])), "bar gap"
    bars = [{"time": m, "open": per_min[m]["o"], "high": per_min[m]["h"],
             "low": per_min[m]["l"], "close": per_min[m]["c"],
             "volume": per_min[m]["v"]} for m in minutes]
    bundle = MarketContext(bars, trades)
    _DATASET_CACHE["bars"] = bars
    _DATASET_CACHE["bundle"] = bundle
    return bars, bundle


def build_folds():
    folds = V.build_folds(N_BARS_FROZEN, train_bars=300, test_bars=300,
                          purge_bars=150, embargo_bars=25, step_bars=300,
                          n_folds=3)
    assert V.validate_folds(folds) == [], V.validate_folds(folds)
    assert V.validate_expanding(folds) == [], V.validate_expanding(folds)
    return folds


class ResearchPipeline11L(EX.ResearchPipeline11G):
    """11G-C NBO pipeline, reused verbatim (intent assembly, trigger
    stamping, registry lifecycle inherited unchanged). The only L
    wiring is the causal flow bundle, which rides on the research
    candidate instance (see _KBase.attach) — the slots-restricted
    production PipelineContext is never written."""

    def __init__(self, *args, bundle=None, offset=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.candidate.attach(bundle, offset)


def run_fold(cls, bars, bundle, fold, symbol, cost_key, **overrides):
    s0, s1 = fold["test_start"], fold["test_end"]
    sl = bars[s0:s1]
    candles = to_candles(sl, symbol)
    assert len(candles) == len(sl), "candle/bar count diverged"
    inst = cls(**overrides) if overrides else cls()
    ctx = PipelineContext()
    ctx.market = MarketState(symbol=symbol, timeframe="1m")
    bus = EventBus()
    account = Account(starting_balance=risk_settings.STARTING_BALANCE)
    pipeline = ResearchPipeline11L(ctx, inst, account, symbol, "1m",
                                   cost_key, full_bars=list(sl),
                                   bundle=bundle, offset=s0)
    pipeline.subscribe(bus)
    sim = TradeSimulator()
    bt = Backtester(pipeline=pipeline, event_bus=bus, simulator=sim,
                    account=account)
    with mock.patch.multiple(risk_settings, ACTIVE_ENTRY_MODES=("LIMIT_RETEST",)):
        bt.run(candles)
    orders = []
    if ctx.order_registry:
        for o in ctx.order_registry.all():
            orders.append({
                "order_id": o.order_id, "status": o.status,
                "setup_id": o.setup_id,
                "entry": float(o.entry),
                "quantity": float(o.quantity),
                "entry_execution": str(getattr(o, "entry_execution", "")),
            })
    trades = []
    for t in sim.registry.all():
        commission = float(getattr(t, "commission", 0.0) or 0.0)
        slippage = float(getattr(t, "slippage", 0.0) or 0.0)
        net = float(t.pnl)
        try:
            trig = int(str(t.setup_id).rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            trig = None
        trades.append({
            "trade_id": t.trade_id,
            "direction": t.direction,
            "entry": float(t.entry),
            "exit": float(t.exit_price),
            "quantity": float(t.quantity),
            "entry_time": int(t.entry_time),
            "exit_time": int(getattr(t, "exit_time", 0) or 0),
            "stop": float(getattr(t, "stop_loss", 0.0) or 0.0),
            "take_profit": float(getattr(t, "take_profit", 0.0) or 0.0),
            "gross": net + commission + slippage,
            "commission": commission,
            "slippage": slippage,
            "net": net,
            "risk_amount": float(getattr(t, "risk_amount", 0.0) or 0.0),
            "decision_time": (int(sl[trig]["time"])
                              if trig is not None and 0 <= trig < len(sl)
                              else None),
        })
    return trades, {"orders": orders, "n_bars": len(candles),
                    "final_balance": account.balance,
                    "n_signals": pipeline.n_signals}


def train_signal_stats(cls, bars, bundle, fold):
    """Train-only fits: intended stop distances + NBO bars-held medians."""
    t0, t1 = fold["train_start"], fold["train_end"]
    prefix = bars[:t1]
    inst = cls()
    inst.attach(bundle, 0)
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
    return dists, holds


def train_regime_context(bars, fold):
    prefix = bars[:fold["train_end"]]
    closes = [float(b["close"]) for b in prefix]
    atr = F11.atr14(prefix)
    sma = F11.sma(closes, 50)
    t0 = fold["train_start"]
    vols = [a / c for a, c in zip(atr[t0:], closes[t0:]) if a is not None]
    return vols, atr, sma


def classify_trade(trade, bars, fold, terciles):
    lo, hi = terciles
    prefix = bars[:fold["test_end"]]
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
                exit_px = closes[j]
                closed = True
                break
        if not closed:
            exit_px = closes[-1]
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
    best = cur = 0
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
    for fr in fold_results.values():
        if fr["hypothesis_id"] == hid:
            out.extend(fr["costs"][cost]["trades"])
    return out


def stage_primary(hyps):
    bars, bundle = load_dataset()
    folds = build_folds()
    fold_results = {}
    for hid in hyps:
        cls = BY_ID[hid]
        for f in folds:
            key = "%s|F%d" % (hid, f["fold"])
            per_cost = {}
            for cost in COSTS:
                trades, det = run_fold(cls, bars, bundle, f, SYMBOL, cost)
                for t in trades:
                    assert abs((t["gross"] - t["commission"] - t["slippage"]) - t["net"]) < 1e-9
                    assert t["decision_time"] is not None
                    assert all(v in ("NEXT_BAR_OPEN", "") for v in [t.get("entry_execution", "NEXT_BAR_OPEN")])
                for o in det["orders"]:
                    assert o["entry_execution"] == "NEXT_BAR_OPEN", o
                per_cost[cost] = {"trades": trades,
                                  "n_orders": len(det["orders"]),
                                  "n_signals": det["n_signals"]}
            fold_results[key] = {
                "hypothesis_id": hid, "symbol": SYMBOL, "fold": f["fold"],
                "geometry": f, "execution_model": "NEXT_BAR_OPEN",
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
    bars, bundle = load_dataset()
    folds = build_folds()
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
        nfolds = len({fr["fold"] for fr in fold_results.values()
                      if fr["hypothesis_id"] == hid})
        active = sum(1 for fr in fold_results.values()
                     if fr["hypothesis_id"] == hid and fr["costs"]["C"]["trades"])
        verdict = V.assess_evidence(n, nfolds, active)
        verdict = ("PASS" if m_all["C"]["net_pnl"] > 0 else "FAIL") \
            if verdict == "SUFFICIENT" else "INSUFFICIENT_EVIDENCE"
        hypo[hid] = {"verdict": verdict,
                     "evidence": V.assess_evidence(n, nfolds, active),
                     "n_pooled": n, "n_folds": nfolds, "active_folds": active,
                     "metrics_C": {k: m_all["C"][kk] for k, kk in
                                   (("net", "net_pnl"), ("gross", "gross_pnl"),
                                    ("fees", "fees"), ("slippage", "slippage"),
                                    ("expectancy", "expectancy"),
                                    ("pf", "profit_factor"), ("sharpe", "sharpe"),
                                    ("sortino", "sortino"), ("maxdd", "max_drawdown"),
                                    ("wins", "wins"), ("losses", "losses"),
                                    ("win_rate", "win_rate"))}}
        reg = {}
        for f in folds:
            vols, _, _ = train_regime_context(bars, f)
            if len(vols) < 3:
                continue
            terc = V.tercile_thresholds(vols)
            key = "F%d" % f["fold"]
            cells = {}
            fr = fold_results["%s|F%d" % (hid, f["fold"])]
            for t in fr["costs"]["C"]["trades"]:
                cell = classify_trade(t, bars, f, terc)
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
        for f in folds:
            fr = fold_results["%s|F%d" % (hid, f["fold"])]
            n_tr = len(fr["costs"]["C"]["trades"])
            dists, holds = train_signal_stats(BY_ID[hid], bars, bundle, f)
            sd = statistics.median(dists) if len(dists) >= 3 else None
            mh = max(1, int(statistics.median(holds))) if len(holds) >= 3 else None
            res = run_random_baseline(bars[f["test_start"]:f["test_end"]],
                                      n_tr, sd, mh)
            if res["status"] == "OK":
                strat = sum(t["net"] for t in fr["costs"]["C"]["trades"])
                res["strategy_net"] = strat
                res["strategy_percentile"] = (
                    sum(1 for d in res["draws"] if d <= strat) / len(res["draws"]))
                res["train_stop_median"] = sd
                res["train_hold_median"] = mh
                del res["draws"]
            rb["F%d" % f["fold"]] = res
        rbs[hid] = rb
        mcs[hid] = run_monte_carlo([t["net"] for t in pooled_c])
        execs[hid] = exec_overlays(pooled_c)
    for hid in hyps:
        for name, overrides in BY_ID[hid]().ablations():
            if name == "full":
                continue
            for f in folds:
                for cost in ("A", "C"):
                    cls = BY_ID[hid]
                    trades, _ = run_fold(cls, bars, bundle, f, SYMBOL, cost,
                                         **overrides)
                    m = M.research_trade_metrics(trades)
                    abls["%s|%s|F%d|%s" % (hid, name, f["fold"], cost)] = {
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
    args = ap.parse_args()
    hard_gate()
    hyps = [args.hyp] if args.hyp else sorted(BY_ID)
    if args.stage in ("primary", "all"):
        stage_primary(hyps)
        print("PRIMARY done", flush=True)
    if args.stage in ("analysis", "all"):
        hypo = stage_analysis(hyps)
        print(json.dumps({h: hypo[h]["verdict"] for h in hypo}, indent=1), flush=True)
    if args.stage == "repro":
        bars, bundle = load_dataset()
        folds = build_folds()
        fold_results = json.loads((RESULTS_DIR / "fold_results.json").read_text())
        rep = {"folds": {}, "metrics": {}}
        for hid in hyps:
            for f in folds:
                key = "%s|F%d" % (hid, f["fold"])
                for cost in COSTS:
                    ckey = "%s|%s" % (key, cost)
                    trades, _ = run_fold(BY_ID[hid], bars, bundle, f, SYMBOL, cost)
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
        print("REPRO identical =", rep["identical"], flush=True)


if __name__ == "__main__":
    main()
