# Security & privacy scan — Phase154 (EXECUTED)

## Secret scan (values never printed)

- Worktree: `SECRET_SCAN_FAIL` on `.env` lines 1–2 (operator-provisioned live Testnet secrets, gitignored, unpackaged). Correct behavior — the 2 guard-test failures prove detection works.
- Extracted input package (`_phase154_extract`): clean — 0 secret files, scanner PASS equivalent (no `.env`, no literals, no private keys).
- Capture dirs (`phase148_funding`, `phase153_ledger`, `phase146/152_recon`): scanner PASS each.
- Research-data ZIPs (10 historical): listed, not extracted for secrets — documented limitation; they predate this repair and are covered by the manifest, not by a fresh scan. Flagged for owner review, not claimed clean.

## Privacy (separate from secret scanning)

- `wallet_100.json`: `user_id` on 33/33 rows + order/fill/client IDs. RESTRICTED evidence; general reports carry aggregates only (counts, sums, effective-bp). No sanitized copy fabricated; raw preserved under research captures.
- Secret-scan PASS on a file does not clear account metadata for distribution — enforced by keeping IDs out of all Phase154 reports.

## Tooling gates

- `pip-audit`/`bandit`: not installed → BLOCKED, not passed.
- TLS: `https://`/`wss://` only, no `verify=False` (re-verified). Testnet/live key separation enforced by script contracts + tests.

## Packaging

- Exclusions enforced and tested: secrets, caches, bytecode, venv, git, logs, prior-candidate ZIPs, forensic extract dir. Final verification runs against the built archive.
