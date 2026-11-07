# QuantEngine Phase 178 — End-to-End Tick-Size Enforcement Audit

## Executive Summary

Phase 178 independently audited the end-to-end order validation path and instrument metadata resolution for Delta Exchange India BTCUSD (Product ID 84).

---

## 1. Trace of Tick Handling Through Complete Pipeline

```
InstrumentMetadata.for_btcusd() [tick=0.10, mult=0.001]
       │
       ▼
Strategy Price Level Generation (Entry, Target, Stop)
       │
       ▼
Deterministic Price Normalization (normalize_price_to_tick)
       │
       ▼
Risk Engine & Stop-Loss Budget Verification
       │
       ▼
Friction Hurdle Gate (FrictionHurdleGate.evaluate)
       │
       ▼
Executable Order Validation (validate_instrument_constraints)
       │
       ▼
Queue-Aware Paper Execution Engine (submit_limit_post_only)
       │
       ▼
Fill Accounting & Settlement Reconciliation
```

---

## 2. Invariant & Conflict Defenses

1. **Authoritative Specification Enforcement**: Product ID 84 uses `tick_size = Decimal("0.10")`, `contract_multiplier = Decimal("0.001")`, `quantity_step = Decimal("1")`.
2. **Conflict Immunity**: If legacy BTCUSDT Global catalog metadata (`tick_size = 0.50`) is passed against authoritative metadata, `validate_instrument_constraints()` and `normalize_price_to_tick()` fail closed immediately (`ValueError: Metadata conflict`).
3. **Execution Boundary**: Paper order creation rejects any off-tick price (e.g. `81950.05` or `81950.15`), transitioning order directly to `REJECTED_CONSTRAINTS`.
4. **Adapter Isolation**: `assert_no_live_adapter_invocation()` verified across all submission paths.
