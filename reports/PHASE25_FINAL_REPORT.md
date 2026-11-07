# PHASE 25 — FINAL REPORT

Phase: 25 (Paper-session authority + frozen-OOS strategy validation)
Date: 2026-10-28
Code revision: `ffefa14a8729f6d2160db3735a06257cbb6ab48b` (branch `main`, uncommitted phase work by design)
Baseline: Phase 24 delivered (report: `reports/PHASE24_FINAL_REPORT.md`; 4814 passed / 14 skipped / 466 subtests; `BUILD_MANIFEST.sha256` `MANIFEST_PASS (0 problems)`, 2403 entries).
Mode: Autonomous execution per the Phase-25 master prompt. No live orders. No gate changes. Strategy frozen.

---

## 1. Executive summary

Phase 25 set out to answer two questions with evidence rather than assertion:

1. **Can QuantEngine collect trustworthy, authoritative market data in a real paper session?** — **YES, demonstrated.** A 10-minute bounded authoritative session on real public Delta Global REST data (BTCUSDT 1m) delivered **1445 closed candles: 100% ascending, 100% window-aligned, 0 duplicates, 0 internal gaps, 0 transport failures, 0 engine route errors, reconciliation PASS** — `EXCHANGE_SOURCED_PAPER_SIMULATION` evidence class, with every market observation labelled exchange-sourced and every fill labelled `SIMULATED_PAPER_FILL`.
2. **Does the frozen strategy show credible out-of-sample performance after realistic costs?** — **NO — EDGE NOT ESTABLISHED (unchanged).** The Phase-22-certified Phase-18 frozen-OOS protocol was re-executed at the current revision and **reproduced exactly** (per-period orders 2/0/2/3/8/0 = 15; global continuous run 32 orders; **0 fills, 0 completed trades**). With 0 completed trades, no realized reward-to-risk exists to compare against the 1:6 setup filter, and no cost regime (zero, moderate, conservative, adverse) can change the outcome. Verdict: **OOS_BLOCKED** (0 vs the nine-month minimum of 60 completed trades). This is an evidence problem (sample size), not a tuning opportunity: the strategy was not modified and nothing was selected on OOS data.

Additionally, the Phase-71 funding blocker ("public Delta access previously failed with DNS resolution failure") was **resolved by genuine evidence**: 502 real hourly funding settlements were captured from the live venue and strictly bound to the exact frozen market-data bytes.

All phase gates remain **unchanged** (RELEASE_GATE=HOLD, EDGE=NOT ESTABLISHED, TESTNET_EXECUTION=NOT AUTHORIZED, P192 BLOCKED, `.env` finding owner-blocked).

## 2. Objectives (from the master prompt)

- P25-A: Establish a deterministic baseline (branch/commit/status/manifest) and identify stale reports or results generated from different code revisions. **DONE.**
- P25-B: Build a controlled paper-session harness with explicit evidence classification, real transport ingress, engine-assembly reuse, and Mode-A/Mode-B separation. **DONE.**
- P25-C: Run a REAL bounded live paper session on real public data (~10 min BTCUSDT 1m) with documented conservative cost economics; capture delivery quality, reconciliation, engine counters, and cost profile. **DONE.**
- P25-D: Run the offline Mode-B replay session to prove mode separation and preserve Phase-24 fault semantics. **DONE.**
- P25-E: Frozen-OOS strategy validation: reproduce the certified protocol, then attribute genuine funding and the preregistered cost ladders, without touching frozen semantics. **DONE.**
- P25-F: Security remediation checks (`.env` finding, control-API auth, live-block verification) and honest blocker documentation. **DONE (checks + documentation; remediation owner-blocked).**

## 3. Baseline (P25-A)

- Branch `main`, HEAD `ffefa14`; working tree 103 modified + 300 untracked (phase work uncommitted by design).
- `BUILD_MANIFEST.sha256` verified `MANIFEST_PASS (0 problems)` (2403 entries) before any Phase-25 write.
- Network reachability re-proven during the phase: `https://api.delta.exchange/v2/products` (BTCUSDT id=139, state=live), `/v2/history/candles`, and the funding history endpoint all answered with genuine data. This **resolves** the Phase-71 blocker's environmental premise (prior DNS failure).
- **Different-revision finding:** the recorded `phase30_oos_evidence_accumulation.json` numbers (21 orders / 3 fills across 6 periods of the extended 30247-bar dataset) do **not** reproduce at the current revision (current tree: 45 orders / 1 fill on the same slices). The Phase-30 evidence was produced by an older code revision. The Phase-22-certified reproduction lineage is the **Phase-18 protocol**, and that one **does** reproduce exactly at this revision (§7). The Phase-30 divergence is recorded as different-revision evidence in `research/results/phase25_frozen_oos_validation.json` (`phase30_different_revision_comparison`), not silently ignored.

