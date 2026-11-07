# Paper-Session Runbook (Phase 24) — verified-transport paper runtime

Status: OPERATIONAL EVIDENCE DELIVERED (Phase 24). Paper-only. The release
gates are unchanged: `RELEASE_GATE = HOLD`, `EDGE = NOT ESTABLISHED`,
`TESTNET_EXECUTION = NOT AUTHORIZED`, `P192 = NOT VERIFIED/BLOCKED`,
`CREDENTIAL_EXPOSURE_REMEDIATION = OPEN/NOT VERIFIED`,
`OLD_CREDENTIAL_REVOCATION = NOT VERIFIED`.

This runbook is written for the OWNER. Every step is either (a) a verified
in-repo procedure proven by the Phase-24 test suite and replay artifacts, or
(b) an explicit owner action that is impossible to complete from inside the
repository. Paper mode never touches exchange writes: the runtime is
assembled `dry_run=True` and the verified transport owns no credentials and
no sockets of its own.

## 0. What is verified vs. what is owner-side

Verified by the repository (do not re-argue; see
`reports/PHASE24_FINAL_REPORT.md` §receipts):

- The verified public-candle seam
  (`data/realtime/verified_transport.py`) delivers only what the
  Phase-1..22 verified chain admits: closed candles with finality +
  continuity + traded-price basis + reported volume; forming frames are
  freshness ticks only; duplicates, out-of-order retransmissions,
  mark-price-only, volume-unavailable, continuity-broken and malformed
  frames never deliver; every rejection is counted in `transport.stats()`.
- The full paper path (transport → `DeltaPublicEventStream` →
  `to_runtime_candle` → worker router → `RealTimeEngine` → `PaperRuntime`
  → `BrokerEngine(dry_run=True)` → `InstitutionalPipeline` → `RiskEngine`
  → `TradeSimulator`) routes 11,999/11,999 closed candles in a 12,000-frame
  deterministic soak with zero route errors and a reconciled ledger
  (equity = starting balance + realized PnL exactly).
- Disconnect recovery (`notify_down` → teardown → worker RECONNECTING →
  scheduled retry re-subscribe → LIVE) restores delivery without duplicate
  fills; frames during the outage are counted `unrouted` (fail-closed,
  never delivered late).
- Continuity gaps block ALL subsequent closes (fail-closed) until an
  exact-candle repair restores continuity; repaired history is journaled
  but never routed to strategy.
- Risk floors: the frozen 1:6 era gate (`QUANTENGINE_FROZEN_OOS=1`,
  enforced at `core/setup/decision_engine.py:199-205` with the RiskEngine
  re-validation at `core/risk/risk_engine.py:429-465`) and the runtime
  policy floor (default 1:1, operator-editable,
  `core/risk/trading_policy.py`) are enforced in the REAL chain, and no
  order below its applicable floor can be placed (verified in
  `tests/test_verified_transport_replay_phase24.py`).

Owner-side (cannot be done from the repository):

1. Choosing the session's socket source and operating a public-socket
   pump that feeds `transport.ingest(frame, receipt_timestamp=...)`
   (the seam is deliberately caller-driven — `data/realtime/
   verified_transport.py:15-18`). The repository ships no live socket
   pump for the paper seam; offline replay + soak are the verified ways
   to run sessions today.
2. Any credentials: paper mode requires none, and none must be present
   in the process. (See the testnet checklist for the credential hygiene
   prerequisites when testnet is eventually considered.)
3. Deciding whether the observed paper economics justify any further
   phase (the `EDGE = NOT ESTABLISHED` gate stays until the owner's own
   evaluation says otherwise — the engine does not self-certify edge).

## 1. Pre-flight (every session)

```powershell
# from the repository root
python scripts/generate_manifest.py --root . --verify
# expect: "MANIFEST_PASS (0 problems)" and exit code 0
```

- Confirm the working tree matches the manifest (a changed tree must be
  re-verified before any session; the manifest is the packaging truth).
