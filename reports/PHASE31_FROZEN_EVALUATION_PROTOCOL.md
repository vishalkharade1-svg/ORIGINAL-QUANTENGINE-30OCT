STATUS: PLANNED

# Phase 31 Frozen Evaluation Protocol

## 1. Protocol Overview

This document defines the preregistered evaluation protocol that must be frozen BEFORE any final holdout evaluation is run. No parameters may be tuned against the holdout after freezing. Any exploratory changes must use development data and be recorded as such.

## 2. Protocol Identification

| Field | Value |
|-------|-------|
| Protocol ID | `QE-PHASE31-PROTOCOL-001` |
| Strategy identity | `BREAKOUT_CONTINUATION` (active entry mode per `config/risk_settings.py`) |
| Strategy source revision | `ffefa14` (HEAD at Phase 31 start) |
| Configuration revision | `config/risk_settings.py` at Phase 31 start |
| RR policy | `TRADING_MIN_RISK_REWARD=1.0`, `TRADING_MAX_RISK_REWARD=20.0` |
| Protocol hash | `TO_BE_COMPUTED_AFTER_FINALIZATION` |
| Freeze timestamp | `TO_BE_RECORDED_AT_FREEZE` |

## 3. Strategy Configuration (Frozen)

| Parameter | Value | Source |
|-----------|-------|--------|
| Entry mode | `BREAKOUT_CONTINUATION` | `config/risk_settings.py:159` |
| Active entry modes | `("BREAKOUT_CONTINUATION",)` | `config/risk_settings.py:161` |
| Minimum RR | `1.0` | `config/risk_settings.py:458` |
| Maximum RR | `20.0` | `config/risk_settings.py:459` |
| Trailing enabled | `True` | `config/risk_settings.py:475` |
| Trailing activation R | `1.0` | `config/risk_settings.py:476` |
| Trailing distance R | `0.5` | `config/risk_settings.py:477` |
| Trailing method | `R_DISTANCE` | `core/risk/trading_policy.py:31` |
| Trailing step R | `0.0` | `config/risk_settings.py` (default) |
| Auto exit on opposite signal | `True` | `config/risk_settings.py` (default) |
| Exit mode | `FIXED_TARGET` (baseline) / `TRAILING_STOP` (experiment) | `config/risk_settings.py:473-474` |
| Kill switch | `KILL_SWITCH_ENV_VAR = "QE_KILL_SWITCH"` | `config/risk_settings.py:416` |
| Commission per trade | `0.0` | `config/risk_settings.py:352` |
| Commission rate | `0.0` | `config/risk_settings.py:354` |
| Slippage BPS | `0.0` | `config/risk_settings.py:360` |
| Starting balance | `2000` | `config/risk_settings.py:15` |
| Max allocation per trade | `500` | `config/risk_settings.py:30` |
| Max open positions | `1` | `config/risk_settings.py:440` |
| Max portfolio risk | `0.03` | `config/risk_settings.py:442` |
| Max correlated risk | `0.02` | `config/risk_settings.py:444` |

## 4. Execution Rules (Frozen)

| Rule | Value |
|------|-------|
| Entry delay | `ENTRY_DELAY_BARS = 1` (no same-candle fill) |
| Max wait bars | `MAX_WAIT_BARS = 30` |
| Max pending orders | `MAX_PENDING_ORDERS = 8` |
| Max total exposure pct | `MAX_TOTAL_EXPOSURE_PCT = 25.0` |
| Intrabar policy | `CONSERVATIVE` (stop first, target second) |
| Gap-fill mode | `CONSERVATIVE` (use candle open if <= stop, else stop) |
| Stop-first ordering | Stop checked before target on same bar |
| Trailing activation | 1R favorable move |
| Trailing distance | 0.5R from peak/favorable price |
| Trailing step | 0.0 (disabled) |
| Trailing tick rounding | Floor for long, ceil for short |
| Trailing monotonicity | Never loosens once tightened |

## 5. Market Data Sources (Frozen)

