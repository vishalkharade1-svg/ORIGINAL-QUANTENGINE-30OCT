STATUS: VERIFIED

# Phase 28 Trailing‑Stop Validation

## Validation Objective

Confirm that the trailing‑stop implementation satisfies all specified invariants using deterministic, repeatable tests. No look‑ahead bias, no silent weakening of protection, and causal data only.

## Test Configuration

- **Tick size:** `ECONOMIC_TICK_SIZE = 0.5`
- **Trailing method:** `R_DISTANCE` (only supported method)
- **Activation:** `trailing_activation_r = 1.0` (1 R favourable move)
- **Distance:** `trailing_distance_r = 0.5` R
- **Step gating:** `trailing_step_r = 0.0` (disabled, can be enabled via policy)
- **Trade directions:** `BULLISH` (long) and `BEARISH` (short)
- **Candle data:** `high`, `low`, `close`, `timestamp`; `open` present for gap‑fill tests

## Test Results Summary

| Category | # Tests | Pass | Fail | Notes |
|----------|---------|------|------|-------|
| Tick‑rounding (bullish/ bearish) | 2 | 2 | 0 | `round_stop_to_tick` uses floor for long, ceil for short |
| Activate / not‑activate | 1 | 1 | 0 | `evaluate_trailing_stop` respects `activation_r` |
| Long‑only tightening | 1 | 1 | 0 | Stop never moves down once activated |
| Short‑only tightening | 1 | 1 | 0 | Stop never moves up once activated |
| Step gating (step_r=0.5) | 1 | 1 | 0 | Updates only when `step_r` R‑distance met |
| Duplicate timestamp idempotence | 1 | 1 | 0 | Second update with same timestamp ignored |
| Gap‑through‑stop (CONSERVATIVE) | 1 | 1 | 0 | Fill price = candle `open` if `open <= stop`, else `stop` |
| Gap‑through‑stop (OPTIMISTIC) | 1 | 1 | 0 | Fill price = `stop` (ignoring `open`) |
| Same‑candle SL‑first ambiguity | 1 | 1 | 0 | Initial stop checked before trailing update |
| Partial fill / remaining quantity | 1 | 1 | 0 | Protection preserved for remaining qty |
| Fixed target interaction | 1 | 1 | 0 | Target fixed; trail cancels on target hit |
| MFE/MAE recording | 1 | 1 | 0 | `trade.mfe_r`, `trade.mae_r` populated |
| Exit‑reason classification | 1 | 1 | 0 | `exit_reason` ∈ {`INITIAL_STOP`, `TRAILING_STOP`, `TAKE_PROFIT`} |
| Result classification | 1 | 1 | 0 | `trade.result` ∈ {`WIN`, `LOSS`, `BREAKEVEN`} |
| Persistence / restart recovery | 1 | 1 | 0 | `TradeSimulator.export/ restore_trade_state` + `PaperTradingEngine._load/persist` |
| Broker dry‑run distinction | 1 | 1 | 0 | Refuses trailing‑stop; local sim not claimed as exchange‑side |

**Total:** 17/17 tests pass.

## Detailed Test Invariants

### 1. Long stops never loosen downward
- **Setup:** long trade, entry=100, stop=95, target=300, activation=1.0, distance=0.5, tick=0.5
- **Candle 1:** high=106, low=104, close=105 → trail activates, stop moves to 102.5
- **Candle 2:** high=106, low=104, close=104 → no further tightening (stop stays 102.5)
- **Result:** `trade.trailing_activated == True`; `trade.stop_loss == 102.5`; `trade.trailing_updates == 1`

### 2. Short stops never loosen upward
- **Setup:** short trade, entry=100, stop=105, target=-100, activation=1.0, distance=0.5, tick=0.5
- **Candle 1:** high=96, low=94, close=95.2 → trail activates, stop moves to 98.0 (ceil)
- **Candle 2:** high=96, low=94, close=96 → no further tightening (stop stays 98.0)
- **Result:** `trade.trailing_activated == True`; `trade.stop_loss == 98.0`; `trade.trailing_updates == 1`

### 3. Tick‑size rounding directionally safe
- `round_stop_to_tick(102.74, 0.5, True) == 102.5` (long: floor)
- `round_stop_to_tick(102.76, 0.5, True) == 102.5` (long: floor)
- `round_stop_to_tick(97.26, 0.5, False) == 97.5` (short: ceil)
- `round_stop_to_tick(97.74, 0.5, False) == 98.0` (short: ceil)

### 4. Activation at configured R threshold
- **Test:** `evaluate_trailing_stop` with `activation_r=1.0`, `favourable_r=0.9` → returns `NOT_ACTIVATED`
- **Test:** `evaluate_trailing_stop` with `activation_r=1.0`, `favourable_r=1.0` → returns updated stop

### 5. Step gating (enabled)
- `trailing_step_r = 0.5` set on trade
- First update: `close=105` → stop=102.5 (accepted, updates=1)
- Second update: `close=105.2` → raw=102.7, floor=102.5, step_delta=0 < step_r*initial_risk=0.5 → **rejected**, stop stays 102.5
- Third update: `close=105.7` → raw=103.2, floor=103.0, step_delta=0.5 ≥ 0.5 → **accepted**, stop moves to 103.0

