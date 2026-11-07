# Phase 11E Closure Amendment (reporting clarifications, no threshold changes)

The pre-registered specification (`research/phase11e/spec.json`,
committed `0ede560` BEFORE any OOS result was examined) remains
immutable. This amendment clarifies terminology and methodology
only. **No economic acceptance criterion was changed.** All
pre-registered thresholds (E5 net(C) > 0, E6 n ≥ 30, E7 70% rule,
E9/E10 probabilities, cost scenarios, seeds, sensitivity grid)
apply exactly as specified.

## A1. E4 split (REPORTING CLARIFICATION)

Original rule (spec.json, gates.E4_walkforward): "folds execute with
no leakage (methodological); economics judged under E5/E6".

Ambiguity: the final report used E4 = PASS alongside a
WALK-FORWARD = FAIL summary, mixing two questions.

Clarification (no threshold change):

| Gate  | Question                                            | Rule (unchanged)                        |
| ----- | --------------------------------------------------- | --------------------------------------- |
| E4-M  | Is walk-forward methodology causal and leak-free?   | PASS iff folds execute with no leakage  |
| E4-E  | Does walk-forward economics pass?                   | PASS iff pooled OOS net(C) > 0 (as E5)  |

E4-E reuses the E5 economic rule verbatim; it adds no new criterion.

## A2. Regime calibration (METHODOLOGY CORRECTION)

Original implementation: volatility tercile cutoffs from pooled
D1+D2 IS statistics, applied to all folds including earlier ones —
later observations (including post-D2 September data) could inform
earlier-fold regime labels.

Corrected implementation: per-fold calibration on bars strictly
before that fold's OOS start (F1 ← pre-D2 fetch; F2 ← +F1; F3 ← +F2;
F4 ← +F3+D1, D1 being strictly prior to D3). A `filter_prior`
defense-in-depth drops any bar with timestamp ≥ OOS start even if
passed one. No economic threshold involved; regime analysis is a
diagnostic, not selection.

## A3. Random baseline (METHODOLOGY CORRECTION + PRE-REGISTERED RULE)

Original implementation: pooled D2+D3 candidate entries with holding
periods able to cross fold boundaries.

Corrected implementation: per-fold controls (500 draws each; trades
per draw = that fold's strategy fill count; F3 undefined →
INSUFFICIENT). Boundary rule, fixed BEFORE seeing corrected results:
candidate entries uniform over the fold's bars; exits scan fold bars
only; unclosed trades mark to market at the fold's last close. One
deterministic rule, documented here, applied to all folds.

## A4. P&L semantics (REPORTING CLARIFICATION)

Original `trade_metrics` exposed `gross_pnl` computed over net
outcomes (equal to net by construction) alongside a separately
correct `net_pnl` — misleading duplication.

Clarified semantics (values unchanged, labels now exact):
gross_pnl = Σ price-movement P&L before costs; fees = Σ commission;
slippage = Σ slippage; net_pnl = gross − fees − slippage, with a
`net_consistency_diff` check against booked nets. Expectancy, PF,
Sharpe/Sortino, R-multiples, and drawdown remain NET-based, matching
production `PerformanceAnalytics` (parity tested).

## Statement

No acceptance threshold, cost scenario, seed, fold definition, or
sensitivity variant was altered. Prior (v1) evidence is preserved in
git history; the closure report carries the v1-vs-corrected
comparison table.
