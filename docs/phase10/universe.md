# Universe — Real Eligibility Cascade

> Phase 10 integrates real `InstrumentRegistry`/`UniverseManager`/`MarketUniverse` + `LiquidityProvider`/`HistoryProvider`.

## Discovery

- `ProductClient` → `DeltaREST.get("/v2/products")` → 388 products (12 perps, 6 spot, 6 binary each, 358 options)
- `DeltaContractLoader` → `DeltaMapper` → `Instrument` (exchange:instrument_id,tick_size,quantity_step)

## Registry

- `InstrumentRegistry` — `upsert` + `mark_present` + `ACTIVE` / `NEWLY_LISTED` state machine, 2 passes to graduate

## Eligibility Cascade (for each candidate symbol)

```
instrument exists
→ instrument active (not delisted/disabled/unlisted)
→ market type supported (perpetual_futures/spot, options currently not traded)
→ liquidity (DeltaLiquidityProvider: turnover_usd >= MIN_QUOTE_VOLUME_24H, None means no numeric bound but requires measurable)
→ history (DeltaHistoryProvider: candles >= MIN_HISTORY_BARS)
→ data availability (DATA_AVAILABLE vs DATA_UNAVAILABLE)
→ risk eligibility (MAX_PORTFOLIO_RISK etc.)
→ SUBSCRIBE / REJECT with deterministic reason
```

Rejection reasons: `INVALID_INSTRUMENT`, `INACTIVE`, `INSUFFICIENT_LIQUIDITY`, `INSUFFICIENT_HISTORY`, `UNSUPPORTED_MARKET`, `MISSING_DATA`, `RISK_INELIGIBLE`, `NOT_CONFIRMED` (fresh registry, needs 2nd pass).

## Current Soak

- 50 symbols requested → 50 subscriptions LIVE (subscription layer PASS), 0 crashes, p99 0.23ms
- Engine runtimes 0 in dummy-manager soak → now attempted with real `UniverseManager` (with `InstrumentRegistry` primed, `DeltaContract.key` fallback documented)
- Full `UniverseManager` + real providers to be validated in next 120s soak on host
