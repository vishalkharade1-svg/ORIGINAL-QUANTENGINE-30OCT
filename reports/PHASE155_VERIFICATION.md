# Phase155 — verification evidence

All numbers below are from actual command output in the authoritative
environment (Python 3.12.10, pytest 8.4.2, Windows 10). No placeholders.

## 1. Full suite (authoritative, final run)

Command: `python -m pytest -q -p no:cacheprovider --tb=short`
Raw output: `reports/PHASE155_FULL_SUITE_RUN2.txt`

```
46 failed, 3944 passed, 10 skipped in 2429.30s (0:40:29)
EXIT:1
```

Zero errors. Delta vs the previous Phase155 run
(`45 failed, 3940 passed, 10 skipped, 5 errors`):

- **−5 errors**: the five `TestMcpConfigTestnetSafe` cases now pass once
  the operator-provided `.vscode/mcp.json` is present.
- **+1 failed**: `test_manifest_hashes_match_bytes`, because the
  `.gitignore` edit landed after the manifest was generated. Same
  staleness class as the other manifest failures — resolved by the final
  rebuild.
- **0 regressions** from the three changed source modules.

Triage (`reports/PHASE155_TEST_TRIAGE.json`), 46 = 23 + 18 + 2 + 3:

| Category | Count | Nature |
|---|---|---|
| hash-or-digest pin | 23 | pre-existing, BLOCKED (needs owner re-pin decision) |
| no-git ancestry | 18 | pre-existing, BLOCKED (no Git history in archive) |
| live `.env` guard | 2 | by design — operator secrets correctly detected |
| manifest ordering | 3 | Phase155 artifact, fixed by final rebuild |

After the final rebuild the expected steady state is **43 failed (all
pre-existing), 3947 passed, 10 skipped, 0 errors**; the three manifest
failures are verified green by focused runs against the rebuilt tree
(§5). A further 40-minute full run would not change the gate verdict
(the remaining 43 are pre-existing and outside this repair), so the
executed run above is reported as-is rather than superseded by a claim.

## 2. Targeted regression suites

- Worktree: `test_release_consistency_phase155`, `test_url_scheme_guard_phase155`,
  `test_release_manifest_phase154`, `test_fill_error_taxonomy_phase154`,
  `test_delta_delete_signing_phase154`, `test_order_script_safety_phase154`,
  `test_policy_symbol_threading_phase132` → **39 passed** (before the MCP change).
- MCP safety: `tests/test_delta_mcp_config_safety.py` → **6 passed**
  (previously 5 errored + 1 passed).
- Touched-module sweep (`-k "client or gateway or evidence_gate or remote
  or http_client or url_scheme"`) → **126 passed, 3875 deselected**.

## 3. Extracted-package verification (standalone)

The Phase155 archive is extracted to a clean directory outside the
worktree and the package-local suites run there with no worktree on the
path. Final build result: **54 passed** across
`test_release_consistency_phase155`, `test_url_scheme_guard_phase155`,
`test_release_manifest_phase154`, `test_delta_mcp_config_safety`,
`test_fill_error_taxonomy_phase154`, `test_delta_delete_signing_phase154`,
`test_order_script_safety_phase154`, `test_policy_symbol_threading_phase132`,
`test_phase85_capture_orchestrator`. The packaged tree also verified
byte-identical to the worktree for `NEXT_ACTIONS.md`, `.vscode/mcp.json`,
`.gitignore` and `BUILD_MANIFEST.sha256`; no `.env`, no `__pycache__`.

## 4. Build

Built with `scripts/build_release.py` (frozen rule: regen manifest →
verify → pack → coverage assert → detached hash):

- members 1805 = manifest entries 1804 + the manifest itself
- coverage: 0 extra, 0 missing
- 0 secret/cache/bytecode violations
- final SHA-256 recorded ONLY in the detached record
  `../RELEASE_HASH_PHASE155.txt` (never inside the archive)

## 5. Consistency contract

`tests/test_release_consistency_phase155.py` (4 tests) passes in the
worktree: worktree verifies against the manifest; no packaged text
artifact embeds the archive's own hash; the detached record agrees with
the archive bytes; no orphaned detached record in an extracted tree.

## Verdict

`NOT_PRODUCTION_READY` — unchanged. The release is internally
consistent and the MCP contract is satisfied; the pre-existing
pin/ancestry failures and the economics/security blockers remain.
