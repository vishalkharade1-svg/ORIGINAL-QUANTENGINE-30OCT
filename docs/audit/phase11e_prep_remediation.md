# Phase 11E-Prep Remediation Report — Adversarial Numeric Safety (C1) + Allocation/Risk Truthfulness (H1)

Correctness remediation only. No strategy, parameter, fee, methodology,
or LIVE changes. Strategy code untouched (diff touches risk/accounting/
simulator/candles/settings + tests only).

## 1. Scope and defects

C1 (CRITICAL): NaN/±Inf bypassed risk guards through sizing → audit →
simulator → classification → ledger. Reproduced on HEAD `1bfa190`:
`balance=nan → valid=True qty=nan`; `stop=nan → valid`; `entry=inf →
valid`; audit kept `qty=nan`; simulator created the trade;
`classify(NaN)→BREAKEVEN`, `classify(+Inf)→WIN`, `classify(-Inf)→LOSS`;
`load_history` accepted `high=Inf`, `open=NaN` while `update()` rejects them.

H1 (HIGH): `MAX_ALLOCATION_PER_TRADE=500` meant margin in the sizer
(PV ≤ 5000 at lev 10) and notional in the manager (PV ≤ 500), and the
intent kept stale pre-cap risk. Reproduced: sizer qty 0.0644/PV
5000/risk 6.44 → manager clamped to 0.00644/PV 500.

## 2. Root causes

- NaN/Inf comparisons are False, so every `<= 0` / `min` / `max` bound
  passes them; `min`/`max` additionally launder NaN into finite values
  (found live: NaN confidence → 0.0 via `max`, NaN risk → 0.001 via the
  clamp — the choke was placed before the clamp after discovering this).
- The sizer's allocation cap was written against margin while the
  manager (docstring, reason string, `max_quantity` formula, constant
  name) implements notional. NOTIONAL adopted as the single unit; the
  sizer was the outlier.
- `Trade.risk_amount` was copied from the order even after the manager
  changed the quantity; the intent had no post-cap risk field.

## 3. Files changed (impl commit `9274068`)

- `core/risk/position_sizer.py`: finite guards (balance/entry/stop/
  confidence/drawdown/risk-percent choke pre-clamp; leverage coerce);
  notional cap (`PV > allocation`, leverage-independent); unit docs.
- `core/risk/position_manager.py`: audit zeroes non-finite quantity/
  entry with reasons; `max_quantity` notional doc.
- `core/backtesting/trade_simulator.py`: `open_trade` requires finite
  entry/stop/TP and finite qty > 0; recomputes `trade.risk_amount =
  final_qty × stop_distance` ONLY when the manager changed the
  quantity (scripted authored risk otherwise preserved verbatim).
- `core/backtesting/accounting.py`: `classify_pnl` raises ValueError
  on non-finite P&L (never WIN/LOSS/BREAKEVEN).
- `data/candle_builder.py`: `load_history` rejects non-finite OHLC
  (streaming/bulk paths agree).
- `core/risk/order_intent.py`: new `actual_risk_percent` field
  (default 0.0, backward compatible).
- `core/risk/risk_engine.py`: populates it from the sizer.
- `config/risk_settings.py`: `MAX_ALLOCATION_PER_TRADE` documented as
  notional.

Final authority map: final quantity — `open_trade` post-manage; final
notional — audit reconciled PV; margin — PV/leverage (derived); stop
distance — sizer; actual risk — final_qty × stop_distance (trade) and
sizer post-cap EL (intent); `actual_risk_percent` — intent truth field.

## 4. Tests (test commit `6d90b29`)

- New `tests/test_numeric_safety_11eprep.py` (23 tests): 9 sizer
  sign/type cases + factor/leverage cases; audit ×4; simulator ×5;
  classify ×4; candles ×3; phantom e2e ×2; accounting invariants ×1.
- New `tests/test_allocation_truth_11eprep.py` (11 tests):
  below/at/above cap, lev-1 vs lev-10 identity, sizer↔manager
  agreement, risk/actual/intent truthfulness, simulator recompute.
- Updated pins that encoded the margin unit, with rationale comments:
  `test_position_sizing_9q.py` (below-cap scenario), `test_quant_math_11b.py`
  (3 sizer formulas → notional expectations), `test_risk_execution_contract.py`
  (risk/fees at PV 500).

