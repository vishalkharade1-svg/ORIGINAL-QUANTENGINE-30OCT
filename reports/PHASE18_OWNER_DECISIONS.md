# PHASE 18 OWNER DECISIONS — MUTUALLY EXCLUSIVE OPTIONS AND REPAIR CANDIDATES
Date: 2026-10-23
Status: ALL proposals. Nothing is applied. Cross-evidence: reports/PHASE18_LINEAGE_EVIDENCE.md (forensic base),
reports/PHASE17_FINAL_REPORT.md, reports/PHASE16_OWNER_DECISIONS.md (superseded letterboxes).

## MASTER TRADE-OFF: what each option buys, in one line

- Option A restores the ORIGINAL (secret-bearing) history — PROVEN to exist, but poisoning of any
  published artifact is immediate if any object bundle ever leaves the workstation.
- Option B keeps the adopted (decontaminated) lineage and re-labels the tests to match reality —
  resolves every 11g/closure ancestry-red without git mutation and without restoring secrets.
- Option C stays fully blocked, preserving all evidence but keeping the 21-node redness forever.

## OPTION A — recover authoritative lineage (restore the original chain as main's history)

- Evidence FOR: the dangling 154-commit chain exists and is fully traversable; the closure tree and
  the 11g-seed trees are tree-equal to the adopted chain's aligned positions; the subject chain
  154/154 matches.
