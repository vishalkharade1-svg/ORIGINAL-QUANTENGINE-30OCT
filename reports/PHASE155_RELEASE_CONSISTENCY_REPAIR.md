# Phase155 — release internal-consistency repair

## Why this phase exists

Phase154 produced `QuantEngine_PHASE154_RELEASE_CANDIDATE.zip`. Re-checking the
artifact against the worktree (the exact check the Phase154 audit prompt asks an
independent auditor to run) found the release was **not internally consistent**.
Three defects, all in Phase154's own output — none in the imported source.

## Defects found (reproduced)

1. **Worktree ≠ manifest.** `python scripts/generate_manifest.py --root . --verify`
   returned `MANIFEST_FAIL (1 problems) — mismatch:NEXT_ACTIONS.md`. The Phase154
   closeout note was appended to `NEXT_ACTIONS.md` *after* the final pack, so the
   manifest (and archive) hash a pre-closeout copy.
2. **Stale hash embedded in a packaged report.** `reports/PHASE154_RELEASE_GATES.json`
   inside the archive declared `final_archive.sha256 = 81a23baa…` while the actual
   archive hash is `af0fc155…`. The value was written during an earlier build and
   never refreshed by the two later rebuilds. A packaged report naming the wrong
   artifact hash is precisely a "stale report" failure.
3. **Worktree ≠ archive for a shipped file.** The packaged `NEXT_ACTIONS.md` did
   not contain the closeout section the worktree had (direct consequence of #1).

## Root cause

Phase154 treated "regenerate manifest → pack" as the final step but then wrote
text artifacts (closeout, gates) *after* packing, and additionally embedded an
archive hash inside the archive itself. Both are ordering/self-reference errors:
a hash of the container cannot live inside the container, and any write after the
pack invalidates the pack.

## Repair

1. `reports/PHASE154_RELEASE_GATES.json` no longer embeds an archive hash. It now
   states the hash is **not embedded** and points to the detached record
   `../RELEASE_HASH_PHASE154.txt`. Self-reference removed at the source.
2. Freeze ordering rule for this and future builds: **write every text artifact
   first → regenerate manifest → verify → pack → compute detached hash → extract
   and re-verify.** No writes to the tree between verify and pack.
3. Rebuild performed under that rule; worktree `--verify` is clean.

## Verification of the repair

- `python scripts/generate_manifest.py --root . --verify` → `MANIFEST_PASS (0 problems)`.
- Rebuilt archive: members = manifest entries + 1 (the manifest itself);
  0 uncovered, 0 missing, 0 secret/cache violations.
- Extracted package: focused regression tests green standalone (see below).
- Packaged `NEXT_ACTIONS.md` byte-identical to worktree; packaged gates file
  contains no archive hash.

Final archive SHA-256 is recorded ONLY in `../RELEASE_HASH_PHASE155.txt`
(detached, non-self-referential), never inside the archive. The Phase155
build is written as `QuantEngine_PHASE155_RELEASE_CANDIDATE.zip`; the
Phase154 zip is preserved as historical (defective) evidence — its
pre-repair hash was `af0fc155…`.

## Status

`IMPLEMENTED` / `EXECUTED` / `TESTED` for the consistency repair.
Overall release verdict unchanged: `NOT_PRODUCTION_READY` (pre-existing pin/env
failures, missing MCP config, and economics/security blockers all remain).