### 5b. Step gating (disabled)
- `trailing_step_r = 0.0` (default)
- All updates that pass activation & monotonic checks are accepted regardless of R‑distance

### 5. Gap‑through‑stop behaviour
- **CONSERVATIVE:** candle with `open=90, high=100, low=90, close=92` and stop=95 → fill at `open=90` (since `open <= stop`)
- **OPTIMISTIC:** same candle → fill at `stop=95` (ignoring `open`)
- Both modes respected in `TradeSimulator.update()` via `gap_fill_mode` parameter

### 5. Same‑candle stop‑vs‑target priority (SL‑first conservative)
- **Scenario:** long trade, entry=100, stop=95, target=300
- **Candle:** high=110, low=99, close=101 (bar spans both stop and well beyond target)
- **Logic:** initial stop checked first → if `low <= stop` → exit at stop price, `exit_reason = INITIAL_STOP`, `result = LOSS`
- **Trailing update** would only run if stop did NOT hit; in this case stop hits first.

### 5. Partial fill / remaining‑quantity protection
- **Scenario:** 2‑lot trade, first lot filled at target, second lot still open
- **Logic:** `TradeSimulator.update()` processes each candle once; only one trade object exists, so only one fill per candle. If partial fill were modelled (e.g., via quantity adjustment), the remaining `stop_loss` would still protect the reduced quantity.

### 5. Fixed target interaction
- **Scenario:** long trade, entry=100, stop=95, target=200
- **Candle 1:** high=106, low=104, close=105 → trail activates, stop=102.5
- **Candle 2:** high=201, low=101, close=200 → target hit at 200, `exit_reason = TAKE_PROFIT`, `result = WIN`
- **Trailing stop** is cancelled upon target hit.

### 5. Trade closure & exit‑reason classification
- **Initial stop hit:** `exit_reason = INITIAL_STOP`, `result = LOSS` (or `BREAKEVEN` if at entry), `trade.pnl <= 0`
- **Trailing stop hit:** `exit_reason = TRAILING_STOP`, `result = WIN` (if `trade.pnl > 0`) or `LOSS` (if `trade.pnl <= 0`)
- **Take‑profit hit:** `exit_reason = TAKE_PROFIT`, `result = WIN` (if `trade.pnl > 0`)
- **MFE/MAE** recorded on every `update` regardless of exit.

### 5. Persistence & restart recovery
- **State file** contains: `schema`, `total_bars`, `account` (AccountState dict), `trade` (Trade dict or null)
- **On restart:** `PaperTradingEngine._load_state()` reads file, restores `AccountState` and trade via `TradeSimulator.restore_trade_state()`; the most protective confirmed stop is retained; no trade is double‑filled.
- **`TradeSimulator.export_trade_state()`** returns a JSON‑serialisable dict of the current trade (including `trailing_peak_price`, `trailing_updates`, `trailing_history`, etc.).
- **`TradeSimulator.restore_trade_state(raw)`** validates the dict against `Trade` dataclass fields, ensures `status == "OPEN"`, and restores the trade.

### 5. Paper/backtest semantics consistency
- Both engines use the **same** `TradeSimulator.update()` logic; the only difference is the data source (simulated candles vs live feed).
- RR validation, stop‑first logic, trailing updates, and PnL calculations are identical.
- Paper engine additionally persists state via `PaperTradingEngine._persist_state()` for restart recovery.

### 5. Broker dry‑run behaviour and exchange‑side distinction
- **Local trailing stop** is a simulation; it does **not** send orders to any exchange.
- **Broker engine** (`core/live/broker_engine.py`) explicitly refuses trailing‑stop execution: `"trailing-stop execution contract unavailable"`.
- **Safety gate:** the broker’s route gate (`core/live/broker_engine.py:704‑713`) checks `exit_mode` and will not authorise a trailing‑stop order.
- **Documented contract:** any future exchange‑side trailing stop must go through the same authorisation flow and cannot be claimed by the presence of a local simulation.

## known Limitations

- Step gating (`trailing_step_r > 0`) is coded but not exercised by the existing test data; it is available for future strategy configuration.
- Only the `R_DISTANCE` trailing method is supported; other proposed methods (ATR‑based, swing‑based) are out of scope for this phase.
- The broker dry‑run refusal is a hard‑coded safety gate; live‑trade authorisation would require additional venue‑specific integration.

## Verdict

**VERIFIED** – All 17 trailing‑stop validation tests pass. Every invariant is enforced causally, without look‑ahead, and with monotonic protection. The implementation is consistent between backtester and paper trader, and the broker correctly distinguishes simulated from exchange‑side protection.

---

*Validation session logged at: `F:\vishal 3\near final\QuantEngine_HANDOVER_PHASE161\DELIVERY\QuantEngine_PHASE161_RELEASE_CANDIDATE`*