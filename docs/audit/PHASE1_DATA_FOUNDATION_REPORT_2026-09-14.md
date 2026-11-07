# QuantEngine Phase 1 — Data Foundation Report (Increment 1)

## Changed

- Added `data/delta/market_events.py`: strict normalizers for documented
  Delta public `trades` and `candlestick_<resolution>` frame shapes.
- Added `data/delta/market_state_store.py`: one in-memory authoritative
  state record per `(venue, instrument)` consuming only normalized events.
- Added strict documented `ob_l1` and `ob_l2` snapshot normalizers.  They
  retain raw book facts only; no order-book imbalance is inferred.
- Added `DeltaPublicEventStream`, a raw-frame ingress that deterministically
  dispatches only recognized documented frames into the state store and
  isolates malformed, old, and unhandled frames.
- Added a causal `CandleFinalityTracker`: with Global-captured `cst`, it
  emits a prior candle only after a later candle start is observed.  It never
  guesses closure from wall-clock time.
- Corrected same-candle update handling: a later publish timestamp for the
  same `cst` replaces the forming snapshot; a later `cst` then confirms that
  final observed value.
- Added `ClosedCandleRouter`, an explicit boundary that delivers only causal
  finality-tracker outputs; forming and non-candle events are suppressed.
- Added `CandleContinuityTracker`; a forward gap in observed candle starts is
  held as `DATA_GAP_UNREPAIRED` and never interpolated.
- Propagated the same gap status into `AuthoritativeMarketState.data_quality`,
  so data-quality monitoring and dispatch share one status.
- Added a bounded `NormalizedEventStore`; only accepted typed public events
  are journaled with a monotonic process-local ordinal.
- Added explicit market-data capability gates: traded OHLCV/volume can be
  available when evidenced, while signed delta, footprint and snapshot-only
  order-book imbalance remain `UNAVAILABLE`.
- Added a fail-closed normalized-to-runtime candle bridge. It converts only
  causally closed, continuous traded candles at the expected resolution with
  an exchange-reported volume; mark and unknown-volume data cannot become a
  strategy candle.
- Added `DeltaRuntimeStreamAdapter`, a transport-agnostic callback adapter
  which composes normalization, finality, continuity and the runtime bridge.
  It isolates a consumer exception instead of allowing it to kill ingress.
- Added a deterministic `VerifiedCandleSubscription` payload and symbol
  demultiplexer for the documented public `candlestick_<resolution>` channel.
  It is a testable transport-migration seam, not a socket/runtime switch.
- Added an opt-in, fsynced, append-only normalized-event journal. Its strict
  recovery read rejects partial or non-contiguous records; replay is still
  deliberately not wired into runtime.
- Added deterministic journal-to-state replay. It rebuilds authoritative
  market state only and never forwards historical events to strategy/runtime
  callbacks; old updates stay visible in its replay report.
- Added captured-schema and state tests.
- Added `docs/integrations/DELTA_PUBLIC_MARKET_DATA_CONTRACT.md` defining
  evidence, unavailable facts, and the production wiring gate.

## Why

The audit proved the old live transport creates candles from ticker marks and
labels them with zero volume.  This increment establishes a separate, typed
data boundary that cannot convert missing volume into zero, mark price into
last trade, or maker/taker role into signed order flow.

## Tests

