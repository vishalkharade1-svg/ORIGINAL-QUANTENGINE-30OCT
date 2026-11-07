# PHASE 24 FINAL REPORT — VERIFIED TRANSPORT REPLAY, PAPER-SESSION READINESS & OPERATIONAL EVIDENCE (2026-10-28)

## 1. Executive result

Phase 24 is delivered as verified engineering work with all six release gates
unchanged fail-closed. A deterministic replay harness
(`data/realtime/verified_replay.py`) now drives the REAL production assembly —
the verified public-candle transport seam, the delivered verified chain
(finality + continuity + fail-closed bridge), the 6D subscription workers, the
frozen institutional pipeline and the dry-run paper broker — over recorded
captures and labelled synthetic fixtures with explicit, reproducible fault
injection. A real integration defect was found by probe (P24-1: a documented
disconnect path that could never succeed) and fixed fail-closed with
regression coverage. The full repository suite stands at **4814 passed / 14
skipped / 466 subtests** with the only 8 failures being the expected
manifest-staleness class that clears with the closing manifest regeneration
(re-verified green at the closing receipt). Paper-session operational
evidence is delivered: runbook, testnet checklist, blocker register,
capability-matrix update and sample replay reports. No research baseline,
frozen dataset, hypothesis or digest pin was modified; no live or testnet
order path was armed; nothing was shipped unlabelled.

## 2. Starting and final state

- Starting state: branch `main`, tracked-modified 99 / untracked ~292,
  manifest 2393 entries verified `MANIFEST_PASS (0 problems)` rc=0
  BEFORE any Phase-24 change; all Phase-23 suites green at the seam
  (transport 10/10 + engine integration 4/4 in the focused run).
- Final state adds: `data/realtime/verified_replay.py` (harness),
  `scripts/run_verified_transport_replay.py` (operator CLI),
  `tests/test_verified_transport_replay_phase24.py` (35 tests),
  `reports/PHASE24_REPLAY_EXAMPLE/*.json` (3 sample reports),
  `docs/operations/PAPER_SESSION_RUNBOOK_PHASE24.md`,
  `docs/operations/TESTNET_READINESS_CHECKLIST_PHASE24.md`,
  `reports/PHASE24_BLOCKER_REGISTER.md`, the Phase-24 appendix in
  `reports/PHASE17_PRODUCT_COMPLETION_MATRIX.md`, and the Phase-24
  additions documented in `data/realtime/verified_transport.py`'
  module docstring (its docstring now records what changed and why).
- The legacy `reports/UNRESOLVED_BLOCKERS.json` was left untouched
  (historical record); the Phase-24 register is additive.

## 3. The P24-1 defect and its fail-closed closure

**Finding (probe-verified):** `VerifiedPublicCandleTransport.notify_down`
(mission item 3a) fanned out `on_down` but RETAINED the subscription. The
worker's documented reconnect retry then called `transport.subscribe` forever
and failed forever with `ValueError: symbol 'BTCUSD' is already registered
with this transport` — the channel was dead but DELIVERY CONTINUED THROUGH
THE STILL-REGISTERED CALLBACK while the worker churned in `RECONNECTING`.
The Phase-23 form of the transport made its own documented worker-reconnect
path impossible.

**Closure (verified, fail-closed):** `notify_down` now tears down the
affected registrations after the fan-out — the subscription ceases to exist
exactly like the socket that died. Consequences, all tested:

- frames arriving while a symbol is torn down are counted `unrouted`
  (never queued, never delivered late);
- the worker's scheduled reconnect retry re-subscribes through the ordinary
  `subscribe` seam and restores LIVE delivery;
- the stream's finality/continuity state is retained by the teardown: a
  disconnect spanning candle boundaries surfaces as a real continuity gap,
  which blocks closes until repaired or until the session restarts;
- Phase-23's transport test was updated to the corrected contract
  (`test_notify_down_fans_out_tears_down_and_resubscribe_restores`) — a
  documented contract refinement, not a weakened assertion: the same test
  previously asserted the impossible inbound-delivery-forever behavior.