- Confirm no secrets in the environment: `DELTA_API_KEY`,
  `DELTA_API_SECRET`, `DELTA_SANDBOX_API_KEY`,
  `DELTA_SANDBOX_API_SECRET` must be ABSENT for a paper session.
- Confirm the mode: `EXECUTION_MODE` unset or `PAPER` (default
  `PAPER_MODE=True` / `LIVE_MODE=False` in `config/settings.py:62-63`).

## 2. Offline replay session (verified today)

The deterministic replay harness drives the real assembly offline — this
is the currently-verified way to operate a paper session:

```powershell
# recorded capture replay (CAPTURED evidence; the India BTCUSD capture)
python scripts/run_verified_transport_replay.py replay-capture `
  --capture "data/fixtures/delta/observed_india_btcusd_trades_candles_rollover_20260916.json" `
  --measure --out "reports/PHASE24_REPLAY_EXAMPLE/replay_capture.json"
# exit 0 = delivery routed, zero route errors, ledger reconciled

# sustained deterministic soak (SYNTHETIC_FIXTURE; labelled)
python scripts/run_verified_transport_replay.py soak `
  --symbol BTCUSDT --candles 12000 --seed 11 --measure `
  --out "reports/PHASE24_REPLAY_EXAMPLE/soak_12000_seed11.json"

# fault-injected soak (duplicates / out-of-order / malformed / gap /
# disconnect) with the operator gap-repair step
python scripts/run_verified_transport_replay.py soak `
  --symbol BTCUSDT --candles 6000 --seed 99 `
  --fault duplicate@100 --fault out_of_order@200:3 `
  --fault malformed@300:impossible_ohlc --fault gap@400:2 `
  --fault disconnect@500:3 --repair-gap `
  --out "reports/PHASE24_REPLAY_EXAMPLE/soak_6000_seed99_faults.json"