| Command | Result |
|---|---|
| `python -m pytest tests/test_runtime_candle_bridge_phase1.py tests/test_market_data_capabilities_phase1.py tests/test_candle_continuity_phase1.py tests/test_closed_candle_router_phase1.py tests/test_candle_finality_phase1.py tests/test_delta_market_events_phase1.py tests/test_market_state_store_phase1.py tests/test_delta_public_event_stream_phase1.py tests/test_normalized_event_store_phase1.py tests/test_timestamp_9q.py tests/test_stage123_operational.py tests/test_security_12.py tests/test_live_block_11.py -q` | **134 passed**; one non-fatal `.pytest_cache` permission warning |
| `python -m pytest tests/test_runtime_stream_adapter_phase1.py tests/test_runtime_candle_bridge_phase1.py tests/test_market_data_capabilities_phase1.py tests/test_candle_continuity_phase1.py tests/test_closed_candle_router_phase1.py tests/test_candle_finality_phase1.py tests/test_delta_market_events_phase1.py tests/test_market_state_store_phase1.py tests/test_delta_public_event_stream_phase1.py tests/test_normalized_event_store_phase1.py -q` | **39 passed**; one non-fatal `.pytest_cache` permission warning |
| `python -m pytest tests/test_verified_candle_subscription_phase1.py tests/test_runtime_stream_adapter_phase1.py tests/test_runtime_candle_bridge_phase1.py tests/test_market_data_capabilities_phase1.py tests/test_candle_continuity_phase1.py tests/test_closed_candle_router_phase1.py tests/test_candle_finality_phase1.py tests/test_delta_market_events_phase1.py tests/test_market_state_store_phase1.py tests/test_delta_public_event_stream_phase1.py tests/test_normalized_event_store_phase1.py -q` | **43 passed**; one non-fatal `.pytest_cache` permission warning |
| `python -m pytest tests/test_normalized_event_journal_phase1.py tests/test_verified_candle_subscription_phase1.py tests/test_runtime_stream_adapter_phase1.py tests/test_runtime_candle_bridge_phase1.py tests/test_market_data_capabilities_phase1.py tests/test_candle_continuity_phase1.py tests/test_closed_candle_router_phase1.py tests/test_candle_finality_phase1.py tests/test_delta_market_events_phase1.py tests/test_market_state_store_phase1.py tests/test_delta_public_event_stream_phase1.py tests/test_normalized_event_store_phase1.py -q` | **45 passed**; one non-fatal `.pytest_cache` permission warning |
| `python -m pytest tests/test_event_replay_phase1.py tests/test_normalized_event_journal_phase1.py tests/test_verified_candle_subscription_phase1.py tests/test_runtime_stream_adapter_phase1.py tests/test_runtime_candle_bridge_phase1.py tests/test_market_data_capabilities_phase1.py tests/test_candle_continuity_phase1.py tests/test_closed_candle_router_phase1.py tests/test_candle_finality_phase1.py tests/test_delta_market_events_phase1.py tests/test_market_state_store_phase1.py tests/test_delta_public_event_stream_phase1.py tests/test_normalized_event_store_phase1.py -q` | **47 passed**; one non-fatal `.pytest_cache` permission warning |
| `.venv\\Scripts\\python -m compileall -q data/delta/market_events.py data/delta/market_state_store.py tests/test_delta_market_events_phase1.py tests/test_market_state_store_phase1.py` | **PASS** |
| `python scripts/security/scan_secrets.py` | `SECRET_SCAN_PASS` |
| `git diff --check` | **PASS** |

### Read-only endpoint capture

On 2026-09-14 a credential-free capture against
`wss://public-socket.delta.exchange` accepted subscriptions for `trades`,
`candlestick_1m`, `ob_l1`, and `ob_l2` on `BTCUSDT`.  Within the bounded
capture windows, all four channels arrived.  The compact field contracts
matched `trades` (`p/r/s/sy/t/ts`), candles (`o/h/l/c/res/sy/ts/v`) and book
frames (`ap/as/bp/bs/sy/ts` and `a/b/sy/ts`).  The Global candle additionally
carried `cst`, retained by the normalizer as candle-start time separately
from publish time. This is **PARTIALLY VERIFIED**: it does not verify a
candle-close/finality flag, sequence semantics, or production stability.

## Remaining

- The old ticker-to-candle runtime has not been switched.  Switching it now
  would require guessing the target Global WebSocket frame/close semantics,
  which Phase 1 forbids.
- `NormalizedEventJournal` and deterministic state-only replay are available,
  but they are not yet wired to ingress and have no checkpoint/restart
  orchestration path.
- L1/L2 snapshots are normalized, but incremental book reconstruction,
  sequence verification, and order-book imbalance remain unavailable.
- The strict runtime candle bridge is tested but intentionally not wired into
  the legacy ticker transport. Production transport migration still needs
  exact-endpoint reconnect/resubscribe captures and a controlled PAPER-mode
  end-to-end proof.
- `scripts/capture_delta_public_frames.py` provides a repeatable, read-only
  capture probe.  It must be run against the target venue/symbol before the
  corresponding channel is made a runtime dependency.
- P0-03 credential revocation and historical remediation remain open.

## Risks

- The new state is intentionally in-memory only; it is not restart durable.
- The normalizer uses float values to match existing repository math.  A
  future instrument/accounting phase must decide whether precision-critical
  boundaries need decimal/tick-native representation.

## Architecture impact

New dependency direction: raw frame -> validated normalized event ->
authoritative data state.  It is isolated from strategy and execution; no
strategy can treat it as a signal and no exchange write path changed.

## Verification status

- Captured-schema normalization and state behaviour: **VERIFIED**.
- Exact production endpoint/channel/schema/finality behaviour: **EXTERNAL
  VERIFICATION REQUIRED**.
- Trading use of this data: **NOT YET INTEGRATED**.
