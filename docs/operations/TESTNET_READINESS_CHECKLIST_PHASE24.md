# Testnet Readiness Checklist (Phase 24)

Status at delivery: **TESTNET_EXECUTION = NOT AUTHORIZED.** Nothing below
may be marked complete by the engine itself; every owner step requires
evidence the owner produces and accepts. This checklist is the exact
dependency map between "paper-only today" and "a testnet session could be
attempted" — completing it changes nothing by itself; the gate flips only
by owner decision recorded in a future phase report.

## A. What is already verified (no owner action needed)

| Item | Evidence |
|---|---|
| Verified public-candle transport seam (finality + continuity + fail-closed bridge) | `tests/test_verified_public_candle_transport.py` (11/11), `tests/test_verified_transport_replay_phase24.py` (35/35) |
| E2E delivery through the real paper assembly (captured + synthetic, faults, recovery) | `tests/test_verified_transport_replay_phase24.py`; sample reports `reports/PHASE24_REPLAY_EXAMPLE/*.json` |
| Sustained soak: 12,000 frames, 11,999/11,999 routed, zero errors, ledger reconciled | `reports/PHASE24_REPLAY_EXAMPLE/soak_12000_seed11.json` (EXIT=0) |
| Disconnect/reconnect recovery without duplicate fills; outage frames fail-closed | `TestInterruptionRecovery` |
| Gap block + exact repair semantics; repaired history never routed | `TestFaultInjectionPolicy` |
| Risk floors enforced in the real chain (runtime policy + frozen 1:6) | `TestIntegratedRiskEnforcement`; `ORDER_SKIPPED_RR` site `core/risk/risk_engine.py:486-496` |
| Paper ledger reconciliation identity holds exactly | `reconcile_paper_ledger` in every clean report |
| Testnet safety gate exists and is evidence-gated | `core/execution/testnet_safety_gate.py` (`TestnetSafetyGate.evaluate`), `test_phase193a_execution_safety_gate.py` |

## B. Owner prerequisites (each blocks testnet until complete)

- [ ] **B1 — Credential remediation (hard blocker).**
      `CREDENTIAL_EXPOSURE_REMEDIATION = OPEN/NOT VERIFIED`: the exposed
      credentials must be rotated/revoked by the OWNER on the venue, and
      the revocation evidence must be produced by the venue (not the
      repository). Also: `OLD_CREDENTIAL_REVOCATION = NOT VERIFIED`.
- [ ] **B2 — Sandbox credentials issued fresh for testnet only.**
      Sandbox keys (`DELTA_SANDBOX_API_KEY` / `DELTA_SANDBOX_API_SECRET`,
      `config/settings.py:49-50`) must be NEWLY issued, bound to the
      testnet environment, and never shared with any production key.
- [ ] **B3 — Testnet execution gate posture.**
      `TestnetSafetyGate.evaluate` must be exercised against the REAL
      venue's testnet config and return the decision the owner intends;
      no simulated or offline pass-through is acceptable.
- [ ] **B4 — Operator socket pump for the paper seam, run against the
      venue's TESTNET public stream, observed for the full capture bar.**
      The paper seam is verified; the pump is the owner's operational
      piece. The venue's public channel should be captured (schema
      `quantengine.delta-public-capture.v1`) and its evidence class kept
      honest (CAPTURED).
- [ ] **B5 — Verified runtime evidence gates.** The Phase-4
      `verified_socket_transport` evidence bar (documented in
      `docs/operations/PHASE85_DELTA_TESTNET_CAPTURE.md`) remains the
      canon for which captures count; a new capture must pass the same
      verifier (`scripts/verify_delta_global_evidence.py`).
- [ ] **B6 — Owner paper-session evidence first.** At least one full
      owner-run paper session (per the runbook) with a kept report and a
      manual reconciliation review, BEFORE testnet. The runbook is
      `docs/operations/PAPER_SESSION_RUNBOOK_PHASE24.md`.
- [ ] **B7 — Risk floor decision recorded.** The owner must record which
      RR floor applies on testnet: the frozen 1:6 era gate (via
      `QUANTENGINE_FROZEN_OOS=1`) or a runtime policy floor (default
      1:1, editable). Either is enforced; mixing them without recording
      is an audit failure.
- [ ] **B8 — Fill/economics expectations frozen in writing** before the
      first testnet fill (what commissions/slippage the venue's testnet
      actually applies and what "correct" looks like), so post-session
      review compares against a pre-registered expectation.

## C. In-session testnet duties (once, and only once, B is complete)

- [ ] Verify the safety banner shows the testnet posture at startup; any
      mismatch = stop immediately.
- [ ] Confirm every order's RR floor was enforced at the correct site
      (`SETUP_REJECTED`/`ORDER_SKIPPED_RR` trails) before trusting fills.
- [ ] Keep the capture journal of the testnet session; reconcile the
      ledger after every stop; keep the report JSONs.
- [ ] No production credentials in the process at any time; the venue
      binds keys to environments and the authority refuses substitution.

## D. Explicit non-goals

- Completing this checklist does NOT establish edge (`EDGE = NOT
  ESTABLISHED` is a research verdict, not an execution-state matter).
- Nothing here authorizes LIVE execution (`ALLOW_LIVE` stays unset;
  the live gate requires its own conditions, all owner-held).
- The legacy `reports/UNRESOLVED_BLOCKERS.json` register stays as-is;
  the Phase-24 view of open items lives in
  `reports/PHASE24_BLOCKER_REGISTER.md`.
