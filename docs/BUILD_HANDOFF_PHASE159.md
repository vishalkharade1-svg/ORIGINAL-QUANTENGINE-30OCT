# Build handoff — QuantEngine Phase 159 hardened candidate

## What was delivered

Phase 159 is a **hardening-only** cycle: it does exactly the three observations
left open by the Phase158 revision-2 self-audit (plus this record set), and
everything else is carried, not re-derived.  If you need the full Phase158
repair story, read `docs/BUILD_HANDOFF_PHASE158.md` (preserved in-tree).

| Item | Name | Where |
|---|---|---|
| Release candidate | `QuantEngine_PHASE159_RELEASE_CANDIDATE.zip` | beside this tree |
| Detached hash record | `RELEASE_HASH_PHASE159.txt` | beside the archive — **not** inside it |
| Post-build audit (against final bytes) | `PHASE159_SELF_AUDIT.md` | post-build bundle `QuantEngine_PHASE159_POST_BUILD/` |
| Extracted-package run | `PHASE159_EXTRACTED_PACKAGE_TESTS.txt` | post-build bundle |
| Input identity (what this was built from) | `reports/PHASE159_ARCHIVE_INTEGRITY.json` | inside the archive (the sealed revision-2 bytes, hash `b283332a…`) |
| What changed (complete list) | `reports/PHASE159_SOURCE_DIFF.json` | inside the archive |
| The three hardening repairs | `reports/PHASE159_HARDENING.json` | inside the archive |
| Blockers (unsoftened) | `reports/PHASE159_BLOCKERS.json` | inside the archive |
| Vendor-audit status | `reports/PHASE159_RELEASE_GATES.json` (`independent_audit`) | inside the archive |

Three artifacts cannot live inside the archive because they describe the
archive itself: the hash record, the self-audit against the final bytes, and
the extracted-package test log.  They travel beside it in the post-build
bundle.  `tests/test_release_records_phase159.py` enforces the whole shape.

## The three hardening repairs (and nothing else)

1. `scripts/security/scan_secrets.py` decodes every file with `utf-8-sig`, so a
   BOM on line 1 can no longer hide a credential assignment
   (`AUD-OBS-158-01`; regression: `test_bom_prefixed_first_line_secret_is_found`).
2. `scripts/generate_manifest.py` reports a manifest-listed file that is absent
   from disk as `missing:` — the old `manifest-extra:` label read inverted —
   and the stale compensation branch is gone; detection is unchanged
   (`AUD-OBS-158-02`; the contract test now pins the exact label).
3. `tests/test_phase158_privacy_contract.py` fixtures use the synthetic id
   `9000001234` instead of a real harvested venue order id
   (`AUD-OBS-158-03`); the test states the fixture-synthetic rule and the value
   was verified against the harvested id set.
4. Alongside, `scripts/security/scan_privacy.py`'s line reader got the same
   BOM hardening, with its own regression test.

The complete changed-file set at seal time is in
`reports/PHASE159_SOURCE_DIFF.json`; every content change maps to one of the
four bullets or to this record set.  If it shows anything else, suspect the
delivery.

## Verify a delivery

```
sha256sum  QuantEngine_PHASE159_RELEASE_CANDIDATE.zip    # == detached record
unzip -q   QuantEngine_PHASE159_RELEASE_CANDIDATE.zip -d extracted
cd extracted
python scripts/generate_manifest.py --root . > regen.tmp
python scripts/generate_manifest.py --root . --verify      # MANIFEST_PASS (0 problems)
python -m pytest -q -p no:cacheprovider --tb=short tests/  # see below
```

The manifest is LF-only and regenerates byte-for-byte (revision-2 property,
carried).  The suite is **not green by design**: five deliberate
strategy-digest change-detector failures (`BLOCK-159-01`) and 40 Git facts
skipped `BLOCKED_EVIDENCE` (`BLOCK-159-04`).  The full worktree run is in
`reports/PHASE159_FULL_SUITE_RUN.txt`; the extracted-package run is in the
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
  re-verified fresh (OSV query in `reports/PHASE159_OSV_SCAN.json`), not changed.
* The sealed Phase158 revision-2 deliverable — never edited; superseded by this
  candidate and preserved in `_phase158_audited/`.

## Operator queue (unchanged, restated)

Vendor-independent audit remains open (`BLOCK-159-05`) — a self-audit does not
discharge vendor independence; the revision-2 handoff note beside the delivery
still applies to this candidate byte-for-byte with the names swapped.  The
Testnet egress-IP whitelist still blocks public funding/repeat-match evidence
(`BLOCK-159-02/03`); the old account position (`BLOCK-159-07`) waits for the
operator; Indian index options stay untouched by design.  Edge is NOT
ESTABLISHED and `LIVE_ORDER_PLACEMENT` is NOT PERFORMED; no order-capable
script ran in this cycle.