## 5. Mutation evidence (all detected, all restored, tree verified clean)

- MUT-1 sizer balance guard removed → balance test fails. Restored.
- MUT-2 audit quantity guard removed → 2 audit tests fail. Restored.
- MUT-3 simulator condition reverted to `quantity <= 0` → stop test
  fails (NaN-qty still caught one layer up by the audit — defense in
  depth confirmed). Restored.
- MUT-4 classify raise replaced with BREAKEVEN → 3 tests fail. Restored.
- MUT-5 candle finite check removed → per-field test fails. Restored.
- MUT-6 margin-cap restored → 3 allocation tests fail. Restored.

## 6. C1-F sweep result

No additional Category A sites. Category B (research/analytics/display/
operator-config, documented, unchanged): `net_exit_pnl`, `snapshot()`
FLAT, performance analytics, indicator NaN passthrough, `_env_float`
NaN-tolerant threshold parsing. Category C (impossible by construction
given the five guards, with reasoning): backtester touch/resize gates,
account/portfolio `<= 0` gates (inputs finite post-guards), timestamp
fail-fast, `classify` callers.

## 7. Regression

- `compileall` on core/data/backtesting/config/risk/tests/main: PASS.
- Full suite: **1955 passed, 0 failed, 0 skipped, 0 collection errors**
  (1921 pre-existing + 34 new).
- LIVE safety suites green within the run; `ALLOW_LIVE=false`,
  `LIVE_EXECUTE=false`; 0 real exchange order calls; no credentials.
- Gate A (`verify_gate_a.py`, 2 separate processes, byte-identical
  stdout): orders 27, fills 11, wins 6, losses 5, breakevens 0 —
  identical signals/entries/exits/IDs; net 3.80889 → 0.117534 (CASE 2,
  explained below). avg_r/median_r/Sharpe-family change accordingly
  (same pnl-sign pattern, scaled notionals).

## 8. Gate A change analysis (CASE 2 — deterministic, causally exact)

Per-trade old-vs-new comparison (base worktree @`1bfa190` vs HEAD):
same 11 trades/IDs/entries/exits; 9 trades qty ×0.100 exactly, 1 ×0.210,
1 ×1.000. Cause chain:

1. Gate A signals carry ~$8-wide stops → uncapped sizer qty ≈ 2.5
   contracts (PV ≈ $192k).
2. Old margin cap scaled to margin $500 → intent PV $5000, risk ≈ $0.52.
3. `_resize_for_actual_entry` re-divides intent risk over the actual
   fill distance (~$182) → qty ≈ 0.0029 (PV ≈ $220, under the
   manager's $500 cap, no second clamp).
4. New notional cap scales to PV $500 at intent → risk ≈ $0.052 →
   resize → qty ≈ 0.00029 (PV ≈ $22).
5. Ratio = 5000/500 = 10 exactly where the manager binds in neither
   run; ×0.210 where the old manager-clamped PV 499 meets new
   unclamped PV 105; ×1.000 where the manager clamp binds identically
   in both (PV exactly 500).

Signs cannot change (qty > 0 both runs) → W/L/BE identical. The new
behavior is strictly more correct: the old margin cap let $5000
intents through that only looked safe because the resize happened to
divide by a larger distance — a fill at the signal's own $8 distance
would have opened 10× over the documented allocation. No strategy,
signal, entry, exit, fee, or parameter changed.

## 9. Policy notes (§25 compliance, remaining findings)

- No silent sanitization: every fix rejects or zeroes-with-reason at a
  typed boundary; the sole coercion (non-finite leverage → 1.0) follows
  the pre-existing `<= 0 → 1.0` convention and is tested.
- `risk_multiplier < 0` still clamps to minimum risk (pre-existing edge,
  out of scope, documented here).
- `net_exit_pnl` NaN-passthrough and research-path NaN handling
  unchanged (Category B).
- Hygiene preserved: diff is 13 files, no `.env`/`.venv`/`*.pyc`/
  logs/credentials; `git status` clean except pre-existing untracked
  `muse suggetions*.md`.

## 10. Phase verdicts

C1 — NON-FINITE SAFETY: PASS. H1 — ALLOCATION/RISK TRUTHFULNESS: PASS.
PHASE 11E STATUS: READY (pending this report's acceptance; edge
certification may proceed on corrected sizing).
