# Phase 207 — Real-time orchestrator market-data gate configuration

## Change

`RealTimeEngine` now accepts `market_data_max_age_seconds` and an optional
`market_data_now_provider`, validates configuration at construction, and passes
both values to every newly created `PaperRuntime`. The age threshold remains
opt-in: `None` preserves the legacy path. A configured threshold activates the
existing fail-closed `PaperRuntime` candle gate. The injectable clock enables
repeatable tests.

## Safety boundary

This change only configures the paper runtime. It does not enable live trading,
call a broker API, or place/cancel orders. It does not establish feed authenticity,
exchange-session correctness, completeness, or strategy profitability. Existing
explicit wrappers for other paper entry points remain opt-in and unchanged.

## Configuration example

```python
engine = RealTimeEngine(
    universe_manager=universe_manager,
    market_data_max_age_seconds=90,
)
```

The threshold must be finite and non-negative. Omit it to retain legacy behavior.

## Verification scope

The Phase 207 tests check invalid configuration, clock-provider type validation,
propagation into each newly constructed `PaperRuntime`, and the disabled default.
Focused test results are recorded in the detached release record. The full test
suite is not represented as passing unless it is run to completion.
