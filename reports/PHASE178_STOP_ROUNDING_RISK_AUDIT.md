# QuantEngine Phase 178 — Stop-Loss Rounding & Risk Semantics Audit

## Executive Summary

This report delivers a rigorous audit of stop-loss normalization semantics, order types, trigger mechanics, risk budget recalculation, and execution realities.

---

## 1. Stop-Loss Normalization Mechanics

In `core/execution/maker_execution_model.py`, `normalize_price_to_tick(price, policy=CONSERVATIVE, side=side, is_stop=True)` operates as follows:

| Position Direction | Stop Exit Order Side | Raw Stop Level Relative to Entry | Conservative Rounding Action | Normalized Stop Level | Stop Distance ($\Delta$) | Planned Gross Risk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **LONG Position** | SELL Order | Below Entry ($P_{\text{stop}} < P_{\text{entry}}$) | `ROUND_CEILING` (upward) | Moves **closer** to entry | $\Delta_{\text{norm}} \le \Delta_{\text{raw}}$ | Reduced or invariant |
| **SHORT Position** | BUY Order | Above Entry ($P_{\text{stop}} > P_{\text{entry}}$) | `ROUND_FLOOR` (downward) | Moves **closer** to entry | $\Delta_{\text{norm}} \le \Delta_{\text{raw}}$ | Reduced or invariant |

---

## 2. Risk Semantics & Trade-Off Analysis

### A. Premature Trigger Probability
Because `CONSERVATIVE` rounding shifts the trigger price closer to the entry price (and therefore closer to the current market price):
- **Premature Trigger Delta**: Up to 1 tick ($+0.10$ USD) closer to market.
- **Impact**: In tight-range conditions, a high-frequency wick could trigger the stop prematurely when the raw unrounded level would have survived.
- **Trade-off Rationale**: Protecting the capital risk budget takes absolute precedence over trade longevity.

### B. Risk Budget Re-verification (`audit_and_recalculate_stop_risk`)
1. Risk must be recalculated using the **normalized stop price**, including exchange commission fees on both entry and stop exit.
2. If an alternative rounding policy (e.g. `FLOOR` on long stop) is forced, the stop moves **away** from entry ($\Delta_{\text{norm}} > \Delta_{\text{raw}}$).
3. In that case, `risk_expansion_usd > 0`. If total risk exceeds `risk_budget`, the candidate is strictly rejected.

---

## 3. Order Types, Trigger Basis & Slippage Realities

> [!WARNING]
> **A STOP-LOSS PRICE NEVER GUARANTEES MAXIMUM LOSS**

1. **Order Type**: Delta Exchange India stop orders are typically `stop_market` or `stop_limit`.
   - `stop_market`: Upon trigger, dispatches a market order. In an illiquid book or market gap, the realized fill price may slip significantly worse than the trigger price.
   - `stop_limit`: Upon trigger, places a limit order at a specified limit price. If market gaps through, the order remains resting and unfilled, exposing capital to unhedged tail risk.
2. **Trigger Price Basis**:
   - `mark_price` trigger: Protects against orderbook manipulation and flash wicks, but during high volatility, mark price may lag last traded price.
   - `last_price` trigger: Responds immediately to executed trades, but vulnerable to micro-wicks.
