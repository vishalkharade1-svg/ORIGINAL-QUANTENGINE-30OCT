# Phase 197 — Crash-Safe Testnet Experiment Cleanup Audit

Date: 2026-10-30

## Decision

**IMPLEMENTED AND FOCUSED-TESTED; RELEASE GATE REMAINS HOLD.** The audit found a failure path in `scripts/bounded_testnet_reconciled_experiment.py`: a later-leg exception could prevent `do_legs()` from returning its accumulated `legs` list, losing the acknowledged earlier order IDs before cleanup. Cleanup also ran only after secondary evidence processing, so an earlier processing failure could bypass it.

## Changes

- `scripts/bounded_testnet_reconciled_experiment.py`
  - Added a mutable per-order ownership journal populated immediately after an exchange order ID is acknowledged.
  - Each record retains exchange order ID, client order ID, product ID, and that order's gate decision.
  - The caller now passes the ownership journal into cleanup even when a later placement leg fails.
  - Placement exceptions are recorded and do not trigger automatic order retries.
  - Private WebSocket listener failures are captured as evidence rather than bypassing cleanup.
  - Cleanup runs immediately after capture tasks are stopped and before secondary evidence parsing/archive work.
  - A failed placement and unresolved cleanup are represented explicitly in the evidence status.
- `scripts/bounded_testnet_order_experiment.py`
  - Cleanup now accepts only structured per-order ownership records; bare order IDs are insufficient.
  - Before cancellation, the exchange order-detail response must match the recorded exchange ID, product ID, and client order ID.
  - Unknown/mismatched ownership fails closed; pre-existing orders are not touched.
  - Each cancellation token is minted from the decision retained for that specific order, and is explicitly bound to `DELETE`.
- `tests/test_phase193b_authority.py`
  - Strengthened the later-leg preflight-failure test to prove that the first acknowledged order remains in the cleanup journal.
  - Added an adversarial test proving cleanup refuses cancellation when the exchange-reported client order ID differs from the journal.

## Verification

- Focused authorization, cleanup, lifecycle, crash-recovery, and credential-isolation suite: **132 passed**, 9 subtests passed, 2 multiprocessing fork deprecation warnings, 3.43 seconds.
- Full test collection: **4,879 tests collected** in 6.90 seconds; collection only, not a full-suite pass.
- Python compilation for modified scripts/tests: PASS.
- `scripts/generate_manifest.py --verify`: `MANIFEST_PASS (0 problems)`.
- `scripts/security/scan_secrets.py`: `SECRET_SCAN_PASS`.
- No exchange network calls or order writes were performed; tests used local fakes/mocks.

## Limitations and release gates

- Full repository suite remains NOT RUN in this phase.
- The exact pinned Python 3.12 runtime and all pinned dependencies remain uncertified; the available runtime is Python 3.13.5, pytest 9.0.2, and `pyarrow` is absent.
- This change improves cleanup for acknowledged orders within the running experiment. It does not replace durable restart recovery/reconciliation when an order acknowledgement is ambiguous or the process dies before it can persist the exchange ID.
- The API's order-detail shape must be validated against authoritative testnet evidence before any bounded experiment. Missing client-order IDs intentionally prevent cancellation and require manual reconciliation.
- Operator public-key provisioning, genuine signed authorization, credential rotation/revocation, and account review remain owner-controlled/unverified.
- Strategy edge remains **NOT ESTABLISHED**.

**RELEASE_GATE = HOLD. NOT_PRODUCTION_READY.**
