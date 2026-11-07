# Build handoff — QuantEngine Phase 161 dependency-environment candidate

## What was delivered

Phase 161 is a **dependency-environment adoption** cycle: it executes the
deliberate step `BLOCK-160-06` declared as its unblock — the three evaluated
advisory upgrades are adopted and the whole release evidence set is re-derived
under the adopted pins — plus this record set.  If you need the
Phase158/159/160 repair stories, read `docs/BUILD_HANDOFF_PHASE158.md`,
`docs/BUILD_HANDOFF_PHASE159.md` and `docs/BUILD_HANDOFF_PHASE160.md` (all
preserved in-tree).

| Item | Name | Where |
|---|---|---|
| Release candidate | `QuantEngine_PHASE161_RELEASE_CANDIDATE.zip` | beside this tree |
| Detached hash record | `RELEASE_HASH_PHASE161.txt` | beside the archive — **not** inside it |
| Post-build audit (against final bytes) | `PHASE161_SELF_AUDIT.md` | post-build bundle `QuantEngine_PHASE161_POST_BUILD/` |
| Extracted-package run | `PHASE161_EXTRACTED_PACKAGE_TESTS.txt` | post-build bundle |
| Input identity (what this was built from) | `reports/PHASE161_ARCHIVE_INTEGRITY.json` | inside the archive (the sealed Phase160 bytes, hash `83af6cca…`) |
| What changed (complete list) | `reports/PHASE161_SOURCE_DIFF.json` | inside the archive |
| The environment step | `reports/PHASE161_ENVIRONMENT.json` | inside the archive |
| Blockers (unsoftened) | `reports/PHASE161_BLOCKERS.json` | inside the archive |
| Vendor-audit status | `reports/PHASE161_RELEASE_GATES.json` (`independent_audit`) | inside the archive |

Three artifacts cannot live inside the archive because they describe the
archive itself: the hash record, the self-audit against the final bytes, and
the extracted-package test log.  They travel beside it in the post-build
bundle.  `tests/test_release_records_phase161.py` enforces the whole shape.

## The environment step (and nothing else)

1. `requirements.txt` adopts **python-dotenv 1.2.2**, **pyarrow 23.0.1** and
   **pytest 9.0.3** (httpx 0.28.1, websockets 12.0, pandas 2.2.2 and numpy
   2.1.1 carried); the installed environment matches, and
   `tests/test_dependency_pin_contract.py` enforces the agreement with the
   recorded evidence environment.
2. A fresh OSV query against the adopted pins clears every advisory for all
   seven packages (`reports/PHASE161_OSV_SCAN.json`); the reachability greps
   stay in the record and stay clean.
3. The **entire evidence set is re-derived** under the adopted environment:
   the worktree and extracted-package suite runs, both scanners, the dataset
   reconstruction re-check under pyarrow 23.0.1, the manifest and this record
   set.  The Phase160 run numbers remain only as the labelled pre-adoption
   baseline.
4. The release-consistency constants advance to this candidate (routine; no
   lag to repair this time).

The complete changed-file set at seal time is in
`reports/PHASE161_SOURCE_DIFF.json`; every content change maps to one of the
bullets or to this record set.  If it shows anything else, suspect the
delivery.

## Verify a delivery

```
sha256sum  QuantEngine_PHASE161_RELEASE_CANDIDATE.zip    # == detached record
unzip -q   QuantEngine_PHASE161_RELEASE_CANDIDATE.zip -d extracted
cd extracted
python scripts/generate_manifest.py --root . > regen.tmp
python scripts/generate_manifest.py --root . --verify      # MANIFEST_PASS (0 problems)
python -m pytest -q -p no:cacheprovider --tb=short tests/  # see below
```

The manifest is LF-only and regenerates byte-for-byte (carried property).
The suite is **not green by design**: five deliberate strategy-digest
change-detector failures (`BLOCK-161-01`) and 40 Git facts skipped
`BLOCKED_EVIDENCE` (`BLOCK-161-04`) — the same failure set as before, now
re-executed under the adopted environment.  The full worktree run is in
`reports/PHASE161_FULL_SUITE_RUN.txt`; the extracted-package run is in the
post-build bundle.  A session snapshot guard (`tests/conftest.py`) verifies the
tree against the manifest at session start and restores known-rebuilt files, so
a run leaves the tree manifest-valid.

## What did NOT change (by explicit decision)

* The scanner machinery — the Phase160 content-decoding closure and rule E are
  byte-carried; this cycle re-ran the scans, it did not rewrite them.
* The five pinned strategy digests — no re-pin; the documented re-certification
  still requires the original Git checkout (`scripts/recertify_strategy_digest.py`
  returns `STATUS: BLOCKED`).
* The runtime-policy authentic byte pins, the dataset reconstruction and its
  frozen `dataset_hash 4feccebb…`, the frozen LF representations — all carried.
* The sealed Phase160 deliverable — never edited; superseded by this candidate
  and preserved in `_phase160_superseded/` with a lineage README that repairs
  the handoff note's relative-path caveat.
* Nothing else ships: the same member set as Phase160 plus this cycle's
  records; no new strategy, dataset or runtime behavior.

## Operator queue (unchanged, restated)

Vendor-independent audit remains open (`BLOCK-161-05`) — a self-audit (and the
release-side round-2 audit continuation) does not discharge vendor
independence, and **no Phase161 handoff note was prepared** (the Phase160
handoff is preserved in `_phase160_superseded/`).  The Testnet egress-IP
whitelist still blocks public funding/repeat-match evidence
(`BLOCK-161-02/03`); the old account position (`BLOCK-161-06`) waits for the
operator; Indian index options stay untouched by design.  Edge is NOT
ESTABLISHED and `LIVE_ORDER_PLACEMENT` is NOT PERFORMED; no order-capable
script ran in this cycle.  The dependency advisories block (`BLOCK-160-06`) is
closed by this cycle — see `reports/PHASE161_BLOCKERS.json`,
`closed_this_cycle`.