## 4. What was built (P25-B)

- `data/paper_session/paper_session.py` (+ package `__init__.py`):
  - `PaperSessionRunner` — Mode A authoritative session: real `RestPollingCandleTransport` over `DeltaHistory` (public `/v2/history/candles`, closed-bars only, watermark dedup, ordered), real engine assembly (`MultiSymbolSubscriptionManager` → `SubscriptionWorker` → `CandleRouter` → `RealTimeEngine` → paper pipelines → `BrokerEngine` dry-run), instrumented delivery capture (receipt timestamps + history-call index), raw REST observability (bounded samples), engine log observation (`_LogCountObserver` reuse from Phase 24), reconciliation re-keyed by symbol, and a `_delivery_quality` audit (ascending / duplicates / window alignment / internal missing buckets).
  - `run_replay_session` — Mode B: delegates to the Phase-24 `VerifiedTransportReplay` with the Phase-25 report schema, preserving evidence-class semantics (the synthetic-label regression fix to `load_capture` was made and regression-tested in the Phase-24 suite).
  - `refuse_live_execution` — fail-closed: refuses when `LIVE_MODE` or `EXECUTION_MODE=LIVE` is armed.
  - Artifacts per session: `reports/PAPER_SESSIONS/<session_id>/{session_report.json, delivered_candles.jsonl, session_summary.md}`.
- `scripts/run_paper_session.py` — operator CLI (live/replay; fault tokens `duplicate@N`, `out_of_order@N:steps`, `malformed@N:mode`, `gap@N:missing`, `disconnect@N:delay`).
- `scripts/capture_funding_evidence.py` — genuine funding capture + strict binding (fail-closed if coverage does not reach the OOS end; rc=2).
- `scripts/run_phase25_frozen_oos.py` — deterministic frozen-OOS validation (identity → reproduction → different-revision comparison → funding attribution → cost ladders), writing `research/results/phase25_frozen_oos_validation.json`.
- Tests: `tests/test_paper_session_phase25.py` — 15 tests, all passing (live-path delivery + reconciliation, gap-never-bridged, endpoint-failure clarity, fresh repeat runs, live refusal, invalid inputs, tolerant history proxy, cost profile recorded, shutdown midrun, Mode-B synthetic + capture + faults, audit math, no-order-write-path source scan).

## 5. Real-data paper session (P25-C) — the authoritative evidence

Session `P25-20261028T093215Z-BTCUSDT-1m` (`reports/PAPER_SESSIONS/P25-20261028T093215Z-BTCUSDT-1m/`), provenance commit `ffefa14`, wall 600.0 s, stop reason `run_seconds_elapsed`:

| Metric | Value |
| --- | --- |
| Evidence class | `EXCHANGE_SOURCED_PAPER_SIMULATION` |
| Market data source | `delta_global_public_rest_history_candles` (`https://api.delta.exchange/v2/history/candles`) |
| Delivered (BTCUSDT 1m) | 1445 (warmup 1435 + live 10), unique buckets 1445/1445 expected in span |
| Delivery quality | ascending=true, duplicates=0, window_aligned=true, internal_missing=0 |
| Transport stats | 38 polls, 0 failures, watermark 1793180460 |
| REST history | 39 calls, 0 errors, 55,811 rows seen |
| Engine | routed=1445, unrouted=0, route_errors=0, reconcile_errors=0 |
| Reconciliation | consistent=true; equity 2000.0 = starting balance; 0 open positions; 0 completed trades |
| Cost economics | `CONFIGURED_SIMULATION`: rate 0.0005, slippage 5.0 bps, per_trade 0.0, profile `p25-conservative-assumption`, venue_realistic=false (venue fees UNKNOWN — documented assumption, not a venue claim) |
| Fills are | `SIMULATED_PAPER_FILL` (never exchange fills) |
| Instrument metadata | `SYNTHETIC_SPOT_FALLBACK` (explicit-cut universe; not derivative-realistic) |

**Honest readings:** a 10-minute, 1-symbol, 1-timeframe session is a **preliminary** demonstration of data-pipeline trustworthiness, not a strategy evaluation; 0 orders were generated (no qualifying setup in 10 minutes); paper fills are simulated and no venue fee schedule was available, so cost economics are a labelled conservative assumption.

## 6. Mode-B replay session (P25-D)

