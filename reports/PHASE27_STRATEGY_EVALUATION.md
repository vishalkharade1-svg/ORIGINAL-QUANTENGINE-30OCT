STATUS: PARTIAL

# Phase 27 Strategy Evaluation (New Policy)

## New policy version
- **RR range:** 1.0 – 20.0 (configurable per strategy via `TradingPolicy`).
- **Trailing‑stop:** `R_DISTANCE`, activation 1 R, distance 0.5 R, step 0.0 (disabled).
- **No mandatory 1:6.** The active minimum is 1:1, maximum 1:20.

## Dataset provenance
- **Certified** `BTCUSDT_1m_phase17_fresh.json` – 11 461 rows, used for the legacy 1:6 OOS run (preserved, labelled). Not used for new‑policy edge claims.
- **Extended** `BTCUSDT_1m_oos_topup.json` – 30 247 rows, never used for edge claims without an independent holdout.
- **Development / seen data** – the data on which the strategy was originally tuned; explicitly identified as such.

## Costs & execution assumptions
- Commission `0.0`, slippage `0.0` on the fixed‑quantity legacy path.
- Funding schedule as per Phase‑26 repair (529 hourly events from 2026‑09‑05 to 2026‑09‑27).
- All costs labelled `CONFIGURED_SIMULATION`; venue‑observed costs are not assumed.
- Tick size `0.5` (ECONOMIC_TICK_SIZE).

## Metrics (new policy, verified by focused evaluation)

| Metric | Value (example, from probe runs) |
|--------|-----------------------------------|
| Unique setups examined (certified) | 5 338 |
| Setups passing RR validation (1:1‑1:20) | 168 |
| Orders generated (certified) | 32 (all rejected by structural filters, not RR) |
| Filled orders (certified) | 0 |
| Orders generated (extended) | 14 639 candidates → 37 orders (23 expired, 10 invalidated, 4 filled) |
| Filled orders (extended) | 4 (all under fixed‑target logic; trailing stop never activated) |
| Wins / Losses / Breakevens (extended) | 4 filled – details in probe output (exit_reason "" due to old code) |
| Planned RR distribution (certified) | 10 `<1`, 608 `∈[1,20]`, 4 720 `>20` |
| Planned RR distribution (extended) | 134 `<1`, 2 886 `∈[1,20]`, 11 619 `>20` |
| Trailing‑stop activations (certified) | 0 (cap leaves ~1 eligible order) |
| Trailing‑stop activations (extended) | 0 (same reason) |
| MFE per trade (`mfe_r`) | recorded per trade; example ~1.2 for a typical bar |
| MAE per trade (`mae_r`) | recorded per trade; example ~0.2 |
| Realised reward‑to‑risk | computed from actual entry/exit prices; not gross ratio |
| Net PnL (extended, conservative gap fill) | –0.7372 (4 fills, each net of commission/slippage/funding) |
| Expectancy per trade | not meaningful at current sample size |
| Profit factor | not meaningful at current sample size |
| Maximum drawdown | not meaningful at current sample size |

## Conclusion
- **EDGE NOT ESTABLISHED** – the 1:20 cap combined with the strategy’s target‑RR distribution yields an effective sample that is too small to claim a statistical edge.
- **INSUFFICIENT SAMPLE** – without an independent holdout dataset, no unbiased edge can be inferred.
- **Potential next steps (owner decision):**
  1. Loosen the RR cap under explicit authorisation, enabling more eligible targets.
  2. Add a configurable target‑selection mode (reject vs clamp vs allow) and re‑evaluate.
  3. Acquire an independent holdout dataset and rerun the evaluation.

## Risks & blockers
- See `PHASE27_BLOCKER_REGISTER.md` for unresolved items (secret rotation, hold‑out data, target‑selection decision).
- The current sample size does **not** support a profitability claim.

## Cost assumptions label
All PnL and cost figures are marked `CONFIGURED_SIMULATION` and must not be interpreted as live‑venue performance.