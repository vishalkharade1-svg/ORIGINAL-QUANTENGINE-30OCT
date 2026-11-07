# Build handoff — Phase 130 test-baseline triage

Date: 2026-10-12

## Scope

Phase 130 continues from the sanitized Phase 129 full repair archive. Work remained offline: no exchange orders, no exchange network experiments, and no credentials were added.

## Fix implemented: risk-policy API symbol round-trip

The full-suite first-failure run exposed a regression in `TestRiskPolicyApi.test_risk_policy_instrument_round_trip`: internal canonicalization changed the visible key `TEST-API` to `TESTAPI`, breaking the authenticated control API's response contract.

`core/risk/trading_policy.py` now separates canonical lookup keys from operator-facing display keys:

- Formatting variants continue to resolve to one canonical internal key.
- API snapshots and persisted JSON preserve the first configured display spelling.
- Updating an existing policy through a formatting alias does not silently rename the operator-facing key.
- Persisted files containing two instrument keys that collapse to the same canonical key are rejected instead of silently choosing one.
- Reset removes both the policy and its display key.

Added regression coverage for duplicate normalized persisted keys failing closed.

## Verification performed

- Collection: **3,954 tests collected**.
- Focused Phase 129/130 policy, API, backtest-gate, post-cost, environment, and security shard: **113 passed, 2 skipped**.
- First full-suite `-x` run initially found the API display-key regression after 79 passing tests; that regression was fixed and re-tested.
- Second `-x` run: **107 passed**, then stopped at `tests/test_authoritative_path_phase7.py::TestNormalizedStrategyDigest::test_digest_matches_forensic_baseline`. Actual digest `99a47bdd49d96643a0037843f089ddfacdd15da42a0927b0acde04679128f4bc`; expected forensic baseline `9eff61b777846c7f5e2056c486c9c381872a93e154d35160e70f63051c8fd8a2`.
- A 20-minute full-suite attempt reached about 26% and showed failures and setup errors before timing out. It is not a completed full-suite result.
- Python 3.13.5 / pytest 9.0.2 was available in this build environment. This does **not** match the project's documented Python 3.12 pinned environment; reproducibility on the pinned environment remains outstanding.
- `python -m compileall -q core backtesting config research scripts tests`: PASS.
- Security/credential-isolation tests are included in the focused shard. No credential values were inspected or printed by the build procedure.

## Deliberately not changed

The strategy digest baseline was **not** updated. A digest mismatch can indicate meaningful strategy/code drift; changing the expected pin without reviewing lineage and owner approval would hide evidence rather than fix a bug. Related historical head-ancestry, research-dirt, OOS lineage and Gate-A pins remain operator/research reconciliation items.

## Remaining blockers

- Reproduce and disposition the forensic strategy digest mismatch and related lineage pins without blind re-pinning.
- Run the complete suite under the pinned Python/dependency environment and root-cause all failures/setup errors/timeouts.
- Finish execution-economics certification (fees, funding, slippage, simultaneous friction and fill binding).
- Verify Global WebSocket wiring/continuity, reconnect/recovery and private-fill reconciliation with real external evidence.
- Complete strategy out-of-sample lineage reconciliation and independent edge validation.
- Owner-side rotation/revocation of exposed credentials and provider-account review.
- Production readiness remains **FALSE**. No live trading or profitability claim is made.


## Phase 131 follow-up (2026-10-13)

Phase 131 updates how the source archive tests express historical strategy identity. The old digest remains unchanged as a historical reference, but the archive lacks `.git` history and cannot prove it is the exact historical Phase-4 tree. Tests now verify that the current canonical digest is reported consistently and that certification remains `BLOCKED`; the ancestry assertion is skipped only when the original Git checkout is absent. This is not strategy re-certification and does not transfer old OOS findings to the current code.
