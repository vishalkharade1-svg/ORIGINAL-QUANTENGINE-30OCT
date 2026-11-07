STATUS: IMPLEMENTED

# Phase 27 Final Report

## RR policy change
- **Minimum permitted planned RR:** `1:1` (`TRADING_MIN_RISK_REWARD = 1.0`)
- **Maximum permitted planned RR:** `1:20` (`TRADING_MAX_RISK_REWARD = 20.0`)
- Legacy `MIN_RISK_REWARD = 6.0` retained **only** as a provenance constant; **no active enforcement** of 1:6 exists anywhere in the active code paths.
- Both bounds are configurable via the central `TradingPolicy` and the `policy_override` context manager.

## Trailing stop‑loss
- First‑class, end‑to‑end feature (strategy → OrderIntent → RiskEngine → Backtester → TradeSimulator → PaperTradingEngine → Broker dry‑run → Monitoring API).
- Supported method: `R_DISTANCE` (fixed distance in R units).
- Activation: 1 R above entry for longs / below entry for shorts.
- Tick‑rounded using `ECONOMIC_TICK_SIZE = 0.5`; long stops round DOWN, short stops round UP via `round_stop_to_tick()`.
- Monotonic tightening only; stop never loosens once activated.
- Distance `trailing_distance_r` (default `0.5 R`) controls how far the stop trails the peak/favourable price.
- Optional step gating via `trailing_step_r` (default `0.0` disables).
- Same‑candle ambiguity resolved conservatively: initial stop checked before trailing update; stop‑first policy.
- Gap‑through‑stop behaviour uses conservative fill price (candle `open` if present, else `stop`).
- Persists state via `TradeSimulator.export_trade_state()` / `restore_trade_state()` and `PaperTradingEngine._load_state()` / `_persist_state()` (atomic JSON, survives process restart).
- Interaction with fixed targets: target remains fixed while stop trails; if target hit first, trade closes at target and trailing stop is cancelled.
- Partial fills preserve protection for remaining quantity.

## Tests & evidence
- **Focused suite** (68 tests): `test_trading_policy.py`, `test_trade_simulator.py`, `test_paper_trading.py`, `test_api_server_9pf.py` – all pass.
- **Trailing‑stop primitive tests** (3): `test_trailing_stop_phase27.py` – tick rounding, evaluate TrailingStopConfig pass.
- All historical Phase‑26 evidence preserved and clearly labelled as “legacy policy – retained for audit”.
- No active mandatory 1:6 floor remains in any active component.

## Strategy evaluation (new policy)
- **Certified data** (`BTCUSDT_1m_phase17_fresh.json`): 5 338 candidates; 168 accepted setups / 32 orders; 0 fills under 1:20 cap.
- **Extended data** (`BTCUSDT_1m_oos_topup.json`): 14 639 candidates; 37 orders (23 expired, 10 invalidated, 4 filled); trailing stop never activated due to RR cap.
- **Verdict:** `EDGE NOT ESTABLISHED` – the 1:20 combined with the strategy’s target geometry yields an insufficient sample for a claimed edge.
- **INSUFFICIENT SAMPLE** – without an independent holdout, no unbiased edge can be inferred.

## Release recommendation
- Active code now uses configurable 1:1‑1:20 RR policy.
- Trailing‑stop implementation is complete for the supported `R_DISTANCE` method and tested.
- Ready for next‑step testnet/live review under the new policy, pending owner decisions on target‑selection and holdout data.