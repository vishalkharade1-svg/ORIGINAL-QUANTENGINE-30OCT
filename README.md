# QuantEngine — Sanitized Development Build

This repository is a research, replay, backtesting, and paper-trading development project. **Production/live readiness is NOT established.** Live execution must remain disabled unless the independent readiness gates and external approvals documented in `NEXT_ACTIONS.md` are satisfied.

## Current build status

- Baseline archive: `QuantEngine_PHASE161_RELEASE_CANDIDATE.zip` (SHA-256 `ce95884b5c34c47f19e58c7b02267b8afa49b0bbb871a56785697c5d2230d8f5`).
- Phase 162 builds on Phase 161 by completing full-package forensic auditing, dead code triage, manifest stdout robustness, documentation reconciliation, empirical funding/repeat-match reconciliations, and authoritative test baseline reporting.
- Current test status: 4,065 tests passed, 399 subtests passed, 57 skipped, 5 failed (the deliberate strategy-digest change detectors; see `reports/PHASE162_FAILURE_TRIAGE.json`). Full suite is NOT certified production-ready.
- Historical captures and research artifacts are preserved under recorded provenance; their internal hashes do not independently prove profitable edge.
- Detailed status and gate records: `reports/PHASE162_RELEASE_GATES.json`, `reports/PHASE162_BLOCKERS.json`, `docs/BUILD_HANDOFF_PHASE162.md`.

## Security

- Never place exchange credentials in this repository or an archive.
- Copy `.env.example` to a local `.env` only on a trusted machine; use fresh least-privilege **Testnet-only** keys for testnet work.
- Never mix production and Testnet credentials. India Testnet capture/experiment scripts read only `DELTA_INDIA_TESTNET_API_KEY` and `DELTA_INDIA_TESTNET_API_SECRET`; they do not fall back to generic `DELTA_API_KEY/SECRET`. Do not upload `.env`, credential-bearing scripts, or account exports.
- Any credential previously present in a shared/uploaded archive must be revoked or rotated in the exchange console. This archive intentionally contains no `.env` files or credential-bearing `env/` package.
- `LIVE` is not certified. No network order experiments are authorized by this package.

## Environment and tests

Use Python 3.12 and install the pinned runtime/test dependencies:

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest tests/ -q -p no:cacheprovider --tb=short
```

For the Phase 129 repair regression set:

```bash
python -m pytest tests/test_trading_policy.py tests/test_level4_rr_exit_policy.py tests/test_breakout_policy_erosion_phase99.py tests/test_policy_authority_guard_phase100.py tests/test_simulator_post_cost_gate_13.py -q -p no:cacheprovider --tb=short
```

The test command above does not by itself certify exchange connectivity, execution economics, profitable edge, or production readiness.

## Project map

- `core/` — trading pipeline, risk, execution, paper runtime, evidence and adapters.
- `backtesting/` — historical replay/backtesting.
- `tests/` — offline regression tests.
- `data/fixtures/`, `data/history/`, `research/` — research and capture evidence; provenance limitations are recorded alongside the artifacts.
- `IMPLEMENTATION_STATE.md`, `NEXT_ACTIONS.md`, `project_status.md` — implementation state and unresolved work.