## 4. Replay harness and operator CLI

- `data/realtime/verified_replay.py` — `VerifiedTransportReplay` builds the
  production assembly once and feeds frame records in receipt order
  (`speed=0` fully deterministic; clock-driven only for reconnect retry
  scheduling). Evidence classes are explicit: `load_capture` parses
  `quantengine.delta-public-capture.v1` bundles (CAPTURED);
  `synthetic_candle_frames` / `make_synthetic_bundle` produce labelled
  SYNTHETIC_FIXTURE feeds whose OHLCV series is byte-for-byte the
  repository's canonical pipeline feed family for the same seed. Fault
  plans: `DuplicateFault`, `OutOfOrderFault`, `MalformedFault` (5 modes),
  `GapFault`, `DisconnectFault`. A `ReplayReport` (schema
  `quantengine.verified-transport-replay.v1`) carries stream/transport/
  worker/engine/pipeline/risk/paper/gap/disconnect/log-verdict counts plus
  observational latency/runtime/memory; `to_json()` is the report format.
- `scripts/run_verified_transport_replay.py` — operator CLI with
  `replay-capture` and `soak` subcommands, repeatable fault tokens
  (`duplicate@N`, `out_of_order@N[:steps]`, `malformed@N:MODE`,
  `gap@N:missing`, `disconnect@N[:delay]`), `--repair-gap` operator step,
  clean-criteria exit code, machine-readable report output.
- Cumulative risk trail: per-cycle registry clears are production design,
  so the harness accumulates `setups_seen_total`, `decision_accepted_total`
  (with the per-candidate RR list), `decision_rejected_total` and
  `orders_created_placed` across the run from the real per-cycle objects;
  the production log verdicts (`SETUP_ACCEPTED`, `SETUP_REJECTED`,
  `ORDER_CREATED`, `ORDER_FILLED`, `ORDER_SKIPPED_*`, `ROUTE_BLOCKED_*`)
  are counted by an additive, restoring log observer as the secondary trail.

## 5. Verified behaviors (fault injection & recovery matrix, all in the REAL chain)

| Scenario | Verified behavior |
|---|---|
| Recorded capture (India BTCUSD, 235 frames) | 234 applied + 1 stream-deduped duplicate; 1 closed candle delivered and routed; pipeline processed 1; continuity CONTINUOUS; ledger reconciled; unrouted 0 |
| Deterministic soak (12,000 frames) | 11,999/11,999 closed candles delivered AND routed; 0 route/reconcile errors; stream clean; ledger reconciled; 4,302 setups seen, 328 accepted, 18 orders, 18 closed trades, equity 2000 → 2158.30 (+7.91%) |
| Fault-injected soak (6,000 frames) | duplicates + out-of-order + malformed + gap + disconnect combined; 2 duplicates suppressed, 1 malformed rejected, gap detected; EXIT=0 with the repair step |
| Duplicate frame | `DUPLICATE_OR_OLD` at the store; no extra pipeline cycle; routing unchanged |
| Out-of-order retransmission | `DUPLICATE_OR_OLD` behind the watermark (even with a fresh provider timestamp); no state change, no closed delivery |
| Malformed frames | 4 of 5 modes rejected at the stream with precise counted reasons; the 5th (`drop_volume` replay) is store-deduped; a volume-less candle's close is refused at the DELIVERY gate ("traded candle volume is unavailable") — fail-closed |
| Continuity gap | ALL subsequent closes rejected ("candle continuity is not verified") while the gap is outstanding — strict fail-closed, not just the straddling close |
| Exact repair | only complete starts clear a range (`ranges_repaired=1`); incomplete/foreign repairs keep `DATA_GAP_UNREPAIRED`; repaired candles are journaled but NEVER routed (routing unchanged after repair); delivery resumes on the next admitted close |
| Disconnect + resubscribe | teardown → RECONNECTING → scheduled retry → LIVE; frames during the outage unrouted (never delivered late); no duplicate fills after reconnection; symbol-scoped |
| Unregistered symbol | stream may record state-only; nothing routes (transport `unrouted` counted); no decisions/orders possible |
| Impossible geometry | rejected at the stream (`candle OHLC geometry is impossible`); never reaches strategy |
| Forming-only feed | no closed delivery, no decisions, no orders |
| Transport shutdown | subscriptions torn down; further ingests are state-only and never route; ledger/trades remain inspectable (known-safe state) |
| Downstream exception | isolated and counted (`route_errors=1`); subsequent candles route normally; ledger stays clean |
| Cold start | first close requires two distinct candle starts (documented finality semantics) |

