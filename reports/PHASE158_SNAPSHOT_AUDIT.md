# Snapshot audit — Phase 158 (the tree that was packed)

## Scope, stated first

This record audits the **frozen snapshot**: the exact tree state that was handed
to `scripts/build_release.py`. It ships *inside* the archive, so it cannot and
does not audit the archive's own bytes — a file cannot truthfully contain a hash
of the container it travels in. The audit of the final bytes is
`PHASE158_SELF_AUDIT.md` in the post-build bundle beside the archive, together
with `PHASE158_POST_BUILD_VERIFICATION.json` and the extracted-package test log.

Phase157 shipped a self-audit that described a *superseded* build (1,817 members,
sha256 `72fe28e0…`) while the archive beside it was a later 1,820-member rebuild.
That is the defect this split prevents: an in-archive audit must describe the
snapshot it is in, and the archive-level audit must live outside.

## What was verified, and where the evidence is

| claim | evidence record |
|---|---|
| input archive identity (three sources agree) | `reports/PHASE158_BASELINE_INVENTORY.md` §1 |
| extraction byte-verified 1,820/1,820 | `reports/PHASE158_ARCHIVE_INTEGRITY.json` |
| the Phase157 archive is a faithful snapshot of the Phase157 worktree, apart from its `.env` (revision 2's own changes against it are classified in the bundle's `PHASE158_SOURCE_CHANGES.json`) | `reports/PHASE158_SOURCE_DIFF.json` |
| pre-repair baseline, every failure classified | `reports/PHASE158_BASELINE_FULL_SUITE.txt`, `reports/PHASE158_HASH_FAILURE_TRIAGE.json` |
| frozen inputs LF-restored, every recorded pin reproduces | `tests/test_phase158_frozen_representation.py`, `research/phase11f/freeze_manifest.json` |
| dataset reconstruction derivation-checked and disclosed | `tests/test_phase158_dataset_reconstruction.py`, the artifact's own `reconstruction` block |
| 40 Git facts gated, positive control, gate blocked | `reports/PHASE158_GIT_EVIDENCE_STATUS.json`, `tests/test_git_evidence_mode_contract.py` |
| stale records labelled, not rewritten | `reports/PHASE158_PROVENANCE.json`, `tests/test_release_records_phase158.py` |
| manifest complete, deterministic, LF byte-reproducible, snapshot-guarded | `reports/PHASE158_MANIFEST_AUDIT.json`, `tests/test_phase158_manifest_contract.py`, `tests/test_phase158_snapshot_neutrality.py` |
| revision-1 audit findings dispositioned | `reports/PHASE158_AUDIT_REPAIRS.json` |
| no credentials; privacy confinement enforced | `reports/PHASE158_SECURITY_SCAN.md`, `reports/PHASE158_PRIVACY_REVIEW.md`, `reports/PHASE158_PRIVACY_SCAN.json` |
| dependency advisories triaged, not silently adopted | `reports/PHASE158_DEPENDENCY_REVIEW.md`, `reports/PHASE158_OSV_SCAN.json` |
| no order-capable script ran; live placement disabled | `reports/PHASE158_RELEASE_GATES.json`, this snapshot's source review |
| post-repair authoritative run | `reports/PHASE158_FULL_SUITE_RUN.txt` |
| blockers with owners | `reports/PHASE158_BLOCKERS.json` |

## The repairs, in one line each

