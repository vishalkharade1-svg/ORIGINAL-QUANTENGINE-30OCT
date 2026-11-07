# QuantEngine Phase 177 — Tick-Size Remediation Audit

## Executive Summary

Phase 177 resolves `FINDING-176-01` and closes `BLOCK-176-07`. The previous Phase 176 audit identified a discrepancy where `FeeScheduleProvenance.verified_contract` cited `tick=0.50` while the authoritative venue payload (`data/fixtures/delta/delta_mcp_public_products_20260925.json`) for Delta Exchange India BTCUSD (Product ID 84) recorded `tick_size = "0.1"`.

This audit traced the origin of the discrepancy, audited all tick handling through the codebase, implemented deterministic conservative rounding policies, and verified the complete order-validation and paper-execution paths.

---

## 1. Discrepancy Origin & Root Cause Analysis

### A. The Origin
- **Global Catalog (`observed_global_products_public_20260923.json`)**: Contained `BTCUSDT` with `tick_size = "0.5"`. In Phase 171 research defaults, this 0.50 value was copied into research models.
- **Delta India Testnet Product ID 84 (`delta_mcp_public_products_20260925.json`)**: Authoritatively specifies `tick_size = "0.1"`, `quoting_asset = "USD"`, `settling_asset = "USD"`, `contract_value = "0.001 BTC"`.
- **Finding**: While `FeeScheduleProvenance.verified_contract` in Phase 171–175 documented `tick=0.50`, the authoritative contract tick size on Delta India for `BTCUSD` is **0.10 USD**.

---

## 2. Complete Codebase Trace

Tick handling was traced across the entire pipeline:
1. **Strategy Entry & Target Prices**: Calculated from market levels and rounded to tick size.
2. **Stop Prices**: Computed from risk parameters and volatility buffers.
3. **Price Rounding & Normalization**: Implemented via `normalize_price_to_tick()`.
4. **Order Intent Construction**: Encapsulated in `OrderIntent` with contract specifications.
5. **Validation Boundary**: Checked via `validate_instrument_constraints()`.
6. **Paper Execution Engine**: Validated in `QueueAwarePaperExecutionEngine.submit_limit_post_only()` and `submit_order()`.
7. **Backtest Fills**: Simulated via `PostCostBacktester`.
8. **Adapter Requests**: Blocked in paper simulation via `assert_no_live_adapter_invocation()`.

---

## 3. Implemented Remediation

### A. FeeScheduleProvenance Correction
In `core/execution/maker_execution_model.py`:
- Updated `FeeScheduleProvenance.verified_contract` to `"BTCUSD (multiplier=0.001, tick=0.10, step=1)"`.
- Updated assumptions to cite authoritative Product ID 84 payload with `tick_size=0.10`.

### B. Authoritative InstrumentMetadata Factory
Created `InstrumentMetadata.for_btcusd()`:
```python
@classmethod
def for_btcusd(cls) -> "InstrumentMetadata":
    return cls(
        symbol="BTCUSD",
        tick_size=Decimal("0.10"),
        step_size=Decimal("1"),
        min_quantity=Decimal("1"),
        contract_multiplier=Decimal("0.001"),
        settlement_currency="USD",
        price_precision=1,
        qty_precision=0,
        min_notional=Decimal("1.00"),
    )
```

### C. Constraint Validation Hardening
In `validate_instrument_constraints()`:
- Default `tick_size` changed from 0.50 to `Decimal("0.10")`.
- Metadata conflict detection: if both `tick_size` argument and `meta.tick_size` are provided, any discrepancy fails closed immediately (`ValueError: Metadata conflict`).
- All price and quantity inputs must be finite positive numbers. Off-tick prices are rejected.

### D. Queue-Aware Paper Execution Engine
In `core/paper_trading/queue_aware_paper_engine.py`:
- `PaperOrder.tick_size` default changed from `Decimal("0.50")` to `Decimal("0.10")`.
- `submit_limit_post_only` default `tick_size` changed from `Decimal("0.50")` to `Decimal("0.10")`.

### E. Deterministic Conservative Rounding Policy
Implemented `normalize_price_to_tick()` with `TickRoundingPolicy`:
- `ROUND_HALF_UP`: Standard financial rounding.
- `FLOOR`: Always rounds down to nearest tick.
- `CEILING`: Always rounds up to nearest tick.
- `CONSERVATIVE`: Direction-aware and risk-preserving:
  - **BUY Limit Order**: Floors down (ensures trader never pays more than target limit).
  - **SELL Limit Order**: Ceilings up (ensures trader never sells for less than target limit).
  - **LONG Stop Loss**: Ceilings up (moves stop closer to entry, strictly preserving or reducing risk).
  - **SHORT Stop Loss**: Floors down (moves stop closer to entry, strictly preserving or reducing risk).

---

## 4. Test Verification Summary

The remediation is verified by `tests/test_phase177_tick_remediation.py`:
- Prices on 0.10 ticks (`82000.10`, `82000.20`, `82000.50`) pass validation.
- Prices between ticks (`82000.05`, `82000.15`) are rejected.
- Metadata conflict (passing 0.50 with 0.10 metadata) fails closed immediately.
- `CONSERVATIVE` rounding behavior verified for long/short entry limits and stop losses.
- Paper engine end-to-end order submission accepts 0.10 ticks and rejects off-tick orders.

**Status**: `BLOCK-176-07: RESOLVED`.
