# Phase 24 Blocker Register

Scope: the verified-transport replay, paper-session readiness and
operational-evidence work of Phase 24. This register is ADDITIVE to the
legacy `reports/UNRESOLVED_BLOCKERS.json` (which stays untouched as the
historical record); it restates the standing gates with their current,
verified dispositions and adds the Phase-24 findings.

Overall posture: `NOT_PRODUCTION_READY` (unchanged). Paper-session
operation is READY (evidence delivered); testnet remains NOT AUTHORIZED.

## 1. Standing gates (unchanged, verified this phase)

| Gate | Status | Verified how this phase |
|---|---|---|
| RELEASE_GATE | HOLD | full regression set re-run (Phase-23 suites 15/15; realtime battery 43/43; Phase-24 suite 35/35) — no gate weakened |
| EDGE | NOT ESTABLISHED | out of scope for execution work; no economics claim made |
| TESTNET_EXECUTION | NOT AUTHORIZED | checklist `docs/operations/TESTNET_READINESS_CHECKLIST_PHASE24.md` — every owner prerequisite open |
| P192 | NOT VERIFIED/BLOCKED | unchanged; no P192 surfaces touched |
| CREDENTIAL_EXPOSURE_REMEDIATION | OPEN/NOT VERIFIED | venue-side owner action; no credentials exist in the paper path |
| OLD_CREDENTIAL_REVOCATION | NOT VERIFIED | venue-side owner action |

## 2. Carried blockers (unchanged dispositions)

| ID | Class | Disposition |
|---|---|---|
| B01 | git-history access limitation | BLOCKED (operator-side tooling) |
| B02 | digest pinning BLOCKED | BLOCKED (operator-side tooling) |
| B03 | gate-A FAIL nodes | FAIL standing (not touched this phase) |
| B04 | credential rotation | BLOCKED — owner action on the venue |
| B05 | economics / edge | BLOCKED — `EDGE = NOT ESTABLISHED`; execution work cannot establish it |
| B06 | ws-recovery private-track evidence | BLOCKED — private-track live evidence remains owner-side |
| B07 | formal scans missing tools | BLOCKED — scanner runs in-repo (rc=1 fail-closed posture); external tool formalization stays owner-side |

## 3. Phase-24 findings

| ID | Finding | Disposition | Evidence |
|---|---|---|---|
| P24-1 | `notify_down` retained subscriptions: every worker reconnect retry failed forever with "symbol ... is already registered" (worker churned in RECONNECTING while deliveries continued through the still-registered callback) | **RESOLVED this phase** — `notify_down` now fans out `on_down` AND tears down the affected registrations; frames during the outage are counted `unrouted` (fail-closed, never queued); the worker's scheduled retry re-subscribes and restores LIVE | probe-backed fix; `tests/test_verified_public_candle_transport.py::test_notify_down_fans_out_tears_down_and_resubscribe_restores`; `tests/test_verified_transport_replay_phase24.py::TestInterruptionRecovery` |
| P24-2 | Gap-repair validator requires window-ALIGNED candle starts (`stamp % window == 0`) while the live stream admits unaligned starts (it only compares adjacency) | DOCUMENTED (repair is stricter — fail-closed; no production change; synthetic fixtures now generate aligned starts like real captures) | `DeltaPublicEventStream.repair_historical_candles` vs `CandleContinuityTracker.ingest`; probe + `TestFaultInjectionPolicy` |
| P24-3 | The paper seam is deliberately caller-driven; no built-in public-socket pump ships for the paper path | DOCUMENTED as an owner dependency (runbook §3); offline replay + soak are the verified ways to operate sessions today | `data/realtime/verified_transport.py:15-18` docstring; runbook |
| P24-4 | `DecisionEngine.accepted` holds only the CURRENT cycle's accepts (cleared at each analyze) | DOCUMENTED (by design; the cumulative trail lives in the production log verdicts and the harness's cycle accumulator) | `core/setup/decision_engine.py::analyze`; harness `ReplayReport.risk` |

## 4. What would close the posture (owner decisions, in order)

1. B04/B01 revocation + rotation evidence from the venue.
2. Owner paper session per the runbook, with kept reports.
3. Testnet checklist items B2–B8 with owner-produced evidence.
4. A future phase decision on economics (B05) — execution evidence
   does not and cannot substitute for a research edge verdict.