## 6. Integrated risk enforcement (1:6 floor wherever applicable)

The feeds' RR distributions (same chain, real placement):

- **Runtime policy (default 1:1, operator-editable):** seed-99 feed → 66
  setups, 16 decision-accepted (RR 3.205–5.652), 3 orders PLACED and filled;
  every placed order's `risk_reward >= 1.0` (the active floor); ledger
  reconciled.
- **Frozen era gate (`QUANTENGINE_FROZEN_OOS=1` ⇒ 1:6):** the SAME feed →
  0 accepted, 0 orders; every sub-floor candidate rejected at the DECISION
  stage with reason `Risk Reward` — the enforcement site is
  `core/setup/decision_engine.py:199-205` (frozen) / `:219-222` (policy);
  the RiskEngine defense-in-depth site is `core/risk/risk_engine.py:429-465`
  (frozen) / `:486-496` (policy, logs `ORDER_SKIPPED_RR`).
- **Above-floor admission under the frozen gate:** seed-11 feed (RR
  8.077–11.307) → candidates accepted and orders placed; every accepted
  candidate RR `>= 6.0` and every placed order RR `>= 6.0`; ledger
  reconciled.
- **Policy floor raised in memory (8.0, restored):** same feed → 0 accepted,
  0 orders, `Risk Reward` in the recorded rejection reasons; the persisted
  operator policy file was never touched.

Conclusion: the floor is enforced at the correct site for its mode, in the
real transport→pipeline→risk→placement chain, and no order below its
applicable floor can be placed. The frozen 1:6 remains opt-in via
`QUANTENGINE_FROZEN_OOS=1`; the runtime policy floor remains
operator-configurable; neither was modified.

## 7. Test receipts

| Run | Command | Result |
|---|---|---|
| Phase-24 suite | `python -m pytest tests/test_verified_transport_replay_phase24.py -q` | 35 passed |
| Unified seam battery | transport + engine-integration + Phase-24 suites | 50 passed |
| Starting-state Phase-23 suites | transport + engine integration | 15 passed (4.62s) |
| Realtime battery (11c + realtime) | 43 passed (246.51s) |
| Pipeline/risk/paper regressions | pipeline_regressions + stage4_soak + risk_gates_12 + hardening_stage123 | 77 passed (1294.56s) |
| **Full suite (final tree, manifest pre-regen)** | `python -m pytest tests/ -q -p no:cacheprovider --no-header` | **8 failed / 4814 passed / 14 skipped / 466 subtests in 2952.00s (0:49:11)** — every failure in the manifest-staleness class (4 files: manifest_contract 158 ×5, snapshot_neutrality 158 ×1, release_consistency_155 ×1, release_manifest_154 ×1), the expected state before the closing regeneration |

Closing verification (after `generate_manifest.py --write`): the 8
manifest-class tests re-run green and the focused seam battery re-verified —
figures recorded in §11.

The mid-phase SNAPSHOT_GUARD start_problems lines that appear in focused-run
output are the same staleness class (tree ahead of manifest), not a suite
failure; they clear with the regeneration by design.

## 8. Evidence classes and provenance hygiene

- CAPTURED: the India BTCUSD public capture (schema
  `quantengine.delta-public-capture.v1`, receipt ordinals 1..235) — replayed
  read-only; repaired-via-capture flows were proven on synthetic frames and
  are procedurally identical for captured ones.
- SYNTHETIC_FIXTURE: every fault injection and soak (explicit
  `synthetic: True` labels in frames, bundles and reports).