- Evidence AGAINST: the original chain carries `.env` tree states in 114 commits (4 distinct blob
  generations). Any recovery that RE-ROOTS main to the original chain would (a) reintroduce
  those trees into every future clone/fetch/bundle of the repository, (b) invalidate the current
  decontaminated ancestry that the shipped phase reports referenced, and (c) require
  re-basing/exact re-creation of the 41 post-closure commits onto the original chain (new commit
  objects; the current tests still would NOT turn green automatically because the re-based tip
  hashes would differ from both lineages' pin values consulted to date).
- Security + research-integrity risk: HIGH (secret republication risk; genealogy-of-evidence
  churn for every phase document that referenced lineage digests).
- Exactly what would change: refs/heads/main would be rewritten (history-rewrite class operation),
  every downstream phase report's provenance facts would be re-anchored.
- Reversibility: refs mutation is reversible via a marker branch (e.g. `git branch backup-main-…`
  BEFORE the rewrite) but the ORIGINAL chain (with secrets) would then be LIVE in the tree.
- Validation needed post-approval: fresh full-suite run + re-run of all nine ancestry nodes +
  scanner re-verification + a release-wide repack check.
- Remaining-blocked items after this action: NONE lineage-related de jure (~9 ancestry nodes
  potentially green), but the whole secret-exposure count would RISE.
- Verdict: NOT RECOMMENDED in this form. The original history's context value is already captured
  in this evidence file; restoring it to 'main' identity buys nothing that Option B does not buy
  more safely.

## OPTION B — formally re-register the canonical baseline at the ADOPTED (scrubbed) lineage — RECOMMENDED

- Evidence FOR: the adopted chain is (i) confirmed the current effective baseline by 18 local
  commits of certified phase work plus a manifest-verifiable worktree, (ii) proven subject- and
  tree-aligned to the original for the 40 mid/late positions including ALL 8 11g seed positions
  (idx 143..150) and the Stage-123 closure (idx 153), and (iii) FREE of any `.env` tree — 0/195.
- Exact changes proposed (none applied):
  1. `tests/test_researcher_11g_n/o/p/q/r/s/t/u.py` + `tests/test_stage4_paper_certification.py`:
     replace the 9 seed hex IDs with the equivalent positions on the ADOPTED chain
     (11g_n -> acab874d1a, 11g_o -> 5c95fd623f, 11g_p -> 6a961459ae, 11g_q -> e1483a1090,
     11g_r -> bd21e9ac06, 11g_s -> d77af19e85, 11g_t -> e235663d2a, 11g_u -> 0e4d3f04ce,
     closure_tip -> b42e8181406). Each replacement preserves the historical contract (the tests
     keep asserting ancestry: 'must descend from the phase's seed'), just at the correct object.
  2. A provenance record (`reports/PHASE18_BASELINE_REREGISTRATION.json` — designed, NOT created)
     pairing ORIGINAL object IDs with the REPLICA object IDs and the verification basis
     (subject equality 154/154, timestamp equality, tree equality for positions 114..153), plus
     the statement 'original chain preserved in place; not reachable from any ref; secrets carried
     by early positions'.
- Security/research-integrity risk: LOW — the original objects stay in place untouched and
  unreachable; no publishable artifact changes; the re-registration makes the SHIPPED tests reflect
  the ACTUAL effective lineage. Preserves the audit trail because every historical ID remains
  documented in the provenance record and in PHASE18_LINEAGE_EVIDENCE.md.
- Exactly what would change: 9 test-file hex values + a new JSON provenance record. Nothing else.
- Reversibility: full (revert the 9 test-file edits; delete the JSON record).
- Validation needed post-approval: (a) rerun the 9 ancestry nodes individually; (b) rerun the
  16 freeze/status nodes after the research/ freeze items are separately resolved (unchanged here);
  (c) fresh full-suite run to re-baseline the census (expected drop: 9 nodes), (d) manifest
  regen + verify.
- Items this does NOT resolve (stay blocked, tracked separately): 16 research-freeze/status
  nodes (working tree 'M' on research/ paths); F5b offender policy (owner structural decision);
  F4 (candidate patch ready; needs owner approval); B-01 digest re-registration (blocked by
  the 6 modified strategy files — separate owner action); the D-16 loss-limited items
  P192 / testnet signature / revocation / history remediation.
- Verdict: RECOMMENDED — cheapest, safest, evidenced.

## OPTION C — remain blocked (preserve everything as-is)

- Evidence FOR: no gate requires turning the ancestry nodes green today; the release posture stays
  fail-closed; all evidence is preserved as-is.
- Evidence AGAINST: 21 lineage/freeze nodes stay red permanently; every future phase report pays
  the census-carried explanation cost repeatedly; the B-01/F4/PATCH-3 decisions remain pending
  regardless.
- Security risk: NONE new. Research risk: NONE new.
- Exactly what would change: NOTHING in the tree; only these documents become the standing record.
- Reversibility: trivially of no effect.
- Validation needed: none.
- Remaining blocked: everything currently blocked stays blocked.
- Verdict: the DEFAULT-with-cost path; use if the owner prefers absolute non-interference this cycle.

## SERVICE-LEVEL CANDIDATE STATUS TABLE (per Work-stream D, separately assessed)

| id | candidate | reproduced where? | state | blocked by |
|----|-----------|-------------------|-------|------------|
| R-01a | B-01: re-pin 3 test constants + 1 artifact record after strategy bytes stabilize | tested in disposable copy (phase 16/17 disposable-copy isolation runs) | CANDIDATE, NOT APPLIED | 6 of 9 strategy files are 'M' — strategy byte-state not stable; needs owner decision to commit/restore |
| R-01b | B-01: formal re-registration via recert doctrine (records preserved; canonical recomputed) | design only | CANDIDATE | same as R-01a + owner approval |
| R-02 | F4 PATCH-2 conditional geometry + boundary 171 | primary-tree failure re-verified (run 12 & 13); candidate fix + 171/169/170 boundaries in disposable copy | CANDIDATE READY-FOR-OWNER, NOT APPLIED | owner approval to patch tests/test_stage4_paper_certification.py |
| R-03 | F5b v3 structural policy: declared digest-bearing records + metadata/sidecar + anti-escape tests | design (in this file, section below); v1/v2 re-validated in disposable copy phase 17 | CANDIDATE DESIGN | owner policy decision; then implement tests + policy change in one patch |
| R-04a | B-02 lineage: EXPECTATION RE-REGISTRATION to the scrubbed lineage (Option B step 1) | forensic evidence this phase; candidate values recorded | CANDIDATE READY-FOR-OWNER, NOT APPLIED | owner approval (option B) |
| R-04b | B-02 lineage: research-freeze release of the 'M' working-tree state | not started; the freeze nodes are accurate against the current tree | CANDIDATE (owner decision on commit/restore of research/) | the research 'M' state itself |
| R-04c | P192 path capture | prior phases recorded BLOCKED | NOT VERIFIED | owner-side capture + data-corpus review |
| R-04d | Testnet signature payload | prior phases recorded NOT AUTHORIZED | NOT VERIFIED | operator identity + PGP + signed payload (offline validation allowed) |
| R-04e | Old-credential revocation evidence | NOT VERIFIED | NOT VERIFIED | provider-side evidence |
| R-04f | History decontamination completion (gc/prune + bundle hygiene) | forensic only; deferred | DEFERRED | owner; bundles containing the 114 secret-bearing trees must never leave the workstation |
| R-06 | Manifest .kilo Tooling Exclusion / Worktree Hygiene | verified in primary tree: 2375 covered files 100% pristine; 1318 .kilo files cause manifest --verify & conftest addition flags | CANDIDATE | owner approval: add '.kilo' to SKIP_PARTS in scripts/generate_manifest.py OR remove external worktree via git worktree remove |


## R-03 DESIGN (F5b structural policy 'declared digest-bearing records')

Goal: eliminate the self-referential 'report quotes digest -> becomes offender' loop WITHOUT
weakening detection or adding filename soup.

Design:
1. A 'DECLARED DIGEST-BEARING RECORD' (DDBR) is a file that (by policy) is allowed to contain the
   CURRENT archive digest because it is a documentation/decision/provenance record (the exact
   class of files that is SUPPOSED to quote digests).
2. Declaration mechanism (metadata, not scanner logic): each DDBR declares itself via a mandatory
   first-line marker, e.g. `<!-- DD:BR:DGBR-REV1 -->` for .md files, or a `"declared_digest_record": true`
   top-level key for .json files. The scanner/test DOES NOT parse semantics; it uses a SYMMETRIC
   two-sided contract:
   - the F5b test adds an interface check: for every file that contains the digest, the file MUST
     carry the DDBR marker (non-DDBR offenders = hard failure, as today); AND
   - a companion test asserts that the marker EXACTLY privileges the digest-embedding class:
     crafting a marker-carrying file that contains a DIFFERENT (non-declared) sensitive digest
     (e.g. a synthetic 'secret-like' pattern) MUST still be flagged by the credential scanner —
     i.e. the DDBR marker cannot launder arbitrary secrets.
3. Self-reference loop avoided: each new phase report that legitimately quotes digests is expected
   to carry the marker; it therefore does NOT add offender noise. The marker is RELIABLY refused
   for non-digest secrets by the companion test (clause 2). Reports that FORGET the marker still
   fail F5b (fail-closed), which themselves can be cured by adding the marker in a follow-up
   documentation patch.
4. Arbitrary-file escape prevention: the DDBR is recognized ONLY by its marker, NOT by filename.
   A test enforces that the marker string cannot appear in any file that does not also contain
   the current archive digest without failing F5b:
   - a file carrying the marker but NOT containing the digest must be flagged by the companion
     test (so an .md cannot hide an arbitrary NON-digest secret behind the marker),
   - a file carrying the digest without the marker must be flagged by F5b (today's behavior),
   - a synthetic non-digest secret hidden behind the DDBR.marker MUST STILL be flagged by the
     credential scanner (clause 2 companion test) because the DDBR is scoped to digests only.
5. Test matrix to implement WITH the policy change (all in tests/, none applied yet):
   - legitimate DDBR (digest + marker): F5b PASS + unchanged census.
   - digest without marker: F5b FAIL (existing behavior).
   - marker on a NON-digest secret-bearing file: companion scanner test FAIL (no laundering).
   - marker BUT no digest: companion scanner test FAIL (no free-floating exemptions).
   - synthetic offender (no marker): F5b FAIL (unchanged from phase 17 evidence).
   - historical records (P14 memos, P165 provenance, P16 final/decision reports, P17 records):
     moved to DDBR status by adding the marker line in a documentation patch (a separate,
     owner-approved change that does NOT touch any code logic).
6. Sidecar alternative (rejected unless the owner prefers it): a
   `reports/DECLARED_DIGEST_RECORDS.json` sidecar listing DDBR filenames; rejected as primary
   because it reintroduces a name-registry that can drift from the files (marker-in-file is
   self-describing and diffs cleanly in the manifest).

This design is planned, not implemented. It changes ZERO hashes today; it requires the owner's
approval to (a) add the policy tests, (b) apply the marker line to the existing historical
records, (c) then re-run and re-baseline the census.

## ROUTE-B BASELINE RE-REGISTRATION — exact command list (NOT EXECUTED)

1. (Documentation) create `reports/PHASE18_BASELINE_REREGISTRATION.json` per Option B.
2. (Code) apply the 9 hex-value replacements in the 9 test files per Option B (each file: a
   single-line change; f16 digits only, tests otherwise untouched).
3. Re-run each of the 9 ancestry nodes (pytest selected -q) and record rc before/after.
4. Full-suite run 14; expected census top-level change: 9 red → green; other 25 census nodes
   unchanged by this change alone.
5. Manifest regen + verify.
```
# exact commands the OWNER would run (example; NOT EXECUTED here):
#   (in each of the 9 test files, replacing OLD SEED with REPLICA SEED)
#   python - <<PY
#     ... ... (byte-exact replace of the 9 hex strings; verified by replace-count == 1 per site)
#   PY
#   python -m pytest "tests/test_researcher_11g_n.py::TestRepositoryHead::test_starting_head_ancestor" ... -q
#   python scripts/generate_manifest.py --root . --write BUILD_MANIFEST.sha256
```

## CLOSED: D-16-03 v1/v2 letter (superseded by the R-03 design above)

The v1/v2 skip-list patches remain valid DISPOSABLE-COPY evidence (phase 17), but they are
NOT the recommended repair: the structural DDBR policy replaces them (they were narrow
name-skips, which the phase 17 evidence already showed can't bound the growing offender set).

## FINAL RECOMMENDATION (owner packet summary)

- Adopt Option B (evidence-backed re-registration of the 9 ancestry pins to the scrubbed lineage),
  then resolve the 16 research-freeze reds by deciding the fate of the modified research/ files
  (likely owner-approved commit or restoration), then apply R-02 (F4), then implement R-03
  (F5b structurally), then resolve R-01a once the 6 modified strategy files are committed,
  and keep R-04c/d/e as outstanding owner-side items.
- Do NOT adopt Option A in its raw form; the secrets-bearing chain must not be put back into the
  published lineage identity. Preservation of the original chain is documented in
  PHASE18_LINEAGE_EVIDENCE.md and is NOT harmed by Option B.
