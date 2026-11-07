# Build handoff — Phase154 (rerun complete; final build next)

## Input (verified)

`QuantEngine_PHASE153_RELEASE_CANDIDATE.zip`, sha256 `eb7c3ba1…91e86`, 55,639,953 bytes, 1,770 entries, `testzip` clean, no traversal/symlinks/secrets/git/mcp.json. 10 nested ZIPs are research data.

## Repairs (all TESTED, focused green)

1. Manifest/provenance: stale 1,692-entry manifest (14 mismatches + 78 uncovered, all traced) replaced by deterministic `scripts/generate_manifest.py` + 4-test contract; provenance v154 (DRAFT until final hash lands).
2. Evidence errors: typed `EmptySymbolWindowError`; both capture scripts fail closed on malformed evidence; 21-test taxonomy green; Phase85 orchestrator fake updated to the new contract.
3. DELETE audit: 21 tests green (canonical bytes, branch-identical signatures, error propagation). No network use.
4. Funding script: `--execute`/`--dry-run` gated, 6 contract tests green. Never executed.
5. MCP: NO file fabricated (absent in all 3 archives + worktree); 5 errors preserved.

## Verification status

- Authoritative env Python 3.12.10 / pytest 8.4.2 (NOT the 3.13.5 audit env).
- Full suite #2 (authoritative Py3.12): 44F/3932P/10S/5E — delta vs Phase149 is the orchestrator fix holding (F→P) plus one manifest-staleness ordering artifact (fixed by regen). No third run needed; remaining 43F+5E are pre-existing pin/env classes.
- Pilot build: 1,784 packed = 1,784 manifest, 0/0/0 (stale — predates final docs).
- Final build: procedure regen → verify PASS → pack with manifest shipped inside → member-by-member coverage assert → detached hash record. Final SHA-256 ONLY in `../RELEASE_HASH_PHASE154.txt` (never inside the hashed set); in-zip provenance carries no self-hash by design (reproducibility proof instead).
- Ledger: commission match holds; funding 0 rows; user_ids restricted.

## Next

Final regen + pack + extracted-package tests + provenance finalization + gate decision on rerun completion. Verdict so far: NOT_PRODUCTION_READY.