Session `P25-REPLAY-20261028T094330Z` (`reports/PAPER_SESSIONS/P25-REPLAY-20261028T094330Z/`): synthetic fixture, seed 99, 600 candles, faults `duplicate@120` + `gap@300:2`. Results: 598 frames ingested, duplicate suppressed (1), 2 candles skipped for the unrepaired gap (`DATA_GAP_UNREPAIRED` — gaps are surfaced, never bridged), 299 closed candles routed / 0 unrouted, 1 order placed, 1 trade closed, equity 2000.0 → 2000.5906, RR gate: 1 accepted (3.205485), 6 rejected. Evidence class `SYNTHETIC_FIXTURE` — mode separation is explicit in every artifact.

## 7. Frozen-OOS strategy validation (P25-E)

Script `scripts/run_phase25_frozen_oos.py` → `research/results/phase25_frozen_oos_validation.json`. Read-only; zero configuration changes; `strategy_parameters_changed=false`.

**Dataset identities verified (fail-closed):**
- Certified Phase-18 dataset `data/history/BTCUSDT_1m_phase17_fresh.json`: 11,461 rows, 1788601500..1789289100, identity `247d8f11…b89c54` — **matches** the recorded Phase-18 `dataset_hash`.
- Extended top-up `data/history/BTCUSDT_1m_oos_topup.json`: 30,247 rows, 1788601500..1790427360, identity `520b849b…2310b0` — matches the Phase-37 manifest.
- Both strictly after the Gate-A discovery boundary 1788601440.

**Certified protocol reproduction (Phase-18, 6 independent cold-start periods + global run):**

| Period | Bars | Orders (current) | Orders (recorded) | Fills | Match |
| --- | --- | --- | --- | --- | --- |
| OOS_01 | 1910 | 2 | 2 | 0 | ✔ |
| OOS_02 | 1910 | 0 | 0 | 0 | ✔ |
| OOS_03 | 1910 | 2 | 2 | 0 | ✔ |
| OOS_04 | 1910 | 3 | 3 | 0 | ✔ |
| OOS_05 | 1910 | 8 | 8 | 0 | ✔ |
| OOS_06 | 1911 | 0 | 0 | 0 | ✔ |
| Global | 11461 | 32 | 32 | 0 | ✔ |

Funnel: per-period 15/0, global 32/0 — **exact match** with `phase18_oos_validation.json`. The certified frozen lineage holds on the delivered bytes at revision `ffefa14`.

**Phase-30 divergence (documented, not ignored):** recorded 21 orders / 3 fills vs current 45 orders / 1 fill on the same six slices — attributed to the older code revision that produced the Phase-30 report. Classification: different-revision evidence.

**Funding attribution (genuine venue evidence):** all six certified periods re-executed WITH the real funding schedule (`btcusdt_funding_bound_to_phase18.json`, 502 hourly settlements, verified against the Phase-18 dataset bytes). Applied funding = 0.000000 across all periods — correct, because settlements apply only within actual holding intervals and there were 0 fills (no holding intervals). The 22,500 s head of the OOS window (before the first captured settlement at `funding_first_event`) has no settlement evidence and is disclosed as `funding_head_gap_seconds` — funding was never defaulted to zero over a holding interval, and no synthetic funding was invented.

**Cost sensitivity (preregistered 11F ladders; reporting only):** A (zero), B (rate 0.0005 + 2 bps), C (rate 0.00059 + 5 bps), D (rate 0.00118 + 10 bps) — with 0 fills, notional-based cost attribution is 0 in every scenario; net PnL = gross PnL = 0.0. The honest conclusion: **costs are not the current bottleneck; the absence of fills is.**

**Realized reward-to-risk:** UNAVAILABLE (0 fills). The Phase-14-era realized-RR finding (1.465 / 1.065 / 1.577, all far below the 6.0 setup floor, from the old-revision Phase-30 run) remains historical context from a different revision and is **not** re-asserted as current-tree evidence. The 1:6 setup gate remains intact and was never bypassed.

**Verdict:** `EDGE NOT ESTABLISHED`, `final_decision=OOS_BLOCKED` (0 completed trades vs the nine-month minimum of 60). This is the honest, unchanged verdict — reproduced, not tuned.

## 8. Funding evidence (Phase-71 blocker resolution)

