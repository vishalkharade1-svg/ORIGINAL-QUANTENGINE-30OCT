# QuantEngine Production Hardening — Stages 4–7

**Status: implementation present; integrated CI verification added by this change.**

This continuation consolidates the Stage 4–7 hardening artifacts already present in the repository. It does not authorize live execution, certify strategy edge, or claim out-of-sample performance.

## Stage 4 — Paper certification and sustained-soak invariants

**Existing implementation/evidence:**
- `tests/test_stage4_paper_certification.py` exercises the production pipeline, paper accounting, cost semantics, RR policy, order lifecycle, reconciliation, restart drills, multi-symbol isolation, breakers, determinism, causality, and production/research isolation.
- `tests/test_stage4_soak.py` runs one continuous 30,000-candle paper-path soak, checks ledger identity and finite account/trade values, records resource maxima, checks deterministic reruns, and replays the repository's BTCUSDT parquet fixture.

**Acceptance boundary:** paper-only. The parquet replay is explicitly a normalization/runtime exercise, not an OOS or performance sample. The soak's synthetic candles are operational stress fixtures, not market evidence. A passing soak does not certify profitability.

## Stage 5 — Verified instrument contract and sizing semantics

**Existing implementation/evidence:**
- `core/registry/verified_contract.py` provides `verify_contract_spec` and multiplier-aware `size_quantity`.
- `tests/test_verified_contract_phase5.py` rejects missing product/instrument/contract/tick/quantity/notional/multiplier/settlement/leverage/provenance fields; it also rejects unverified sizing input and quantities below venue minimums.

**Acceptance boundary:** tests use offline fixtures and explicit provenance metadata. They do not establish that current live venue metadata has been freshly fetched or independently verified. Production sizing must continue to fail closed when a verified contract specification is unavailable.

## Stage 6 — Verified market-data gap recovery

**Existing implementation/evidence:**
- `data/delta/verified_socket_transport.py` blocks strategy delivery across a candle gap and only restores continuity after the injected history fetcher supplies the complete missing interval.
- `core/exchanges/delta/delta_history.py::gap_candles` requests only strict interior candle bounds.
- `tests/test_verified_gap_recovery_phase6.py` covers complete backfill, incomplete/missing backfill, and strict endpoint bounds.

**Acceptance boundary:** fixtures use a fake socket and fake history adapter. This is not proof of live Global endpoint availability, venue retention completeness, or successful authenticated operation. Missing or partial history must keep strategy dispatch blocked; candles must never be synthesized to conceal a gap.

## Stage 7 — Durable reconciliation snapshot write

**Existing implementation/evidence:**
- `core/live/reconciler.py::persist` writes a complete JSON snapshot to a same-directory temporary file, flushes and `fsync`s it, then atomically replaces the target.
- `tests/test_reconciler_snapshot_durability_phase7.py` verifies `fsync` is invoked and a fresh reconciler can read the complete snapshot.

**Acceptance boundary:** this proves the tested file-write sequence and readback, not full restoration of every RAM-resident trading subsystem, directory-entry durability across all filesystems, multi-process coordination, or exchange reconciliation after a real crash. A missing, corrupt, or stale journal remains a fail-closed condition; restart must not auto-resume trading.

## Integrated verification

The companion workflow runs the five existing Stage 4–7 test modules and verifies the strict source manifest. It runs on the PR checkout with full Git history. The Stage 4 repository-integrity test requires the local branch name `main`, so CI checks out the exact PR SHA on a local branch named `main`; this does not change the PR's source branch or target.

## Carried-forward release blockers — unchanged

- Historical Delta credential exposure/revocation and any authorized history remediation remain unresolved unless separately evidenced by the operator.
- Production cost defaults remain explicitly zero unless a real, versioned venue cost profile is configured and verified. Zero-cost results are not realistic profitability evidence.
- No new OOS evidence is created by these stages. Strategy edge remains **NOT ESTABLISHED**.
- Live execution remains **NO-GO / NOT_LIVE_READY** while any security, economics, data-quality, or strategy-certification blocker remains. These stages do not enable live mode, contact an exchange, or place/cancel orders.

## Change-control note

No frozen research artifact, strategy threshold, historical hash, credential, or release gate is modified by this continuation. CI results must be reported separately for each test module; skips or missing evidence are not passes.