```

What the reports mean (schema `quantengine.verified-transport-replay.v1`):

- `counts.stream` — the verified stream's own accounting (`applied`,
  `duplicates_or_old`, `rejected`, `unhandled`).
- `counts.transport.closed_delivered` — closed candles admitted by
  finality+continuity+bridge and handed to the runtime; equals
  `counts.engine.routed` in every clean run.
- `counts.transport.runtime_rejections` — counted, human-readable
  rejection reasons; a non-zero value is expected under faults and must
  be explainable from the fault plan.
- `counts.risk` — cumulative trail: `setups_seen_total`,
  `decision_accepted_total` (with the per-candidate RR list),
  `decision_rejected_total`, `orders_created_placed`.
- `counts.paper` — orders, closed trades, equity; `ledger reconciled :
  True` requires equity == starting + realized PnL exactly.
- `non_deterministic` (latency/runtime/memory) — observational only;
  never acceptance criteria.
- Evidence class labels: `CAPTURED` (recorded exchange data) vs
  `SYNTHETIC_FIXTURE` (labelled synthetic; fault/soak only). Never
  promote one class to the other.

Exit code 0 requires: zero route errors, zero reconcile errors, the
ledger reconciled, and (with `--repair-gap`) continuity restored to
`CONTINUOUS`.

## 3. Live paper session (owner socket pump required)

When the owner provides a socket pump, the runtime binding is:

```powershell
$env:EXECUTION_MODE = "PAPER"          # or leave unset (PAPER default)
$env:QE_PAPER_VERIFIED_TRANSPORT = "1" # opt into the verified seam
$env:SYMBOLS = "BTCUSD"                # or "BTCUSDT,ETHUSDT" for the global venue
$env:TIMEFRAME = "1m"
python main.py
```

Startup semantics (all verified):

- `build_paper_engine` binds `verified_public_candle_transport_factory`
  and logs `PAPER verified candle transport ENABLED` — without the env
  the default stays fail-closed (no ticker-derived candles ever).
- The `LiveSafetyGate` banner prints the paper posture; nothing can
  place an order (dry-run assembly; no executor exists in paper mode).
- The engine polls on a cadence (`run_paper_with_monitoring`), routing
  each closed candle through the verified chain to the per-symbol
  `PaperRuntime`. Ctrl-C ends the loop and stops the engine cleanly.

Operational duties during the session (owner pump side):

- Feed frames strictly as received: `ingest(frame, receipt_timestamp)`
  with the receipt time the frame was handed to you. Never re-derive,
  re-order, drop-without-count, or re-time frames; the chain's own
  dedupe/finality/continuity decides admission.
- Watch `transport.stats()`: `unrouted` should stay 0 while every
  subscribed symbol is registered; any growth means frames are arriving
  for a torn-down or unregistered symbol (see fault recovery).
- On a socket drop: call `notify_down(symbol_or_None)` (fan-out +
  registration teardown), let the worker's scheduled retry re-subscribe,
  and do NOT hand-deliver backfill through the live seam. If the outage
  spanned candle boundaries, a continuity gap will block closes
  (`DATA_GAP_UNREPAIRED` in `continuity_status`) until an exact-candle
  repair is performed with the venue's historical candles for exactly
  the missing starts (`repair_gap_history`) — repaired candles are
  journaled, never routed to strategy.
- Record every session: start/stop times, symbol set, stream/transport
  counters at stop, the ledger reconciliation verdict, and any manual
  interventions. The sample reports under `reports/PHASE24_REPLAY_EXAMPLE/`
  show the exact JSON shape to keep.

## 4. Health checks and stop procedure

- Per-cycle ledger check (any time):
  `reconcile_paper_ledger(harness)` — equity identity must hold exactly.
- Continuity state: `transport.continuity_status(symbol)`; expectation
  for a healthy session: `CONTINUOUS`, zero outstanding gaps.
- Stop: `engine.stop()` (or Ctrl-C under `main.py`) — subscriptions
  torn down, statuses empty; further ingests are state-only and never
  route (`UNROUTED` counted). The paper ledger and its trades remain
  inspectable afterwards (known-safe state).
- After any stop: re-run the manifest verification before the next
  session; do not hand-edit any runtime state file.

## 5. Failure modes and the correct response

| Symptom | Meaning | Response |
|---|---|---|
| `unrouted` grows while a symbol is LIVE | frames arriving for an unregistered symbol (never routable) | check the pump's symbol set vs the engine's registry; do not attempt to force-route |
| `duplicates_or_old` grows | the venue re-sent frames behind the watermark | no action; dedupe is by design, routing unchanged |
| `runtime_rejections["candle continuity is not verified"]` grows | a real continuity gap blocks closes | collect the venue's historical candles for the missing starts; repair exactly those starts (or restart the session); expect ALL closes blocked until repaired |
| `runtime_rejections["traded candle volume is unavailable"]` | a closing candle without reported volume was refused | expected fail-closed behavior; no repair exists for invented volume |
| `route_errors > 0` | a downstream failure was isolated per candle | inspect the logged error; the engine keeps routing subsequent candles; re-run reconciliation |
| worker state `RECONNECTING` | the subscription was torn down and awaits its scheduled retry | let the worker retry (clock-driven); verify LIVE restored; if retries exhaust (`FAILED`), restart the session |
| `reconcile_errors > 0` | the ledger identity check failed | stop the session; investigate before any further use |

## 6. What this runbook does NOT authorize

- No live/testnet order placement, no credential handling, no gate
  changes, no research-baseline edits. A testnet session requires the
  separate checklist (`docs/operations/TESTNET_READINESS_CHECKLIST_PHASE24.md`)
  and remains NOT AUTHORIZED until its owner steps are complete.
- No re-labeling of evidence classes and no "edge" conclusions from
  paper PnL: the strategy's economics remain `EDGE = NOT ESTABLISHED`;
  paper fills only demonstrate mechanical execution correctness.
