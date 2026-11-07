STATUS: INDEPENDENTLY_VERIFIED

# Phase 27 Trailing Stop‑Loss Specification

## Supported trailing method
- **R_DISTANCE** – fixed distance expressed in R units (the only method currently implemented and tested).

## Configuration fields (Trade & Policy)

| Field | Default | Description |
|-------|---------|-------------|
| `trailing_enabled` | `True` (when policy has `trailing_enabled=True`) | Turn trailing on/off for the trade. |
| `trailing_activation_r` | `1.0` | Must achieve 1 R favourable move before the trail activates. |
| `trailing_distance_r` | `0.5` | Distance to trail behind the peak/favourable price, in R units. |
| `trailing_method` | `"R_DISTANCE"` | Chosen trailing method (only `R_DISTANCE` is supported). |
| `trailing_step_r` | `0.0` | Optional minimum R‑distance between successive updates; `0.0` disables step gating. |

## Invariants

- **Long positions:** stop may only move **upward** (never downward once tightened).
- **Short positions:** stop may only move **downward** (never upward once tightened).
- **Monotonic tightening:** each accepted update must be strictly more protective than the previous stop.
- **Tick‑rounding:** `round_stop_to_tick(price, tick_size, bullish)` uses `ECONOMIC_TICK_SIZE = 0.5`; long stops round DOWN, short stops round UP.
- **No look‑ahead:** an update may use only market data available at the decision timestamp (candle close / bar timestamp).
- **Same‑candle ambiguity:** conservative SL‑first rule – the initial stop is checked for a hit before any trailing update is applied on the same bar.
- **Gap‑through‑stop:** if the candle `open` is present and lies beyond the stop, the fill price is taken as `open` (conservative); otherwise the stop price itself is used.
- **Stop cannot widen** the original risk distance.

## Update algorithm (deterministic)

1. **Peak / favour price** is updated from the new candle’s close (long: `max(prev_peak, close)`; short: `min(prev_peak, close)`).
2. **Activation check:** `favourable_r = (close - entry) / initial_risk` (long) or `(entry - close) / initial_risk` (short). If `favourable_r >= activation_r`, the trail is considered active.
3. **Raw candidate stop:** `candidate = (close - distance_r * initial_risk)` for long, `(close + distance_r * initial_risk)` for short.
4. **Tick rounding:** `new_stop = round_stop_to_tick(candidate, tick_size, bullish)`.
5. **Monotonic check:** `new_stop > current_stop` for long, `new_stop < current_stop` for short; otherwise reject.
6. **Step gating (if `step_r > 0`):** `candidate - current_stop >= step_r * initial_risk` (long) or `current_stop - candidate >= step_r * initial_risk` (short); otherwise reject.
7. **Too‑close check:** `new_stop >= close` (long) or `new_stop <= close` (short) → reject with `STOP_AT_OR_THROUGH_PRICE`.
8. **Accept** the update; set `trailing_peak_price`, `trailing_updates`, append to `trailing_history` (capped at 500 entries).

## Interaction with fixed target

- The fixed target remains unchanged while the stop trails.
- If the target price is hit first, the trade closes at target; the trailing stop is cancelled.
- Partial fills preserve protection for the remaining quantity.

## Persistence & restart recovery

- `TradeSimulator.export_trade_state()` returns a JSON‑serialisable dict of the current trade (including all `trailing_*` fields).
- `TradeSimulator.restore_trade_state(raw)` validates the dict against the `Trade` dataclass fields, ensures status is `OPEN`, and restores the trade.
- `PaperTradingEngine._load_state()` reads a JSON file (`quantengine.paper_state.v1`), restores `AccountState` and (if present) the trade via `restore_trade_state`.
- `PaperTradingEngine._persist_state()` atomically writes the combined account‑+‑trade JSON to `state_path`.
- On restart the most protective confirmed stop is recovered; no trade is double‑filled.

## API / Monitoring exposure

- `risk_policy_get()` returns a snapshot that now includes `trailing_method` and `trailing_step_r` alongside the existing fields.
- `risk_policy_set(body)` accepts the two new fields; unknown fields are rejected.

## Test coverage (existing)

- `tests/test_trailing_stop_phase27.py` – primitive functions (tick rounding, evaluate TrailingStopConfig).
- Focused suite (`test_trading_policy.py`, `test_trade_simulator.py`, `test_paper_trading.py`, `test_api_server_9pf.py`) validates that trailing does not break RR bounds or PnL calculations.
- No test currently asserts that a trailing stop loosens or uses future data; such assertions would fail the monotonic check.

## Known limitations

- Only the `R_DISTANCE` method is supported; other proposed methods (ATR‑based, swing‑based) are out of scope for this phase.
- Step gating (`trailing_step_r > 0`) is coded but not exercised by the existing test data; it is available for future strategy configuration.
- The trailing stop is **simulated**; the broker layer explicitly refuses trailing‑stop execution on live venues with a clear message (`"trailing-stop execution contract unavailable"`).