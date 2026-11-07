"""Phase 11F-3 frozen validation protocol (methodology only, no execution).

Freezes HOW the eight preregistered hypotheses will later be
evaluated — walk-forward geometry, OOS meaning, evidence minimums,
multiple-testing rules, random-baseline / Monte Carlo / regime /
ablation plans, cost order, and metric reuse. Nothing here evaluates
a hypothesis, opens D3, or reads market data: fold geometry is pure
index arithmetic; all plans are frozen data + validators.

Rationale for frozen numbers (fixed BEFORE any hypothesis result):
  * PURGE_BARS=150 covers the longest feature lookback (Donchian-100)
    plus swing confirmation (3) plus max pending wait (5) plus margin,
    so indicator warmup/state can never leak across the boundary.
  * EMBARGO_BARS=25 exceeds any order-expiry tail (max wait 5) after
    the test start, killing boundary-touch leakage.
  * TRAIN_MIN_BARS=2000 matches the 11E clean-OOS scale; TEST_BARS=1000
    gives multi-regime coverage per fold; STEP_BARS=1000 keeps folds
    non-overlapping and chronological.
  * MIN_TRADES=30 reuses the 11E E6 adequacy gate (unchanged rule).
"""

from __future__ import annotations

import statistics

from research.phase11f.contracts import COST_SCENARIOS_11F, FUNDING_PER_TRADE

VALIDATION_PROTOCOL_VERSION = "11F-3.0"

# --------------------------------------------------
# Walk-forward geometry (§2)
# --------------------------------------------------

WALK_FORWARD_SPEC = {
    "design": "expanding-origin chronological folds",
    "train_rule": "train_start = 0 for every fold; "
                  "train_end = train_min_bars + k*step_bars",
    "train_min_bars": 2000,
    "test_bars": 1000,
    "purge_bars": 150,
    "embargo_bars": 25,
    "step_bars": 1000,
    "n_folds": 4,
    "invariant": "train_end + purge + embargo <= test_start < test_end",
}

# End-exclusive bar-index intervals throughout.


def build_folds(n_bars, train_bars=2000, test_bars=1000,
                purge_bars=150, embargo_bars=25, step_bars=1000,
                n_folds=4):
    """Expanding-origin folds over ``range(n_bars)``.

    Fold k: train=[0, train_bars+k*step),
    purge/embargo gap, test=[train_end+purge+embargo, +test_bars).
    Raises ValueError when the dataset cannot host the plan
    (minimum-evidence failure, never silent truncation).
    """
    folds = []
    for k in range(n_folds):
        train_start = 0
        train_end = train_bars + k * step_bars
        purge_start, purge_end = train_end, train_end + purge_bars
        embargo_start, embargo_end = purge_end, purge_end + embargo_bars
        test_start, test_end = embargo_end, embargo_end + test_bars
        if test_end > n_bars:
            raise ValueError(
                "fold %d needs %d bars, dataset has %d" % (k, test_end, n_bars))
        folds.append({
            "fold": k, "train_start": train_start, "train_end": train_end,
            "purge_start": purge_start, "purge_end": purge_end,
            "embargo_start": embargo_start, "embargo_end": embargo_end,
            "test_start": test_start, "test_end": test_end,
        })
    return folds


def validate_folds(folds):
    """Return violation strings for fold geometry (empty = PASS)."""
    errors = []
    prev_test_end = -1
    for f in folds:
        t0, t1 = f["train_start"], f["train_end"]
        p0, p1 = f["purge_start"], f["purge_end"]
        e0, e1 = f["embargo_start"], f["embargo_end"]
        s0, s1 = f["test_start"], f["test_end"]
        if not (t0 < t1 <= p0 < p1 <= e0 < e1 <= s0 < s1):
            errors.append("fold %d breaks train<purge<embargo<test order" % f["fold"])
        if not (t1 + (p1 - p0) + (e1 - e0) <= s0):
            errors.append("fold %d purge/embargo gap too small" % f["fold"])
        train = set(range(t0, t1))
        if train & set(range(p0, p1)):
            errors.append("fold %d train overlaps purge" % f["fold"])
        if train & set(range(s0, s1)):
            errors.append("fold %d train overlaps test" % f["fold"])
        if set(range(p0, p1)) & set(range(s0, s1)):
            errors.append("fold %d purge overlaps test" % f["fold"])
        if set(range(e0, e1)) & set(range(s0, s1)):
            errors.append("fold %d embargo overlaps test" % f["fold"])
        if s0 < prev_test_end:
            errors.append("fold %d test overlaps an earlier test" % f["fold"])
        prev_test_end = s1
    starts = [f["test_start"] for f in folds]
    if starts != sorted(starts):
        errors.append("folds not chronological")
    return errors