- Capture: `research/captures/phase25/global_btcusdt_funding_1h.json` — 502 real hourly settlements (BTCUSDT perpetual, Delta Global public history), coverage 1788624000..1790427600, sha256 `f85fc910…` (16-hex prefix; full hash in the ledger).
- Strict bindings (`research/economics/funding_evidence.py`): to the OOS top-up bytes (`reports/evidence/phase25/btcusdt_funding_bound_to_oos.json`, `MARKET_DATA_SHA256 42d62f3f…`) and to the certified Phase-18 dataset bytes (`reports/evidence/phase25/btcusdt_funding_bound_to_phase18.json`). Both load and verify via `load_and_verify` (fail-closed on hash mismatch, event ordering, fingerprint). Generated evidence lives under `reports/evidence/` (not the frozen `research/` tree) so the 11G/Stage-4 research-integrity guards remain byte-clean.
- Pre-existing gap closed: funding was previously `UNAVAILABLE (zero NOT substituted)` in every OOS report; genuine venue funding is now wired through the strict schedule machinery for future runs.

## 9. Cost economics discipline

- Default paper profile remains `explicit-zero-neutral` (explicit zero, never "unknown treated as free").
- The Phase-25 session ran under `CONFIGURED_SIMULATION` (`p25-conservative-assumption`: commission rate 0.0005 + slippage 5 bps), set explicitly via `QE_PAPER_*` env vars before launch and recorded in the session report.
- Delta venue fee schedule is UNKNOWN from this environment; provisioning venue-realistic costs (and flipping `PAPER_COST_VENUE_REALISTIC=true`) is an owner action. Until then, no report claims venue-realistic costs.

## 10. Security & live-block (P25-F)

- **Secret scan:** `python scripts/security/scan_secrets.py` → rc=1, standing finding `.env line=1,2 rule=non_empty_known_secret` (redacted metadata only; secret values never printed). **Owner-blocked remediation** (owner must empty/rotate the file); unchanged from Phase 24, re-verified this phase.
- **Control API auth:** verified fail-closed at source (`core/monitoring/api_server.py`): constant-time bearer check; empty configured token refuses **all** requests; the only unauthenticated route is the data-free dashboard shell (`PUBLIC_GET_PATHS`). Covered by the Phase-15 suite (24 tests passed in the Phase-24 seam battery).
- **Live-block:** armed `LIVE_MODE=1` and `EXECUTION_MODE=LIVE` each abort the session runner with an explicit refusal before any transport or engine starts (`refuse_live_execution`). Verified by direct probe this phase.
- **Transport has no order path:** the REST transport speaks only public market data; no credentials are required or used in either session mode.

## 11. Blocker register (summary)

See `reports/PHASE25_BLOCKER_REGISTER.md` for the full register. Headline blockers (all owner-blocked or evidence-blocked, none new-code-blocked):

1. `EDGE_NOT_ESTABLISHED` — 0 completed trades; 9M protocol needs ≥60 (evidence-blocked).
2. `.ENV_SECRET` — standing scan finding; owner must remediate (empty/rotate).
3. `OLD_CREDENTIAL_REVOCATION` — unverified; owner action.
4. `TESTNET_EXECUTION_NOT_AUTHORIZED` — owner decision (P192 prerequisite).
5. `P192_BLOCKED` — unchanged (depends on 2/3).
6. `VENUE_FEES_UNKNOWN` — Delta fee schedule not obtainable offline; conservative assumption documented until provisioned.
7. `DEV_PARTITION_ABSENT` — pre-Gate-A dev/validation data is not part of this delivery; dev-partition sensitivity analysis blocked (frozen-OOS attribution is reporting, not tuning).
8. `INSTRUMENT_METADATA_SYNTHETIC_FALLBACK` — fail-closed for derivatives; spot fallback metadata synthetic (explicit-cut design).
9. `PHASE30_REVISION_DIVERGENCE` — recorded Phase-30 counts do not reproduce at this revision; documented as different-revision evidence.

## 12. Deliverables checklist

| Deliverable | Status |
| --- | --- |
| `reports/PHASE25_FINAL_REPORT.md` | DONE (this file) |
| `reports/PHASE25_EVIDENCE_LEDGER.json` | DONE |
| `reports/PHASE25_PAPER_SESSION_RUNBOOK.md` | DONE |
| `reports/PHASE25_STRATEGY_VALIDATION.md` | DONE |
| `reports/PHASE25_BLOCKER_REGISTER.md` | DONE |
| `data/paper_session/` (harness + package) | DONE, 15/15 tests passing |
| `scripts/run_paper_session.py` | DONE, exercised live + replay |
| `scripts/capture_funding_evidence.py` | DONE, rc=0 genuine capture |
| `scripts/run_phase25_frozen_oos.py` | DONE, rc=0 deterministic report |
| `data/realtime/verified_replay.py` fix | DONE (synthetic-label regression, Phase-24 suite 36/36) |
| Session artifacts | DONE (2 sessions under `reports/PAPER_SESSIONS/`) |
| Funding capture + 2 strict bindings | DONE |
| `research/results/phase25_frozen_oos_validation.json` | DONE |
| Full suite + manifest regen | see §14 |

