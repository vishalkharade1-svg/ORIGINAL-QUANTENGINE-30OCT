# Phase 11B — Quantitative Correctness Evidence

Commit: `c72cc52` (parent `20af32e`). All values measured.

## Invariants verified (67 tests, `tests/test_quant_math_11b.py`)

- **Sizing:** risk=balance×pct, stop=|entry−stop|, qty=risk/stop, notional=qty×entry,
  margin=notional/leverage, allocation cap scales with explicit reason, expected_loss
  re-aligned. Invalid (zero stop, bad balance/entry, negative multiplier floored at
  0.001, leverage<=0 → 1.0) all fail closed; negative balance never yields negative qty.
- **Manager hygiene:** rounding + purity (input never mutated), dust drop at 1e-6,
  notional cap ≤500, double-apply no-op, NEW negative-qty clamp + entry<=0 reject.
- **Accounting:** long/short win/loss exact, breakeven exact-zero (dust is NOT BE),
  zero-denominator guards, unknown direction → 0, full simulator lifecycles incl.
  conservative ambiguous-bar LOSS flag, consume-once, consecutive booking.
- **Account:** profit/loss/breakeven streaks + counters, balance == starting + realized,
  NEW in-place reset preserving identity (also through `Backtester.reset()`).
- **Risk adversarial:** extreme size capped, tiny capital dust-dropped, duplicate
  setup → one order, opposing ideas distinct, leverage bound, risk ≤ nominal.
- **Lifecycle:** eligible=created+1, expiry exactly at created+1+30, fill once,
  invalidation ≠ expiry, creation bar ineligible (no lookahead).
- **Dedup:** exact + cross-structural duplicates collapse; entry/stop/target/
  direction sensitivity; tick-snap definition (0.5 grid buckets verified).
- **Walk-forward:** chronological gapless folds, slice isolation, deterministic
  generation, best-config selection, invalid sizes raise.
- **Metrics:** win/loss/BE triad, expectancy over all completed, profit-factor edges
  (inf/0/0), drawdown math + account reconciliation, Sharpe/Sortino independently
  recomputed (trade-based position returns, sample std, sqrt(N), downside incl.
  zeros, NOT annualized).

## Gate A determinism (11B-I)

Two separate processes, byte-identical stdout
(sha256 `ba908c89…52cbe2`), PASS both: 27 orders, 11 fills, 6W/5L/0BE, net 3.80889.

## Cost sensitivity (11B-C/J) — same dataset, same logic, costs at booking only

| Scenario | Fills | W/L | Comm | Slip | Net | Balance | PF |
|---|---|---|---|---|---|---|---|
| A zero (canonical) | 11 | 6/5 | 0.0 | 0.0 | +3.81 | 2003.81 | 3.30 |
| B small (0.02% + 1bp, assumed) | 11 | 1/10 | 11.0 | 11.0 | −18.19 | 1981.81 | 0.08 |
| C moderate (0.05% + 2bp, assumed) | 11 | 0/11 | 27.5 | 22.0 | −45.69 | 1954.31 | 0.0 |
| D adverse (0.059% + 5bp, assumed) | 11 | 0/11 | 32.45 | 55.0 | −83.64 | 1916.36 | 0.0 |

Fee grounding: delta.exchange/fees, Sept 2026 (futures maker 0.02%, taker 0.05%,
+18% GST India). Slippage modeled, not quoted. Fills identical across scenarios
(costs apply at booking; no feedback into signals/sizing — verified). Accounting
reconciles exactly (net == gross − comm − slip) in all four.

**Interpretation (not a viability claim):** the mathematics are correct; the
economics are not viable at realistic costs — the baseline edge (+0.35/trade avg)
is an order of magnitude smaller than per-trade costs (~1–2 in scenario B).
BASELINE PERFORMANCE (+3.81, zero-cost, idealized) is distinct from
COST-SENSITIVITY PERFORMANCE (negative under all modeled cost loads).

## Mutation proof (temporary, reverted, zero MUT strings remain)

- Sizer `risk/stop → risk*stop`: 5 tests fail.
- Accounting long-PnL sign flip: 5 tests fail.

## Regressions

- New file: 67 passed, 0 failed.
- Full suite: 1835 passed, 0 failed.
- compileall core: clean.
- LIVE: disabled; real orders 0; no network in tests.

## Limitations

- `cancel/fetch/balance/positions` pass-throughs remain un-gated (11A note stands).
- Simulator-level direct `open_trade(entry=0)` relies on upstream sizer/manager
  rejection; manager now rejects entry<=0 at the choke point.
- `.env` tracked with API-like strings (separate hygiene task); tests use fakes only.
