# Build handoff — Phase155 (release consistency repair + security tooling)

## What Phase155 fixed

Phase154's release was **not internally consistent**. Re-checking the
artifact against the worktree (the exact check the Phase154 audit prompt
demands) reproduced three defects — all in Phase154's own output:

1. Worktree ≠ manifest: `generate_manifest.py --verify` failed with
   `mismatch:NEXT_ACTIONS.md` (closeout appended after the final pack).
2. `reports/PHASE154_RELEASE_GATES.json` inside the archive embedded a
   **stale** archive hash (`81a23baa…`) that did not match the real
   archive (`af0fc155…`).
3. Packaged `NEXT_ACTIONS.md` differed from the worktree copy.

## Repairs

- Gates file no longer embeds any archive hash; it points to the detached
  record `../RELEASE_HASH_PHASE154.txt`. Self-reference removed at source.
- Frozen build ordering: **write all text artifacts → regenerate manifest →
  verify → pack → compute detached hash → extract & re-verify.** No writes
  between verify and pack.
- Regression `tests/test_release_consistency_phase155.py` (5 tests) fails
  if any text artifact embeds its own archive hash, if the worktree drifts
  from the manifest, or if the detached record disagrees with the archive.

## Security tooling (gate was BLOCKED, now EXECUTED)

- `pip-audit`: 3 unique advisories in pinned deps (dotenv, pyarrow, pytest)
  — recorded with fix versions; upgrade deferred (no silent bump).
- `bandit`: 80 → 77 findings. B310 urlopen scheme fixed with an
  http/https allowlist + regression tests; B324 SHA1 reviewed and accepted
  (content fingerprints); B105/106/107 false positives.
- Report: `reports/PHASE155_SECURITY_SCAN.md`; gates:
  `reports/PHASE155_RELEASE_GATES.json`.

## Files changed in Phase155

- `core/client/http_client.py`, `core/remote/gateway.py`,
  `scripts/evaluate_evidence_gates.py` (scheme guards + nosec).
- `reports/PHASE154_RELEASE_GATES.json` (stale-hash repair),
  `reports/PHASE155_*.md/json`, `NEXT_ACTIONS.md`, this handoff.
- New tests: `tests/test_release_consistency_phase155.py`,
  `tests/test_url_scheme_guard_phase155.py`.

## Verification

- `python scripts/generate_manifest.py --root . --verify` → `MANIFEST_PASS`.
- Full suite (authoritative): 46F / 3944P / 10S / 0E — the 5 MCP errors
  fixed, 3 manifest-ordering failures resolved by the final rebuild,
  0 regressions. Triage: `reports/PHASE155_TEST_TRIAGE.json`.
- Focused: 39 passed in the worktree, 6 passed for MCP safety, 54 passed
  standalone in the extracted package. Details:
  `reports/PHASE155_VERIFICATION.md`.
- Final archive SHA-256 recorded ONLY in `../RELEASE_HASH_PHASE155.txt`
  (the Phase154 zip is preserved as historical defective evidence).

## Verdict

`NOT_PRODUCTION_READY` — unchanged. Pre-existing pin/env failures and the
economics/security blockers remain. No live trading; no edge claim.

## MCP configuration (resolved)

The operator supplied the authentic `.vscode/mcp.json`; it was restored
verbatim and all six MCP safety tests now pass (gate
`mcp_configuration_contract` → PASS). See
`reports/PHASE155_MCP_CONFIG_RESTORED.md`. `.gitignore` gained a narrow
`!.vscode/mcp.json` negation so the file survives a Git checkout.