## 13. Evidence-class discipline (self-audit)

- Mode A artifacts label every market observation exchange-sourced; fills are `SIMULATED_PAPER_FILL`; instrument metadata is labelled `SYNTHETIC_SPOT_FALLBACK`.
- Mode B artifacts carry `SYNTHETIC_FIXTURE` — no synthetic frame can masquerade as live evidence (regression-tested after the Phase-24 `load_capture` fix).
- Endpoint failure yields explicit error artifacts, never fabricated candles (tested).
- Gaps are surfaced (`DATA_GAP_UNREPAIRED`), never bridged (tested).
- Funding defaults: none — uncovered head disclosed, not zeroed.
- No paper session result is presented as a strategy edge; the frozen-OOS verdict is reproduced, not produced.

## 14. Verification, suite, and manifest

- Phase-25 suite: `python -m pytest tests/test_paper_session_phase25.py -q` → **15 passed** (~30 s).
- Phase-24 seam battery after the `verified_replay.py` fix: **82 passed, 1 skipped**.
- Full suite (first run): 26 failures, in two explained groups. (a) Frozen-research integrity guards (11G `test_tree_only_expected` / `test_no_production_paths`, Researcher-15 `test_no_new_hypothesis_family`, Stage-4 `test_research_byte_unchanged`) because generated funding-evidence artifacts had been placed under `research/evidence/`; **fixed by relocation** of the generated evidence to `reports/evidence/phase25/` (no test allowlist or frozen-test changes), scripts/docs/ledger updated, frozen-OOS report regenerated, `git status -- research/` re-verified empty, all 17 guard/status tests re-run green. (b) Manifest-verification tests (Phase-154/155/158) failing against the pre-regeneration manifest (`uncovered:` new Phase-25 files); these pass after the manifest regeneration below. Two stale entries in the pytest last-failed cache (a removed Phase-193a test id) were confirmed non-collectible and excluded.
- Full suite (final, post-fix): **4838 passed, 14 skipped, 466 subtests passed**, session exit 0; snapshot guard reports `tree_pristine_at_session_start=true`, 0 files added, 0 problems (4852 tests collected). The 14 skips are the pre-existing platform/optional-dependency skips unchanged from the Phase-24 baseline.
- Final manifest: `BUILD_MANIFEST.sha256` regenerated **2423 entries** (baseline 2403 + 20 Phase-25 files), `python scripts/generate_manifest.py --root . --verify` → **`MANIFEST_PASS (0 problems)`** (exit 0), regenerated after the last content write and verified with no subsequent writes.
- Note on the guard: any pytest run between Phase-25 writes and the final manifest regeneration reports `SNAPSHOT_GUARD_TREE_NOT_PRISTINE` and forces session exit=1 even when all tests pass — this is the designed guard (tests/conftest.py), and it cleared once the final manifest was regenerated (verified above).

## 15. Self-check Q&A

1. **What exactly was executed, and against what code revision?** The Phase-18 certified frozen protocol (6 cold-start periods + global run) and the Phase-30 six-period slices, both against delivered bytes at revision `ffefa14`; plus a genuine 10-minute Mode-A REST session and a Mode-B replay session; plus a genuine funding capture.
2. **Is any result on this page from a different code revision?** The Phase-30 recorded counts (21 orders / 3 fills, realized RRs 1.465/1.065/1.577) are from an older revision and are labelled as such; every number presented as current-tree evidence was regenerated this phase.
3. **Was the strategy changed, re-tuned, or re-selected on OOS data?** No. `strategy_parameters_changed=false`; OOS runs are read-only reproductions; the cost ladders are post-trade reporting on frozen fills.
4. **Could the 10-minute session's zero-order outcome hide a bug rather than absent setups?** The delivery audit shows 1445/1445 candles routed and processed with reconciliation PASS, and the Mode-B run exercises the full order/RR-gate/trade path — the zero is a genuine no-setup outcome, not a transport/engine fault.
5. **Is the funding attribution real or assumed?** Real venue settlements, hash-bound to the exact dataset bytes; applied only within holding intervals (none existed); the uncovered head is disclosed, not defaulted.
6. **Do the cost numbers claim venue realism?** No — `CONFIGURED_SIMULATION` / documented assumption; venue fees remain owner-provisioned.
7. **What must the owner do before anything here becomes tradable evidence?** Remediate `.env`, revoke old credentials, provision venue fee schedule + instrument metadata, authorize testnet (P192), and fund a far longer observation window — the 9M protocol still needs ≥60 completed trades.
