# Phase 25 — Blocker Register

Carried from Phase 24 (`reports/PHASE24_BLOCKER_REGISTER.md`) and updated
with Phase-25 findings. Status taxonomy: BLOCKED / PARTIAL / RESOLVED /
OPEN. Every blocker names its owner-class (OWNER action vs ENGINEERING
action) and the concrete unblock condition.

| # | ID | Status | Owner | Description / unblock condition |
| --- | --- | --- | --- | --- |
| 1 | `EDGE_NOT_ESTABLISHED` | OPEN (evidence-blocked) | ENGINEERING (evidence accumulation) + OWNER (resource decision) | 0 completed trades across the certified OOS span; nine-month protocol requires ≥60 completed trades and 5 surviving periods. Unblock: accumulate a far larger observation window (longer runs, more symbols/timeframes) through the Phase-25 session machinery under the preregistered protocol; NO tuning against OOS. |
| 2 | `.ENV_SECRET` | BLOCKED (owner) | OWNER | Standing secret-scan finding: `.env` lines 1–2 `non_empty_known_secret` (rc=1; values redacted). Unblock: owner empties/rotates the file; re-run `python scripts/security/scan_secrets.py` → rc=0. |
| 3 | `OLD_CREDENTIAL_REVOCATION` | BLOCKED (owner) | OWNER | Revocation of previously exposed credentials cannot be verified from this environment. Unblock: owner confirms revocation/rotation at the venue. |
| 4 | `TESTNET_EXECUTION_NOT_AUTHORIZED` | BLOCKED (owner) | OWNER | Testnet/live-execution authorization decision (P192 prerequisite). Unblock: explicit owner authorization + credentials provisioning. |
| 5 | `P192_BLOCKED` | BLOCKED | OWNER (via 2, 3, 4) | Unchanged: depends on `.env` remediation, credential revocation, and testnet authorization. |
| 6 | `VENUE_FEES_UNKNOWN` | OPEN (owner-provisioned) | OWNER | Delta fee schedule not obtainable from this environment. Current state: conservative `CONFIGURED_SIMULATION` (rate 0.0005 + 5 bps slippage, profile `p25-conservative-assumption`). Unblock: owner provisions real fee numbers and sets `QE_PAPER_COST_VENUE_REALISTIC=true`; until then no venue-realistic cost claim is made. |
| 7 | `DEV_PARTITION_ABSENT` | OPEN (evidence) | OWNER (data provisioning) | Pre-Gate-A development/validation partition is not part of this delivery; dev-partition sensitivity analysis blocked. Unblock: provide pre-boundary history; sensitivity analysis then runs on dev data per the E4 prohibition. |
| 8 | `INSTRUMENT_METADATA_SYNTHETIC_FALLBACK` | OPEN (design limitation) | OWNER | Explicit-cut universe fails closed for derivatives; instruments carry synthetic SPOT fallback metadata (tagged, not derivative-realistic). Unblock: owner provisions genuine instrument metadata. |
| 9 | `PHASE30_REVISION_DIVERGENCE` | DOCUMENTED (not blocking) | ENGINEERING (none required) | Recorded Phase-30 OOS counts (21 orders / 3 fills) do not reproduce at revision `ffefa14` (current: 45 orders / 1 fill on the same slices) — produced by an older code revision. Classified as different-revision evidence; the Phase-22-certified Phase-18 protocol DOES reproduce exactly. No action required; recorded in `research/results/phase25_frozen_oos_validation.json`. |
| 10 | `FUNDING_HEAD_GAP` | RESOLVED (disclosed) | none | First 22,500 s of the OOS window predate the first captured funding settlement. Disclosed in the validation report (`funding_head_gap_seconds`); funding never defaulted to zero over a holding interval. Genuine funding evidence now exists and is hash-bound (Phase-71 blocker RESOLVED). |

## Resolved this phase

- **Phase-71 funding blocker** ("public Delta access previously failed
  with DNS resolution failure") — network reachability re-proven; 502
  genuine hourly settlements captured and strictly bound to the frozen
  market-data bytes (`reports/evidence/phase25/btcusdt_funding_bound_to_oos.json`,
  `..._bound_to_phase18.json`); wired through the strict
  `FundingSchedule` machinery.

## Explicitly NOT blockers

- Session zero-order outcome in the 10-minute Mode-A run: genuine
  no-setup outcome (delivery audit 1445/1445, reconciliation PASS; the
  order/RR-gate/trade path is exercised in Mode B).
- Pytest session exit=1 with `SNAPSHOT_GUARD_TREE_NOT_PRISTINE` before
  the final manifest regen: expected guard behavior, cleared by the
  final `BUILD_MANIFEST.sha256` regeneration at phase close.
