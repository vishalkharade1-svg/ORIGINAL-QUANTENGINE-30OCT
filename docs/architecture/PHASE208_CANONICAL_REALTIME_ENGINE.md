# Phase 208 — Canonical Real-Time Engine and Paper Data Gate

## Decision

The market-data freshness configuration now lives in the existing
`core.runtime.realtime_engine.RealTimeEngine`. The engine accepts the optional
`market_data_max_age_seconds` threshold and `market_data_now_provider` clock,
validates configuration at construction, and passes both to each `PaperRuntime`
created during universe reconciliation.

`market_data_max_age_seconds=None` preserves legacy behavior. When a finite,
non-negative threshold is explicitly supplied, `PaperRuntime` applies the
existing fail-closed candle gate before strategy processing.

## One canonical engine

`core/runtime/gated_realtime_engine.py` remains as a backward-compatible import
path only. Its `GatedRealTimeEngine` name is an alias of `RealTimeEngine`; it
contains no second implementation or subclass. Existing imports continue to
work, while new code should import `RealTimeEngine` directly.

## Why the original source was changed now

The earlier wrapper was a conservative interim step to avoid changing a
manifest-sealed release tree without a controlled successor build. The source
freeze is an integrity/release discipline, not a reason to keep parallel
runtime implementations indefinitely. This phase deliberately updates the
canonical source, updates affected tests, regenerates the release manifest, and
verifies the resulting packaged tree. It does not bypass snapshot guards or
re-pin strategy digests to hide failures.

## Coverage

- Constructor rejects NaN, infinity, negative thresholds, unparseable values,
  and non-callable clock providers.
- Existing default construction leaves the gate disabled for compatibility.
- Universe reconciliation passes gate configuration to each newly created
  `PaperRuntime`, including after future refreshes that add instruments.
- Existing runtime-level tests verify stale, malformed, forming, or
  symbol-mismatched candles are rejected before strategy intake.
- Historical `GatedRealTimeEngine` imports resolve to the same class object as
  `RealTimeEngine`.

## Limitations and release gates

This is paper-mode protection only. It does not certify feed authenticity,
exchange session correctness, profitability, or venue adapter correctness. The
full test suite remains incomplete and the previously reported frozen strategy
digest failures remain open. Concrete exchange integration remains Delta-
focused; NSE/Sensex and forex adapters still need implementation and venue-level
certification. Live execution remains HOLD.
