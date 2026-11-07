# Delta Public Market-Data Contract

## Status

**PARTIALLY VERIFIED.** The compact public-frame schemas below were
implemented against Delta's official documentation on 2026-09-14.  They have
only captured-schema tests; the repository's deployed Global endpoint and
its production traffic remain **EXTERNAL VERIFICATION REQUIRED**.

Official source: [Delta Exchange API documentation](https://docs.delta.exchange/).

## Normalized channels

| Channel | Documented facts used | Normalized event | Explicitly unavailable |
|---|---|---|---|
| `trades` | price `p`, size `s`, buyer role `r`, symbol `sy`, trade time `t`, server time `ts` | `NormalizedTrade` | trade ID, sequence, aggressor side, signed delta |
| `candlestick_<resolution>` | O/H/L/C, resolution, symbol, publish time, traded volume `v` where supplied; Global capture also observed candle start `cst` | `NormalizedCandle` | candle-close/finality flag; sequence |
| `MARK:<symbol>` candlestick | mark-price O/H/L/C | `NormalizedCandle(price_basis=MARK_PRICE)` | traded-price status and volume unless supplied |
| `ob_l1` | best bid/ask price and size | `NormalizedL1Book` | sequence and aggressor/order-flow inference |
| `ob_l2` | top-15 bid/ask price-size levels | `NormalizedL2Book` | sequence and incremental reconstruction |
| `ob_updates` | documented, not yet normalized | none | incremental-book state/imbalance |

## Invariants

- A mark price is never used as a last trade or traded OHLCV.
- Missing candle volume is `None`, never `0`.
- Maker/taker role is not an aggressor direction; delta and CVD stay
  unavailable.
- A documented public compact frame has no normalized sequence in the new
  adapter; its sequence status stays `UNAVAILABLE`.
- The normalized candle has `closed=False` because the documented sample
  does not establish a close/finality field.  Strategy dispatch must not
  consume it as a closed execution candle until this contract is verified.
- `cst`, when provided, is retained as the candle-start timestamp; the
  provider publish timestamp is retained separately and is never substituted
  as candle time. The latter retains the raw provider resolution so updates
  within the same canonical second stay correctly ordered.
- `CandleFinalityTracker` emits a closed candle only after a later `cst` is
  actually observed. It never closes a candle based solely on elapsed local
  time; a silent feed remains forming.
- `CandleContinuityTracker` records missing `cst` intervals as
  `DATA_GAP_UNREPAIRED`; it never manufactures missing bars.
- `ClosedCandleRouter` suppresses even a causally confirmed candle when its
  ingest result reports `DATA_GAP_UNREPAIRED`. A discontinuous series cannot
  silently resume strategy delivery.

## Feature evidence gates

`data.delta.capabilities.assess_capabilities()` is the required capability
assessment for this normalized state. Traded OHLCV and basic volume analysis
need a traded-price candle with reported volume. A snapshot L2 book is not a
verified incremental book, so it does not enable order-book imbalance.
Public trade maker/taker role does not enable signed delta or footprint.

## Runtime delivery bridge

`data.delta.runtime_candle_bridge.to_runtime_candle()` is the only proposed
new-path conversion to the repository's legacy strategy candle type. It
accepts only an `APPLIED`, causally closed, continuous, traded-price candle
at the expected resolution, with both `cst` and reported volume. Missing
volume, mark price, a forming candle, a discontinuity, and a resolution
mismatch are explicit rejections; none becomes a zero-volume runtime candle.

`DeltaRuntimeStreamAdapter` composes that bridge with normalization, causal
finality and continuity. It has the existing `on_closed_candle(Candle)`
callback shape but no socket lifecycle, which keeps the transport migration
separately testable. Consumer exceptions are counted and isolated from frame
ingress.

`VerifiedCandleSubscription` supplies the exact deterministic
`candlestick_<resolution>` payload and symbol demultiplexing contract for a
future socket migration. It has no connection lifecycle and is not yet wired
to `DeltaSubscriptionStream`.

## Durable normalized-event journal

`NormalizedEventJournal` is an opt-in JSONL journal for accepted typed
events. Each append is schema-versioned, ordered, flushed and fsynced.
Recovery rejects partial, unknown or non-contiguous records; it never skips a
record to present an apparently complete history. The journal remains
disconnected from production ingress.

`replay_journal()` now rebuilds only `MarketStateStore` from a validated
journal; it does not invoke a strategy or runtime callback. It reports stale
or duplicate state updates rather than rewriting state. Journal ingestion,
checkpoints, and restart orchestration remain unwired.

## Normalized journal replay

`replay_verified_candles()` consumes the durable normalized journal and
re-applies causal finality, continuity, traded-price and volume checks before
producing legacy replay candles. An end-of-file forming candle, a gap, a mark
price, or missing volume is suppressed rather than becoming a backtest bar.

## Deployment gate

Before wiring this adapter to `RealTimeEngine`, capture and retain raw frames
from the exact target endpoint, verify channel names and closure semantics,
verify symbol formats and timestamps, test reconnect/resubscribe behaviour,
and prove an end-to-end closed-candle route.  This must occur with live
execution disabled.

## Read-only endpoint observation — 2026-09-16

A credential-free subscription to `wss://public-socket.delta.exchange` for
`BTCUSDT` returned valid `ob_l1` and `ob_l2` frames during a ten-second
capture. A separate eight-second `candlestick_1m` probe completed normally
but observed no candle frames. This establishes only endpoint reachability and
the observed L1/L2 envelope; it does not verify trade delivery, candle schema,
candle finality, rollover, reconnect behaviour, or authorize runtime wiring.

## Observed India public fixture — 2026-09-16

A bounded, credential-free capture against the endpoint documented for Delta
India, `wss://public-socket.india.delta.exchange`, subscribed to `BTCUSD`
`trades` and `candlestick_1m`. Its raw public frames are retained at
`data/fixtures/delta/observed_india_btcusd_trades_candles_rollover_20260916.json`.
The static fixture contains 219 trade frames and 114 candle updates. It
observed two consecutive one-minute `cst` values separated by 60 seconds.

The current documentation's compact candle example describes `o`, `h`, `l`,
`c`, `v`, `res`, `sy`, and `ts`, but does not show `cst`; the observed India
frames included `cst`. The normalizer preserves `cst` only as observed
provider evidence, while still requiring a subsequent distinct start timestamp
to causally close the previous candle. Neither documentation nor the fixture
provides a public candle close flag or public sequence number. Public `trades`
provided `p`, `s`, `r`, `sy`, `t`, and `ts`; `r` remains maker/taker role, not
aggressor side. The capture was intentionally partial within both candles, so
it does **not** establish candle-volume conservation from trade size.

This fixture applies to the India endpoint only. It must not be used as proof
that the repository's configured Global endpoint shares the same contract.

## Reconnect resynchronization gate

`data.delta.candle_session_gate.CandleSessionGate` is a transport-independent
fail-closed control for an evidenced candle subscription. After every socket
disconnect it revokes readiness. A new socket open is insufficient: the gate
requires a fresh candle-start baseline and then an exactly one-resolution-later
start before delivery can resume. Missing starts, an out-of-order start, or a
gap leave the gate unready. This is intentionally not wired to the legacy
ticker transport and does not pretend to recognize an undocumented
subscription-acknowledgement schema.

## Observed subscription control

A separate bounded India capture retained one public control frame before
candle data: `{"type":"subscriptions","channels":[{"name":"candlestick_1m",
"symbols":["BTCUSD"]}]}`. `is_observed_subscription_snapshot()` recognizes
only that captured envelope and exact requested channel/symbol set. It is
useful evidence that the initial subscription was accepted, but it is not a
documented guarantee of successful re-subscription after a network failure.
No server-initiated disconnect or reconnect response was observed in the
bounded captures; that verification remains open.

## Client reconnect observation

Two serial, client-initiated eight-second India candle sessions each returned
the same observed `subscriptions` echo before candle updates. The stored
fixture is `data/fixtures/delta/observed_india_btcusd_client_reconnect_20260916.json`.
The first session also contained an exact duplicate candle frame. The normal
event store and runtime adapter already reject duplicate-or-old updates; the
fixture regression proves this public behavior is represented in test data.

This is evidence of client re-subscription only. It does not demonstrate a
provider-initiated disconnect, resumption sequence, gap repair, or continuity
across sessions, so a reconnect still must pass `CandleSessionGate` before any
future strategy delivery.

## Verified strategy dispatch boundary

`VerifiedStrategyDispatcher` is the required final gate for a future verified
socket path. It accepts a runtime candle only with an authoritative normalized
state that is fresh, continuous, and capability-qualified for traded candle
volume; it separately rejects a forming candle. The capability check examines
actual normalized candles, not a caller-provided boolean. The legacy candle
callback has no provenance or normalized-state link, so it remains outside
this boundary and cannot be promoted by configuration.

`VerifiedStrategyDispatcher` can emit a `StrategyDispatchRecord` for every
allow/reject decision. The record contains decision reason and bounded market
identity/timestamp fields, never raw credentials or provider payloads. A
telemetry callback failure is counted but cannot turn a rejected candle into
strategy delivery or raise into public ingress.

## Global evidence status — 2026-09-18 (execution recovered, real captures)

**PARTIAL.** Genuine bounded captures from `wss://public-socket.delta.exchange`
for `BTCUSDT` are retained under
`data/fixtures/delta/observed_global_btcusdt_*_20260918.json` and pinned by
`tests/test_delta_observed_global_fixture_phase1.py` (10 passed):

* Subscription acknowledgement: multi-channel `subscriptions` echo, observed
  in 8 sessions including a 2-session client reconnect observation
  (client-initiated only — NOT server-disconnect evidence).
* Real `candlestick_1m` schema (`o/h/l/c/v/res/sy/ts/cst`, µs `cst`/`ts`):
  4 burst captures, 2–3 updates per `cst`, OHLCV evolving intra-`cst`.
* Natural exact-duplicate frames in 3 captures (rejected DUPLICATE_OR_OLD;
  exactly-once preserved end-to-end through the normalized chain).
* Real `trades` schema (`p/s/r/sy/t/ts`; `r` = maker/taker role, never
  aggressor side): 2 frames in a 150s window.
* Ticker reference shape (mark `m`, top-level `sy`, embedded daily `ohlc`
  stats — NOT 1m OHLCV, never strategy candles).
* Sparse publication: ~1 burst per 5–6 min; silent minutes are normal.
  Cross-capture `cst` spacings are 300–360s gaps.  Feeding all real frames
  through `DeltaPublicEventStream` yields 8 applied / 4 duplicates rejected,
  `volume_available=True`, `gap_status=DATA_GAP_UNREPAIRED` — the fail-closed
  continuity design is confirmed correct by real data.
* Verifier CLI (`scripts/verify_delta_global_evidence.py --bundle …`)
  correctly reports `GLOBAL_EVIDENCE_BLOCKED` on every partial bundle.

**Still BLOCKED:** consecutive-`cst` (60s) rollover in one session (not
observed in ~25 min across 6 candle sessions); production wiring of the
verified transport; server-initiated disconnect/recovery.

* Required: `wss://public-socket.delta.exchange`, `BTCUSDT`,
  `candlestick_1m` + `trades`, subscription echo, multiple updates sharing
  one `cst`, a 60s rollover, and a two-session reconnect observation.
* Verifier: `scripts/verify_delta_global_evidence.py` (`verify_single_session`
  / `verify_reconnect_observation`); gate tests:
  `tests/test_delta_global_evidence_gate_phase1.py`. Synthetic verifier
  fixtures in tests are gate-logic proofs only, never exchange evidence.
* India `BTCUSD` fixtures remain venue-specific and are never Global proof.
* Documentation fixture:
  `data/fixtures/delta/global_docs_websocket_contract_20260918.md`
  (official docs as documentation only); capture runbook and block notice:
  `data/fixtures/delta/README_GLOBAL_EVIDENCE_BLOCKED.md`.
* Execution shell was unavailable in this session, so no live capture was
  attempted beyond the tooling above; nothing new is claimed.
* `data/delta/verified_socket_transport.py` is the fail-closed Phase-2
  transport (evidence-gated connect, per-symbol `CandleSessionGate`,
  bridge + dispatch gates). It is implemented but NOT production-wired
  until the Global bundle above exists and passes verification.
* Legacy ticker-mark strategy delivery is removed: `data/websocket_client.py`
  `start()` defaults to mark-price reference-only (`publish_candles=False`);
  LIVE/ANALYZE in `main.py` runs that reference-only feed with an explicit
  disabled-strategy banner. Mark price never enters the strategy runtime.

## Phase-2 evidence status — 2026-09-20 (advisory conformance, no wiring change)

* India advisory redacted fixtures
  (`data/fixtures/delta/observed_india_btcusd_advisory_redacted_20260920.json`
  27 frames, hash `1bc25786…`; `..._20260920_b.json` 29 frames, hash
  `4e4adea4…`): two independent bounded India `BTCUSD` captures
  (`candlestick_1m` + `trades` + `ticker`, control echo retained), redacted
  with `data/delta/india_fixture_harness.py` (transport wall-clock removed
  only; frames byte-preserved). Both classify `candlestick_1m`
  VERIFIED_SCHEMA / `trades` VERIFIED_BEHAVIOR (≥2 frames) / `ticker`
  VERIFIED_SCHEMA / duplicate NOT_OBSERVED / rollover NOT_OBSERVED
  (single-`cst` short windows). Rollover and duplicate behavior remain
  evidenced only by the legacy `..._trades_candles_rollover_20260916.json`
  fixture (EXISTING_GENUINE_FIXTURE, VERIFIED_BEHAVIOR).
* Ticker parity is schema-only: India and Global tickers share the mark-`m`
  + daily-`ohlc` reference shape and neither normalizes as a 1m candle.
  Schema similarity is NOT venue-contract equivalence
  (`tests/test_delta_evidence_conformance_phase2.py`).
* Transport conformance pinned on genuine frames: `DeltaPublicEventStream`
  applies real trades/candles, rejects exact duplicates
  (`DUPLICATE_OR_OLD`), leaves `ticker`/control `UNHANDLED` (no normalized
  ticker event by design), and rejects malformed frames without fatality;
  a single-`cst` stream never yields a runtime candle through
  `to_runtime_candle`; `CandleSessionGate` reaches ready only on a genuine
  consecutive-`cst` rollover and revokes on disconnect;
  `VerifiedStrategyDispatcher` refuses delivery without authoritative state.
* Exact contract gaps pinned across all genuine India/Global frames: no
  candle-close flag and no public sequence number observed anywhere
  (UNVERIFIED/UNAVAILABLE); `cst` is PARTIALLY_VERIFIED (observed India +
  Global, absent from the compact documentation sample).
* Global 150s bounded capture on 2026-09-20 connected and received the
  `subscriptions` echo but zero data frames (genuine negative evidence;
  consistent with ~1 burst per 5–6 min sparse publication). Not persisted
  as a fixture — a Global silence fixture already exists.
  GLOBAL_ROLLOVER remains NOT_OBSERVED / BLOCKED; no single Global bundle
  passes the full bar; the India skip flag does not affect any Global
  verdict. Production wiring remains unchanged; the project remains
  **NOT_LIVE_READY**.
* A second 330s Global capture on 2026-09-20 repeated the result
  (connected, echo, zero data frames). Two fresh negative samples now
  corroborate sparse publication; still not rollover evidence and still
  not a substitute for a qualifying cross-boundary session.
