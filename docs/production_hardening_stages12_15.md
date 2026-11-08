# QuantEngine Production Hardening — Stages 12–15

**Status: additive operational controls; paper-only.** This continuation is stacked on Stages 8–11. It does not enable LIVE mode, contact a venue, write orders, or change strategy thresholds.

## Stage 12 — Scoped cost-profile activation

The activate_cost_profile function validates the venue and instrument scope, profile version, numeric fee inputs, observation time, expiry, source reference, and independent-review reference before constructing a CostSpec.

- A current but not independently venue-verified profile is classified PAPER_SIMULATION_ONLY; its CostSpec.venue_source remains empty.
- A profile marked venue-verified must include an explicit verification reference and is labeled VENUE_VERIFIED_COST_PROFILE.
- Every zero-valued fee component requires its own explicit zero-cost provenance reference. Missing, expired, mismatched, malformed, negative, non-finite, or unprovenanced-zero inputs return BLOCKED with no CostSpec; there is no zero-cost fallback.
- The verification reference is still an external attestation. This code does not authenticate the venue document or reviewer.

This is an adapter to the existing core/risk/costs.py CostSpec authority. It does not mutate global risk settings or silently install a profile into a broker.

## Stage 13 — Paper deployment control

The evaluate_paper_deployment function requires a Stage 11 READY_FOR_INDEPENDENT_RELEASE_REVIEW assessment, explicit live_arming_permitted=False, independent review reference, matching strategy/deployment digests, rollback artifact, paper dry-run receipt, and a tested kill switch.

The strongest result is PAPER_DEPLOYMENT_READY. It is not live approval and does not issue a LiveSafetyGate token. Strategy and deployment identities must both be lowercase SHA-256 digests and match exactly. Any mismatch or missing control is BLOCKED.

## Stage 14 — Tamper-evident audit chain

The make_audit_record and verify_audit_chain functions create and verify a deterministic SHA-256 linked event sequence with contiguous numbering, UTC timestamps, canonical JSON, and previous-record linkage.

- Sensitive attribute names (API keys/secrets, passwords, tokens, private keys, authorization headers, cookies, credential values) are rejected.
- Any changed payload, missing record, sequence gap, or broken link invalidates the chain.
- This stage supplies deterministic records and verification only; it does not persist them. Use the Stage 7 durable snapshot/persistence mechanisms or a separately reviewed append-only store for storage and fsync guarantees.

## Stage 15 — Bounded paper canary and rollback decision

The evaluate_paper_canary function evaluates a closed paper-only observation window against explicit sample, latency, data-gap, rejection, loss, kill-switch, and rollback-artifact controls.

- A clean window yields PAPER_CANARY_PASS.
- An operational breach (including any exchange write) yields ROLLBACK_REQUIRED.
- Incomplete samples, missing controls, malformed timestamps, or invalid metrics yield HOLD.
- live_arming_permitted remains false for every outcome.

Synthetic test cases are control-logic fixtures, not venue performance, profitability, or operational certification.

## Verification

The Stage 12–15 workflow runs the focused test module, compiles the new runtime module, and verifies BUILD_MANIFEST.sha256 in strict mode. These are offline unit and integrity checks; they do not replace full regression, real Testnet drills, independent review, or OOS certification.

## Release posture and remaining blockers

- **PAPER ONLY / RELEASE_GATE HOLD / NOT_LIVE_READY.**
- Stage 8–11 operator attestations remain unverified until evidence is independently checked.
- Venue costs are not considered venue-verified merely because a reference string is present.
- No full runtime integration or deployment to a live environment is performed.
- RR-policy ownership, Stage 4–7 lineage/verification, full regression, source lineage, independent OOS edge evidence, and explicit owner approval remain required.
- No credential bytes or account identifiers belong in these records.

These stages add control-plane evidence and paper deployment checks only. They do not change LiveSafetyGate, TestnetSafetyGate, broker routing, exchange adapters, frozen research artifacts, or live execution configuration.
