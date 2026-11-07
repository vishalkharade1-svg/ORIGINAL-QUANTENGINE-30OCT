# QuantEngine Phase 3 — Market Structure Report

## First causal audit increment

Added `audit_confirmed_swing_prefixes()`, a fresh-engine prefix-invariance
audit for `SwingEngine`. It compares only pivots that have passed their
right-side confirmation horizon, so pending tail bars are not falsely treated
as causal observations. This is diagnostic tooling and does not alter the
strategy pipeline.

Next: extend the same audit to structure/BOS/CHOCH and impose explicit data
sufficiency gates at feature consumers.

## Phase 4 semantic boundary started

`score` and its compatibility `confidence` bucket are heuristic ranking
values, not calibrated probabilities. `SetupCandidate` and `TradeSetup` now
carry a separate `calibrated_probability`, defaulting to `None` until a
provenance-pinned calibration model exists.

## Phase 5 data-risk precondition started

`evaluate_market_data()` is a pure fail-closed precondition that rejects
missing, stale, gapped/unknown, and missing-volume authoritative state with a
machine-readable reason. It is not wired into the legacy risk engine until
the normalized transport replaces ticker-mark candles.