def validate_expanding(folds):
    """Expanding-origin semantics (empty = PASS): train always starts
    at 0, train ends grow monotonically, trains nest, tests stay
    chronological and disjoint."""
    errors = []
    prev_train_end = -1
    prev_test_end = -1
    for f in folds:
        if f["train_start"] != 0:
            errors.append("fold %d train_start != 0 (rolling, not expanding)"
                          % f["fold"])
        if not f["train_end"] > prev_train_end:
            errors.append("fold %d train_end not monotonic" % f["fold"])
        if not f["test_start"] >= prev_test_end:
            errors.append("fold %d test overlaps a prior test" % f["fold"])
        prev_train_end = f["train_end"]
        prev_test_end = f["test_end"]
    trains = [(f["train_start"], f["train_end"]) for f in folds]
    for (a0, a1), (b0, b1) in zip(trains, trains[1:]):
        if not (a0 >= b0 and a1 <= b1):
            errors.append("train windows not nested")
            break
    return errors


# --------------------------------------------------
# Parameter/fit isolation (§4)
# --------------------------------------------------

def tercile_thresholds(values):
    """33/66pct cutoffs of TRAINING-region values only."""
    if len(values) < 3:
        raise ValueError("need >=3 training values for terciles")
    qs = statistics.quantiles(sorted(values), n=3, method="exclusive")
    return (qs[0], qs[1])


def check_threshold_fit_region(fit_start, fit_end, test_start):
    """True iff the fit window ends at/before the test starts."""
    return fit_end <= test_start


# --------------------------------------------------
# Minimum evidence rules (§9, frozen pre-results)
# --------------------------------------------------

MIN_EVIDENCE = {
    "min_trades_pooled": 30,
    "min_folds": 3,
    "min_active_folds": 2,
    "min_trades_per_regime_cell": 3,
    "zero_trade_fold": "EMPTY — reported explicitly, never silently dropped",
    "failed_fold": "reported with full metrics, counts toward active-fold rule",
}


def assess_evidence(n_trades, n_folds, active_folds):
    if n_trades < MIN_EVIDENCE["min_trades_pooled"]:
        return "INSUFFICIENT: pooled %d < %d" % (
            n_trades, MIN_EVIDENCE["min_trades_pooled"])
    if n_folds < MIN_EVIDENCE["min_folds"]:
        return "INSUFFICIENT: %d folds < %d" % (n_folds, MIN_EVIDENCE["min_folds"])
    if active_folds < MIN_EVIDENCE["min_active_folds"]:
        return "INSUFFICIENT: %d active folds < %d" % (
            active_folds, MIN_EVIDENCE["min_active_folds"])
    return "SUFFICIENT"


# --------------------------------------------------
# Multiple-hypothesis protocol (§10, frozen pre-results)
# --------------------------------------------------

MULTIPLE_TESTING = {
    "n_hypotheses": 8,
    "alpha": 0.05,
    "bonferroni_reference": 0.05 / 8,
    "exploratory_method": "Benjamini-Hochberg FDR q=0.10",
    "selection_rule": "NO ranking selection: a hypothesis passes only its own "
                      "pre-registered economic gates; any single pass is "
                      "hypothesis-generating pending holdout replication",
    "limitation": "no formal family-wise confirmatory claim without D3 replication",
}


def bonferroni_threshold(alpha, n):
    return alpha / n


def bh_reject(pvalues, q):
    """Benjamini-Hochberg rejection set (indices), deterministic."""
    order = sorted(range(len(pvalues)), key=lambda i: (pvalues[i], i))
    rejected = set()
    m = len(pvalues)
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= rank / m * q:
            rejected.add(i)
    # Step-up: keep the largest passing rank and everything below it.
    if not rejected:
        return set()
    kmax = max(rank for rank, i in enumerate(order, start=1) if i in rejected)
    return set(order[:kmax])


# --------------------------------------------------
# Random-baseline protocol (§11, defined only)
# --------------------------------------------------

