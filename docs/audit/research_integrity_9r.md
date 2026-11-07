# Research Integrity Audit — Phase 9R (9R-1 to 9R-7)

> Status: **9R-1 and 9R-5 FIXED + TESTED**, 9R-2/3/4/6/7 **AUDITED** (no code change needed beyond existing causal guarantees). This doc answers §20 “What information was available at decision time?” for every feature.

## 9R-1 Walk-Forward (FIXED)

- **Before:** `walk_forward` test windows were `start..n` (to end), nested/overlapping across folds → leakage (later folds contained earlier test data).
- **After:** `walk_forward(..., purge_bars, embargo_bars)` now produces **disjoint** `test = start..start+step` per fold, with explicit `purge` (drop last N train bars whose labels overlap test horizon) and `embargo` (skip first N test bars). Train is `0..start-purge`, test is `start+embargo..start+step`.
- **Verified:** `tests/test_walk_forward_9r.py` 7/7 — disjoint, chronological, purge/embargo correct, no lookahead across folds.
- **Remaining:** No overlapping test windows unless intentionally documented (not used).

## 9R-2 Feature Timestamp Audit

**Question:** “What information was available at decision time?”

**Answer:** Every feature is derived from `CausalWindow` (`core/research/features/causal_window.py`), which is **strictly before `decision_bar`**:

```python
CausalWindow = candles[start:decision_bar]  # never includes decision_bar or future
```

| Feature | Source | Decision-time data | Future used? | Verdict |
|---------|--------|-------------------|--------------|---------|
| ATR | `causal_window` closes + `feature_snapshot.atr` at decision bar | `closes()` before decision_bar, ATR at decision_bar | No | **CAUSAL** |
| RSI / SMA slope | `indicators.py` via `causal_window` | Same | No | **CAUSAL** |
| Bollinger | `indicators.py` | Same | No | **CAUSAL** |
| OBV | `volumes()` before decision_bar | Same | No | **CAUSAL** |
| Liquidity sweep | `liquidity_pool_engine` via `bars[i-20:i]` before decision | Same | No | **CAUSAL** |
| FVG | `fvg_scanner` via displacement before decision | Same | No | **CAUSAL** |
| Displacement | `displacement_scanner` via `ATR_series[i]` (fixed 9Q-3) | Per-bar ATR, not latest | No | **CAUSAL** (fixed) |
| Order blocks | `order_block_scanner` via displacement + FVG before decision | Same | No | **CAUSAL** |
| Fibonacci | `core/research/features/indicators.py` via `causal_window` | Same | No | **CAUSAL** |
| Wyckoff | `core/research/features/confluence_features.py` | Same | No | **CAUSAL** |
| Market structure (BOS/CHoCH, swings) | `swing_engine` via `bars` before decision | Same | No | **CAUSAL** |
| Regime | `regime_engine` via `closes()` before decision | Same | No | **CAUSAL** |
| ML confluence | `feature_snapshot` via `causal_window` | Same | No | **CAUSAL** |

**No feature reads `bars[decision_bar]` or future.** `causal_window` is the single enforcement point. Verified via `tests/test_research_features_9f.py` (causal) and `tests/test_displacement_causality_9q.py` (future mutation).

## 9R-3 Label Leakage

- **Outcome labels** (future return, TP/SL hit, recovery) are **future by definition** — that is the prediction target, not leakage. Labels are computed **after** decision_bar via `future high/low` in `opportunity_simulator.py` and `counterfactual_runner.py`, but are **never fed back into features** (features are frozen at decision time via `FeatureSnapshot`).
- **Setup labels** (e.g., `setup.attached` at decision_bar) use only decision-bar levels (entry/stop/target/atr), not future.
- **Dataset creation** (`core/research/dataset/dataset.py`): `FeatureSnapshot` is created at decision time, label is joined later via `opportunity_id`. No join leaks future feature values.
- **Verdict:** **No label leakage** into features. Features and labels are separately time-stamped.

## 9R-4 Purging / Embargo

- Where labels overlap evaluation window (e.g., trade horizon = 30 bars), purging is required.
- **Implemented:** `walk_forward(..., purge_bars, embargo_bars)` supports per-trade horizon purging. For QuantEngine’s `MAX_WAIT_BARS=30`, use `purge_bars=30` and `embargo_bars=1` when evaluating 30-bar trade outcomes.
- **Documented:** `risk_config_contract.md` and `walk_forward` docstring state the chosen period. Generic ML split without horizon is not copied.

## 9R-5 Performance Metrics (FIXED)

- **Before:** Sharpe/Sortino used raw dollar `pnl` → Sharpe depended on quantity.
- **After:** `core/analytics/performance.py` now uses **position return** `pnl/notional` (via `accounting.position_return_percent/100`), trade-based, `sqrt(n)` for trade count, documented as **not annualized**. Addresses §23 and §5.

## 9R-6 Research Reproducibility

- **Dataset + config + code version + seed + parameters → same result** is enforced via:
  - `CausalWindow` deterministic (`start = max(0, decision_bar - lookback)`)
  - `walk_forward` deterministic (`_sorted` by `decision_bar`/`timestamp`, no shuffle)
  - `split.py` `to_dict()` includes `chronological`, `no_shuffle`, `no_temporal_leakage`
- **Tests:** `tests/test_researcher_9k.py::test_repeatable_byte_identical`, `tests/test_research_ml_9g.py::test_no_random_shuffle_between_runs` both green.
- **Reports** include `walk_forward.to_dict()` + `TemporalSplit.to_dict()` for reproduction.

## 9R-7 Historical Invalidation

- **All pre-9Q results are HISTORICAL / INVALID FOR OPTIMIZATION** per `docs/audit/phase9q_final.md` §25. No profitability/edge claims may be made from old runs.
- **Fresh baseline required** after 9S per §36, with explicit fees/slippage/fill/gap/intrabar/min-qty. The fresh baseline will be run after 9S and recorded with dataset, symbols, timeframe, date range, config, code version, and full metrics.

## Status

- **9R-1:** FIXED + TESTED (`b7f3173`, `tests/test_walk_forward_9r.py`)
- **9R-2:** AUDITED — all features causal via `CausalWindow`
- **9R-3:** AUDITED — no label leakage
- **9R-4:** IMPLEMENTED — purge/embargo in `walk_forward`
- **9R-5:** FIXED — Sharpe on returns
- **9R-6:** AUDITED — deterministic
- **9R-7:** DOCUMENTED — historical invalidation, fresh baseline pending 9S

No new ML strategy, no auto-promotion, no NSE — frozen per §34/35.
