# PHASE132 Baseline Inventory — QuantEngine Phase131 archive

Date: 2026-10-15 (UTC)
Root: `F:\vishal 3\latestoriginalquant\QuantEngine_PHASE131_Digest_Evidence_Repair`
Status taxonomy: IMPLEMENTED / EXECUTED / TESTED / VERIFIED / BLOCKED_EVIDENCE / NOT_PRODUCTION_READY

## Environment (EXECUTED)

- Python: 3.12.10 (tags/v3.12.10, MSC v.1943 64-bit AMD64) — matches target 3.12
- OS: Windows-10-10.0.19045-SP0, 64bit WindowsPE
- pytest: 8.4.2 (matches requirements.txt)
- pandas 2.2.2, numpy 2.1.1, websockets 12.0, python-dotenv 1.0.1, pyarrow 18.0.0 — match pins
- DRIFT: httpx installed 0.28.1 vs pinned 0.27.2 (minor, recorded, not changed)
- Git: NOT A REPO (`fatal: not a git repository`) — ancestry UNVERIFIABLE from this archive
- Env vars: no `DELTA_*` / live keys in process env (only `OPENCHAMBER_SKIP_API_COMPRESSION`)
- Secrets on disk: `.env` absent, `env/` absent, `env/.env.py` absent, `*.pyc` 0, `__pycache__` 0, `.pytest_cache` 0

## Source inventory (IMPLEMENTED)

- Python files total: 1116
- core: 437 py files
- tests: 327 files matching `test_*.py` (collection: 3955 tests)
- scripts: 35 py files
- research artifacts: 699 paths under `research/`
- data: 71 paths under `data/`
- docs: 115 paths under `docs/`
- Key docs present: README.md, IMPLEMENTATION_STATE.md, STATUS.md, project_status.md, NEXT_ACTIONS.md, NEXT_ACTIONS_PHASE131.md, LEVEL4_REPORT.md, docs/BUILD_HANDOFF_PHASE129/130/131.md, reports/PHASE129/130/131_VERIFICATION.txt
- Manifest: BUILD_MANIFEST.sha256 with 1692 entries; MANIFEST_SHA256_PHASE131.txt present
- `.env.example` present with blank keys only; `.gitignore` covers `.env`, `env/`, caches, logs, data/history

## Test baseline (TESTED — partial)

- Focused policy shard (secret_scan + trading_policy + level4 + breakout_erosion + authority_guard + simulator_gate + post_cost_rr): **57 passed** in 7.94s
- Phase131 cross-component shard (authoritative_path + digest_recert + continuity_lock + trading_policy + post_cost + simulator_gate + backtester x4): **71 passed, 1 skipped** (skip = Git ancestry absent)
- Collection: **3955 tests collected** (vs 3954 in Phase130 report; +1 delta recorded, not dispositioned)
- Full suite: NOT RUN to completion in Phase132 baseline (historical: 3869 passed / 67 failed per Phase127; NOT GREEN)
- compileall `core backtesting config research scripts tests`: PASS
- Secret scanner worktree scan: PASS (no findings, verified via test + manual grep; only placeholder/test markers and `os.getenv` names present)
- Strategy digest (EXECUTED via `scripts/recertify_strategy_digest.py --json`):
  - canonical: `99a47bdd49d96643a0037843f089ddfacdd15da42a0927b0acde04679128f4bc`
  - forensic Phase-4 ref: `9eff61b777846c7f5e2056c486c9c381872a93e154d35160e70f63051c8fd8a2`
  - recorded research: `c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6`
  - status: BLOCKED (no Git checkout, gate-80 + cost seam deltas, no re-execution)

## Provenance

- No `.git` history in archive — all ancestry/hash-pin claims are UNVERIFIABLE from this artifact alone. No commits fabricated.
- BUILD_MANIFEST vs worktree: 0 missing, 5 mismatched (see PHASE132_FILE_DIFF.json). No extra py files outside manifest.
- Historical research ZIPs retained per Phase131 verification (10 ZIPs); hashes not re-proven as exchange authenticity.

## Priorities (from NEXT_ACTIONS_PHASE131.md, preserved)

1. Restore trusted Git history / source bytes; no history invention.
2. Diff nine strategy files vs historical Phase-4 tree when recoverable.
3. Re-execute preregistered research protocol only after freeze.
4. Reproduce full suite on pinned env; disposition without blanket skips.
5. Continue fee/funding/slippage + WS/private-fill evidence via approved captures only.
6. LIVE disabled until gates pass.

## Verdict

`NOT_PRODUCTION_READY` — baseline established, secrets-free, pinned Python present with one httpx drift noted. Full-suite green, digest re-certification, economics, WS/recovery, and credential-rotation remain BLOCKED. No orders placed. No network calls made in baseline.