- No evidence class was promoted; no captured byte was modified; no
  fabricated market data entered any production path (the synthetic feed
  enters only through the same verified fail-closed seams and is labelled
  end-to-end).
- Changed shipped files: `data/realtime/verified_transport.py` (P24-1 fix +
  exposed seam methods, docstring-documented), the Phase-23 transport test
  (contract refinement), the capability matrix (additive section). No
  research baseline, config gate, hypothesis, frozen dataset or digest pin
  changed.

## 9. Deliverables index

| Deliverable | Path |
|---|---|
| Replay harness module | `data/realtime/verified_replay.py` |
| Operator CLI | `scripts/run_verified_transport_replay.py` |
| Regression/fault-injection suite | `tests/test_verified_transport_replay_phase24.py` (35 tests) |
| Sample reports | `reports/PHASE24_REPLAY_EXAMPLE/replay_capture.json`, `soak_12000_seed11.json`, `soak_6000_seed99_faults.json` |
| Paper-session runbook | `docs/operations/PAPER_SESSION_RUNBOOK_PHASE24.md` |
| Testnet readiness checklist | `docs/operations/TESTNET_READINESS_CHECKLIST_PHASE24.md` |
| Blocker register | `reports/PHASE24_BLOCKER_REGISTER.md` |
| Capability matrix | `reports/PHASE17_PRODUCT_COMPLETION_MATRIX.md` (Phase-24 appendix) |
| Final report | `reports/PHASE24_FINAL_REPORT.md` (this file) |

## 10. Remaining gates — unchanged (verified this phase)

| Gate | Status |
|---|---|
| RELEASE_GATE | HOLD |
| EDGE | NOT ESTABLISHED (paper PnL in the soak demonstrates mechanical execution only, never edge) |
| TESTNET_EXECUTION | NOT AUTHORIZED (checklist §B items all open, owner actions) |
| P192 | NOT VERIFIED/BLOCKED |
| CREDENTIAL_EXPOSURE_REMEDIATION | OPEN/NOT VERIFIED (scanner rc=1 fail-closed on the standing `.env` finding; historical `.env` bytes exist in git history and differ from the current file — owner-side revocation is the remedy; values were never printed this phase) |
| OLD_CREDENTIAL_REVOCATION | NOT VERIFIED |

New documented findings (not defects left open): P24-2 (repair requires
window-aligned starts — stricter than the live path, fail-closed),
P24-3 (no built-in public-socket pump for the paper seam — deliberate,
operator-provided), P24-4 (per-cycle decision registry — design, cumulative
trail via logs + harness accumulator). See
`reports/PHASE24_BLOCKER_REGISTER.md`.

## 11. Closing receipt

Recorded AFTER the closing manifest regeneration:

- Manifest: `python scripts/generate_manifest.py --root . --write
  BUILD_MANIFEST.sha256` → regenerated with **2403 entries**, rc=0
  (the emitted `PROHIBITED_EXCLUDED_FROM_COVERAGE:.env` line is the
  informational notice that the secret-bearing `.env` stays excluded
  from coverage); `--verify` → `MANIFEST_PASS (0 problems)`, rc=0.
- The 8 manifest-class tests re-verified green post-regeneration
  (test_phase158_manifest_contract.py, test_phase158_snapshot_neutrality.py,
  test_release_consistency_phase155.py, test_release_manifest_phase154.py):
  **31 passed, 20 subtests, EXIT=0**.
- Focused seam battery re-verified post-regeneration (transport +
  engine-integration + Phase-24 suites): **50 passed, EXIT=0**.
- Secret scan posture: `SECRET_SCAN_FAIL .env non_empty_known_secret` rc=1
  (fail-closed, standing owner-blocked class; unchanged from the
  starting state; no Phase-24 file is secret-bearing).
- Because this report is itself a packaged file, the manifest was
  regenerated once more after this receipt was written and the
  verification repeated (the recorded figures above were observed on the
  first regeneration; the second regeneration changes only the report's
  own entry — `MANIFEST_PASS (0 problems)` re-confirmed at the very end
  of the session shell transcript).
