# QuantEngine Production Hardening — Stages 8–11

**Status: evidence-gate implementation added; external verification and runtime integration remain blocked.**

These stages continue from the Stage 4–7 hardening work. They add pure, offline evidence evaluators only. They do not read credentials, contact Delta, mutate trading configuration, submit orders, or arm the live runtime.

## Stage 8 — Credential incident closure evidence

**Implementation:** `core/governance/production_hardening.py::evaluate_credential_incident`.

The evaluator accepts only non-secret references and boolean attestations: provider revocation ticket, account-activity review, replacement credential reference, Testnet-only and least-privilege scope, secret-store reference, secret-scan result, independent-review reference, and UTC attestation time.

**Acceptance boundary:** structurally complete operator evidence is labeled `ATTESTATION_COMPLETE_UNVERIFIED`, never `VERIFIED`. The evaluator cannot prove that a provider actually revoked a key or that account activity was fully reviewed. The owner must perform rotation/revocation and obtain provider-side evidence; never paste secrets into the repository or this evaluator.

## Stage 9 — Venue economics evidence

**Implementation:** `evaluate_venue_cost_evidence`.

Requires versioned per-venue and per-instrument commission/slippage values, source reference, observation timestamp, independent-review reference, and an integrated funding-cost model. Explicit zero for an individual fee component is permitted only with provenance; zero is not silently treated as realistic economics.

**Acceptance boundary:** a complete record is labeled `COST_EVIDENCE_COMPLETE_UNVERIFIED`. This stage does not replace or mutate `core/risk/costs.py::CostSpec`, and does not wire a new profile into paper/live fills. Independent validation and production accounting integration are still required. Any omitted venue cost component remains a release blocker.

## Stage 10 — Restart recovery decision

**Implementation:** `evaluate_restart_recovery`.

Requires a SHA-256 journal identity, schema version, bounded snapshot age, complete paginated read-only exchange snapshot (balances, positions, open orders, fills), matching local/exchange identity and state digest, zero unresolved orders, zero anomalies, and an active kill switch.

**Acceptance boundary:** a clean record yields only `PAPER_RECOVERY_ONLY`. Stale, incomplete, divergent, anomalous, or ambiguous state is `BLOCKED`. The evaluator never authorizes automatic restart or live resumption. Full RAM-state restoration and production exchange reconciliation remain unproven.

## Stage 11 — Aggregate release review

**Implementation:** `evaluate_release_gate`.

Aggregates Stages 8–10 plus RR-policy reconciliation, source-lineage verification, full-regression status, an independently reviewed OOS certificate, matching frozen/evaluated strategy digests, evidence that edge is established by OOS, and an operator approval reference.

**Acceptance boundary:** missing or contradictory evidence yields `HOLD`. A complete set of supplied fields yields only `READY_FOR_INDEPENDENT_RELEASE_REVIEW`; it does not yield GO and `live_arming_permitted` is always false. External attestations are not independently verified by this pure evaluator, and it is not wired into `LiveSafetyGate`.

## Verification

`tests/test_production_hardening_stages8_11.py` exercises missing, stale, divergent, malformed, and complete-evidence cases. The companion workflow runs that suite and strict source-manifest verification. These tests are offline unit tests, not venue validation or strategy/OOS evidence.

## Carried-forward blockers

- Provider-side credential revocation and account-activity review remain operator tasks until independently evidenced.
- Production cost configuration and full funding/borrow/liquidation economics remain unverified until connected to the real accounting path.
- Full restart restoration and authoritative exchange reconciliation remain unverified.
- The Stage 1–3 / Stage 4–7 RR-policy description and current runtime policy must be explicitly reconciled.
- Strategy edge remains **NOT ESTABLISHED** until a valid, independent OOS protocol and certificate support it.
- **Release gate remains HOLD / NOT_LIVE_READY. Live trading remains disabled.**

## Scope discipline

No secrets, frozen research artifacts, strategy thresholds, historical hashes, venue state, or live-execution settings are changed by these stages. No external action or order write is performed.