1. **R1 — missing dataset (10 failures).** `data/history/BTCUSDT_1m_phase19_extension.json`
   was absent from every archive from Phase131 onward. It was reconstructed as
   the first 11,899 rows of `BTCUSDT_1m_oos_topup.json` once its rows are
   ordered ascending by time (the stored topup array is not itself time-sorted;
   the artifact's disclosure states this), verified to reproduce the frozen
   `extended_span.dataset_hash` `4feccebb…`, and the artifact now carries an
   explicit `reconstruction` disclosure block. Not a synthesis: a derivation,
   checked against the commitment that was recorded when the data still existed.
2. **R3/R4 — representation (7 failures).** 15 frozen files had been LF→CRLF
   converted between their mint and Phase131. Each was restored to its
   mint-time bytes and every manifest pin now reproduces exactly. The one
   exception, `research/phase11f/research_log.json`, keeps its **shipped** bytes:
   its pin matches neither the CRLF form nor the LF form (a documented append
   exception), so nothing about it can be verified by restoration, and Phase158
   does not edit what it cannot verify.
3. **R2 — strategy digest (5 failures).** Left red on purpose. The pinned digest
   `c52e648c…` matches no recoverable revision, and
   `scripts/recertify_strategy_digest.py` documents re-certification as requiring
   the original Git checkout plus a research re-execution, returning
   `STATUS: BLOCKED`. These five tests are correct change detectors; re-pinning
   them would destroy the only warning that the strategy identity changed.
4. **Git evidence (19 loud + 21 vacuous).** No `.git` exists anywhere, so
   ancestry cannot be established. All 40 Git-dependent facts are now gated as
   `BLOCKED_EVIDENCE` (never a silent pass), a positive control proves the guard
   steps aside in a real repository, and the ancestry release gate stays
   **BLOCKED**. The 21 that previously passed *vacuously* are the reason this is
   a repair of the evidence contract, not just of 19 red lines.
5. **Stale evidence.** `reports/RELEASE_PROVENANCE.json` was the Phase132 record
   under an ambiguous name; renamed to `RELEASE_PROVENANCE_PHASE132.json` with
   its bytes unchanged, and a Phase158 provenance record written. Phase157's
   self-audit and gates are preserved and labelled as describing the Phase157
   candidate.
6. **Privacy.** The archive is declared a **restricted evidence package**. The
   account identifier is confined to six enumerated raw captures by a scanner
   that enforces set equality; 13 sealed historical journals that quote venue
   order ids are enumerated as a baseline rather than rewritten; zero new
   leakage. Originals are byte-identical to their Phase157 members.
7. **Manifest verifier.** It now reports duplicate and malformed manifest lines
   instead of silently collapsing or raising, with five negative controls.
8. **R5 — post-audit authenticity and neutrality (revision 2).** The
   independent audit of the first build found platform-dependent bytes.
   `data/runtime/risk_policy_overrides.json` was re-drifted to CRLF by every
   Windows-side save; it is restored byte-for-byte to its authentic Phase131 LF
   pin (`a2b9f5c6…`), and `core/risk/trading_policy.py` persistence writes LF
   explicitly so identical policy state serialises to identical bytes on every
   platform. `BUILD_MANIFEST.sha256` is LF-only and regenerates byte-exactly on
   every platform. `tests/conftest.py` adds a session snapshot guard: a test
   run can no longer leave a covered file rewritten, and the
   `SNAPSHOT_GUARD_SUMMARY` line reports every in-run rewrite it neutralised.
   Findings and dispositions: `reports/PHASE158_AUDIT_REPAIRS.json`.

## Focused verification (this snapshot)

```
python -m pytest -q -p no:cacheprovider --tb=short <the eight files covering
  every repaired area, both new contracts and the release-record contracts>
66 passed in 56.85s
```

The revision-2 focused validation is green end to end: the snapshot-neutrality
pins, the manifest contract (byte-exact file and stdout regeneration, plus the
end-to-end pin that the release builder itself packs an LF byte-reproducible
manifest), the privacy contract (including the publication-clearance denial),
the dataset reconstruction ordering, the frozen representation, the release
records, the release consistency and the trading-policy persistence. The five
deliberate strategy-digest failures are change detectors that only the
full-suite files exercise; the complete-suite evidence is
`reports/PHASE158_FULL_SUITE_RUN.txt`, whose `SNAPSHOT_GUARD_SUMMARY` records
the tree pristine before the run, zero restores and no files added by the
suite (4,088 tests collected).

## What this audit does **not** establish

* the archive's own hash (impossible from inside; see the detached record);
* independent verification (see `docs/CLAUDE_PHASE158_INDEPENDENT_AUDIT_PROMPT.md`);
* Git ancestry (blocked, no repository);
* strategy-digest re-certification (blocked by contract);
* funding-through-settlement or repeat-match evidence (blocked, external);
* any economic edge. The edge remains **EDGE NOT ESTABLISHED**, and this archive
  is **NOT PRODUCTION READY**.

Every claim above points at a record that can be recomputed. None of it is a
summary-only claim, and no test was weakened, deleted, blanket-skipped or xfailed
to reach it.