RANDOM_BASELINE_PLAN = {
    "design": "per-fold controls (11E corrected methodology)",
    "draws_per_fold": 500,
    "seeds": "1108000..1108499",
    "entries": "uniform over the fold TEST bars only",
    "exits": "frozen 2:1 stop/TP, k = training-region median(stop_dist/ATR14)",
    "notional_cap": 500,
    "costs": "scenario C",
    "boundary": "MTM at fold last close; never cross a fold boundary",
    "comparison": "strategy pooled net(C) vs per-fold random median percentile",
}


def check_random_trade_within_fold(entry_bar, exit_bar, test_start, test_end):
    return test_start <= entry_bar < test_end and test_start <= exit_bar < test_end


# --------------------------------------------------
# Monte Carlo protocol (§12, defined only)
# --------------------------------------------------

MONTE_CARLO_PLAN = {
    "trade_order_shuffle": {"sims": 5000, "seed": 1107001},
    "bootstrap_expectancy": {"sims": 5000, "seed": 1107002},
    "statistics": ["P(net<0)", "p5/p50/p95 final", "maxDD distribution",
                   "P(DD>observed)", "losing-streak distribution"],
    "ci_method": "empirical percentiles",
    "null": "no edge beyond modeled costs",
}

# --------------------------------------------------
# Regime protocol (§13, defined only)
# --------------------------------------------------

REGIME_PLAN = {
    "volatility": "ATR14/close terciles, cutoffs fit on TRAINING bars only",
    "trend": "close vs SMA50 at entry bar (past bars only)",
    "min_trades_per_cell": 3,
    "prohibited": ["full-dataset quantiles", "future-aware thresholds",
                   "post-hoc regime definitions", "result-driven selection"],
}

# --------------------------------------------------
# OOS definition (§15)
# --------------------------------------------------

OOS_RULES = [
    "chronologically later than all fitting/selection data",
    "never used for fitting (thresholds, k, cutoffs)",
    "never used for threshold or candidate selection",
    "D3 is the final sealed holdout and is NOT part of this phase",
]

# --------------------------------------------------
# Execution freeze (§7)
# --------------------------------------------------

EXECUTION_FREEZE = {
    "channel": "LIMIT_RETEST via research-only mock.patch (production default "
               "BREAKOUT_CONTINUATION-only, unchanged)",
    "rule": "no result-driven substitution between LIMIT_RETEST / "
            "MARKET_CONFIRMATION / BREAKOUT_CONTINUATION",
}


def execution_models():
    """hypothesis_id -> preregistered execution_model (read-only)."""
    import json
    doc = json.loads((__import__("pathlib").Path(__file__).resolve().parent
                      / "hypotheses.json").read_text())
    return {h["hypothesis_id"]: h["execution_model"] for h in doc["hypotheses"]}


# --------------------------------------------------
# Cost application order (§6)
# --------------------------------------------------

COST_ORDER = ["signal", "entry", "position", "gross", "commission",
              "slippage", "funding", "net"]


def apply_cost_sequence(gross, position_value, cost_key="C"):
    """Frozen economic order: gross -> commission -> slippage -> funding -> net."""
    from research.phase11f.contracts import cost_breakdown
    parts = cost_breakdown(position_value, cost_key)
    net = gross - parts["commission"] - parts["slippage"] - parts["funding"]
    return {"gross": float(gross), "commission": parts["commission"],
            "slippage": parts["slippage"], "funding": parts["funding"],
            "net": float(net), "order": list(COST_ORDER)}


def verify_ablations():
    """Preregistered single-removal check (data/exec/cost/risk/expiry identical)."""
    from research.phase11f import candidates as C
    from research.phase11f.contracts import ABLATIONS, validate_ablations
    errors = validate_ablations()
    by_id = {cls.id: cls for cls in C.ALL}
    for hid, variants in ABLATIONS.items():
        names = sorted(n for n, _ in by_id[hid]().ablations())
        if names != sorted(v["name"] for v in variants):
            errors.append("%s code/registry ablation mismatch" % hid)
        for v in variants:
            if v["name"] != "full" and len(v["overrides"]) != 1:
                errors.append("%s %s is not a single removal" % (hid, v["name"]))
    # Non-ablated hypotheses expose full only (no hidden variants).
    for hid in ("H11F-001", "H11F-003", "H11F-004", "H11F-006", "H11F-008"):
        if by_id[hid]().ablations() != [("full", {})]:
            errors.append("%s must expose full only" % hid)
    return errors


def cost_scenarios_frozen():
    """Exact 11F/11B/11E numerical definitions (no new scenario)."""
    return {k: dict(v) for k, v in COST_SCENARIOS_11F.items()}
