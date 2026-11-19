# Phase 206 — Paper Entry-Point Quality Gates

## Goal

Extend Phase 205 market-data quality checks to additional paper-only entry points while preserving frozen source files and keeping live execution untouched.

## Implementation

Added `core/runtime/gated_paper_entrypoints.py` with two explicit opt-in wrappers:

- `GatedPaperTradingEngine`: checks a candle before delegating to the existing `PaperTradingEngine.run_candle`; rejected candles do not reset pipeline context, call the strategy pipeline, run simulated fills, update positions, or increment processed bars.
- `GatedVerifiedPaperRuntime`: checks a candle after verified transport delivery but before the in-memory `PaperFillSink`; it rejects candles outside the configured symbol set and rejects stale, future-dated, forming, malformed, or symbol-inconsistent candles.

Both wrappers require a finite, non-negative `market_data_max_age_seconds` setting. Clock-provider failures fail closed. Decisions use stable reason codes and do not record raw payloads or exception strings. The base classes remain unchanged; callers must opt into the wrapper classes. Existing `PaperRuntime` continues to provide its Phase 205 opt-in gate.

## Verification

- Phase 206 wrapper tests: stale data, symbol mismatch, accepted candle, and clock failure.
- Regression selections: Phase 205 quality-gate tests, verified runtime parity tests, PaperTradingEngine tests, and paper runtime boundary certification.
- The combined focused selection passed: 46 tests.
- Strict manifest verification, secret scan, Python compilation, and archive integrity are checked by the release workflow.

## Limitations / open work

- This is opt-in integration, not a forced default across every existing paper path. Use the gated wrapper in place of `PaperTradingEngine` or `VerifiedPaperRuntime` to enable it.
- The `RealTimeEngine` orchestrator still constructs the existing `PaperRuntime` without exposing a top-level freshness setting. That config plumbing remains a follow-up; direct `PaperRuntime` construction already supports `market_data_max_age_seconds`.
- The gate validates structure, symbol identity, and age; it does not prove feed authenticity, exchange session correctness, completeness, or profitability.
- No live execution code is changed, no external API call was made, and no exchange order was submitted.
- Overall release status remains HOLD. Full-suite completion and previously reported frozen strategy-digest failures remain open. NSE/Sensex and forex venue adapters are not implemented/certified by this phase.