| Source | Path | Status |
|--------|------|--------|
| Certified | `data/history/BTCUSDT_1m_phase17_fresh.json` | SEEN_DATA (development) |
| Extended | `data/history/BTCUSDT_1m_oos_topup.json` | SEEN_EXTENSION (not holdout) |
| Phase 19 Extension | `data/history/BTCUSDT_1m_phase19_extension.json` | UNKNOWN_PROVENANCE |
| Holdout | NOT AVAILABLE | Owner must acquire |

**No genuinely independent holdout exists.** The protocol must record this limitation and cannot claim an unbiased edge.

## 6. Cost Assumptions (Frozen)

| Component | Value | Label |
|-----------|-------|-------|
| Commission per trade | 0.0 | `CONFIGURED_SIMULATION` |
| Commission rate | 0.0 | `CONFIGURED_SIMULATION` |
| Slippage BPS | 0.0 | `CONFIGURED_SIMULATION` |
| Funding schedule | 529 hourly events 2026-09-05 → 2026-09-27 | Verified |

**Note:** All costs are `CONFIGURED_SIMULATION` — venue-observed costs are unknown. Any nonzero claim requires explicit operator configuration via environment variables (`QE_PAPER_COMMISSION_PER_TRADE`, `QE_PAPER_COMMISSION_RATE`, `QE_PAPER_SLIPPAGE_BPS`).

## 7. Risk Limits (Frozen)

| Limit | Value |
|-------|-------|
| Risk per trade | 0.01 (1%) |
| Max allocation per trade | 500 (quote currency) |
| Max open positions | 1 |
| Max portfolio risk | 0.03 |
| Max correlated risk | 0.02 |
| Max daily loss | 0.02 |
| Max weekly loss | 0.05 |
| Max monthly loss | 0.10 |
| Kill switch | Fail-closed |

## 8. Performance Metrics (Primary)

| Metric | Definition |
|--------|------------|
| Net PnL after costs | Realized PnL minus commission, slippage, funding |
| Expectancy per trade | Net PnL / number of closed trades |
| Realized RR | Actual exit distance / actual stop distance |
| Win rate | Winning trades / total closed trades |
| Profit factor | Gross wins / gross losses |
| Maximum drawdown | Peak-to-trough equity decline |
| Fill rate | Filled orders / total orders |
| Trailing-stop activations | Count of trades where trailing stop caused exit |
| Exit-reason distribution | Count by INITIAL_STOP / TAKE_PROFIT / TRAILING_STOP / SIGNAL_EXIT |

## 9. Sample-Adequacy Requirements

| Requirement | Threshold | Rationale |
|-------------|-----------|-----------|
| Minimum closed trades | 30 | Statistical significance for win rate |
| Minimum filled orders | 30 | Avoid edge claims on <30 observations |
| Maximum fill rate variance | N/A | Report raw rate; no smoothing |
| Uncertainty reporting | Wilson score interval for win rate | Accounts for small samples |

## 10. Failure Criteria

The experiment is invalidated if:

| Condition | Consequence |
|-----------|-------------|
| Holdout data was used for tuning | Protocol void; results not usable for edge claim |
| Costs silently treated as zero without disclosure | Protocol void; results labeled `CONFIGURED_SIMULATION` |
| Look-ahead bias detected | Protocol void; results not usable |
| Trailing stop claims exchange-side protection | Protocol void; local simulation ≠ exchange-side |
| Fill count < 30 on holdout | Verdict limited to `INSUFFICIENT SAMPLE` |

## 11. Comparison Baselines

| Baseline | Description |
|----------|-------------|
| C1: Fixed-target only | No trailing stop; fixed TP/SL |
| C2: Trailing stop enabled | `R_DISTANCE`, activation 1R, distance 0.5R |
| C3: Fixed-target with realistic costs | Nonzero commission/slippage (if owner provides) |

## 12. Freeze Statement

**This protocol is frozen as of Phase 31.** No parameter changes may be made against holdout results. Any exploratory target-selection or cost experiments must use development data and be recorded separately. The final verdict must be one of: `EDGE NOT ESTABLISHED`, `INSUFFICIENT EVIDENCE`, `PROMISING — REQUIRES INDEPENDENT VALIDATION`, or `SUPPORTED BY VALIDATED EVIDENCE`.

---

*Frozen evaluation protocol documented at: `F:\vishal 3\near final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/reports/PHASE31_FROZEN_EVALUATION_PROTOCOL.md`*
