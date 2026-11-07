# Build handoff — QuantEngine Phase 160 scanner-boundary candidate

## What was delivered

Phase 160 is a **scanner-boundary closure** cycle: it does exactly the boundary
the Phase159 vendor-audit handoff declared (`PHASE159_AUDIT_HANDOFF.md`,
preserved with the superseded delivery in `_phase159_superseded/`), plus this
record set, and everything else is carried, not re-derived.  If you need the
Phase158/159 repair stories, read `docs/BUILD_HANDOFF_PHASE158.md` and
`docs/BUILD_HANDOFF_PHASE159.md` (both preserved in-tree).

| Item | Name | Where |
|---|---|---|
| Release candidate | `QuantEngine_PHASE160_RELEASE_CANDIDATE.zip` | beside this tree |
| Detached hash record | `RELEASE_HASH_PHASE160.txt` | beside the archive — **not** inside it |
| Post-build audit (against final bytes) | `PHASE160_SELF_AUDIT.md` | post-build bundle `QuantEngine_PHASE160_POST_BUILD/` |
| Extracted-package run | `PHASE160_EXTRACTED_PACKAGE_TESTS.txt` | post-build bundle |
| Input identity (what this was built from) | `reports/PHASE160_ARCHIVE_INTEGRITY.json` | inside the archive (the sealed Phase159 bytes, hash `015a3be8…`) |
| What changed (complete list) | `reports/PHASE160_SOURCE_DIFF.json` | inside the archive |
| The three repairs | `reports/PHASE160_HARDENING.json` | inside the archive |
| Blockers (unsoftened) | `reports/PHASE160_BLOCKERS.json` | inside the archive |
| Vendor-audit status | `reports/PHASE160_RELEASE_GATES.json` (`independent_audit`) | inside the archive |

Three artifacts cannot live inside the archive because they describe the
archive itself: the hash record, the self-audit against the final bytes, and
the extracted-package test log.  They travel beside it in the post-build
bundle.  `tests/test_release_records_phase160.py` enforces the whole shape.

## The three repairs (and nothing else)

1. `scripts/security/text_decode.py` (new) decides the encoding by the bytes —
   UTF-8 with optional BOM, UTF-16 LE/BE with or without BOM, UTF-32 with BOM;
   anything else is classified binary and never guessed at.  Both scanners now
   select members by content, closing the boundary the Phase159 handoff
   declared: the 12 carried UTF-16LE members and the suffix-excluded members
   came inside every content rule (`REP-160-01`, `REP-160-02`).
2. The privacy scanner adds **rule E — content coverage**: every member is
   content-inspected or a declared opaque class (`*.zip`, `*.parquet`), and an
   undeclared binary member fails the scan; the report schema advances to
   `quantengine.privacy-scan.v2` with a `content_coverage` block.
3. The release-consistency constants in
   `tests/test_release_consistency_phase155.py` advance to this candidate
   (they had lagged one phase; the live cross-check was degraded to its
   absence-invariant branch) and the checked record list grew (`REP-160-03`).

Ten regressions pin the closures (five per scanner), each fixture asserting
its own bytes first.  The complete changed-file set at seal time is in
`reports/PHASE160_SOURCE_DIFF.json`; every content change maps to one of the
bullets or to this record set.  If it shows anything else, suspect the
delivery.

## Verify a delivery

```
sha256sum  QuantEngine_PHASE160_RELEASE_CANDIDATE.zip    # == detached record
unzip -q   QuantEngine_PHASE160_RELEASE_CANDIDATE.zip -d extracted
cd extracted
python scripts/generate_manifest.py --root . > regen.tmp
python scripts/generate_manifest.py --root . --verify      # MANIFEST_PASS (0 problems)
python -m pytest -q -p no:cacheprovider --tb=short tests/  # see below
```

The manifest is LF-only and regenerates byte-for-byte (carried property).
The suite is **not green by design**: five deliberate strategy-digest
change-detector failures (`BLOCK-160-01`) and 40 Git facts skipped
`BLOCKED_EVIDENCE` (`BLOCK-160-04`).  The full worktree run is in
`reports/PHASE160_FULL_SUITE_RUN.txt`; the extracted-package run is in the
post-build bundle.  A session snapshot guard (`tests/conftest.py`) verifies the
tree against the manifest at session start and restores known-rebuilt files, so
a run leaves the tree manifest-valid.

## What did NOT change (by explicit decision)

* The five pinned strategy digests — no re-pin; the documented re-certification
  still requires the original Git checkout (`scripts/recertify_strategy_digest.py`
  returns `STATUS: BLOCKED`).
* The runtime-policy authentic byte pins, the dataset reconstruction and its
  frozen `dataset_hash 4feccebb…`, the frozen LF representations — all carried.
* The dependency pins and the `ACCEPTED_RISK_DEFERRED` advisory decision —
  re-verified fresh (OSV query in `reports/PHASE160_OSV_SCAN.json`), not changed.
* The sealed Phase159 deliverable — never edited; superseded by this candidate
  and preserved in `_phase159_superseded/` with a lineage README that repairs
  the handoff note's relative-path caveat.
* Nothing else ships: the same member set as Phase159 plus this cycle's
  records and the two scanner changes; no new strategy, dataset or runtime
  behavior.

## Operator queue (unchanged, restated)

Vendor-independent audit remains open (`BLOCK-160-05`) — a self-audit does not
discharge vendor independence, and **no Phase160 handoff note was prepared**
(the Phase159 note is preserved in `_phase159_superseded/`; its declared
boundary is closed here, and the closure claims are what to verify).  The
Testnet egress-IP whitelist still blocks public funding/repeat-match evidence
(`BLOCK-160-02/03`); the old account position (`BLOCK-160-07`) waits for the
operator; Indian index options stay untouched by design.  Edge is NOT
ESTABLISHED and `LIVE_ORDER_PLACEMENT` is NOT PERFORMED; no order-capable
script ran in this cycle.
