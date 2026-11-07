# PHASE 18 FINAL REPORT — AUTHORITATIVE LINEAGE DECISION, SAFE RECOVERY, BASELINE REPAIR
Date: 2026-10-23
Branch: main | HEAD: ffefa14a8729f6d2160db3735a06257cbb6ab48b | origin/main: 47fbecd656f01158a3065eb707b1a61e41b831f6
(origin/main is FULLY ANCESTOR of local HEAD; local is 18 commits ahead; nothing merged, pushed, or rewritten.)

## 0. Gate tape (start-of-phase and end-of-phase: UNCHANGED)

RELEASE_GATE = HOLD
EDGE = NOT ESTABLISHED
TESTNET_EXECUTION = NOT AUTHORIZED
P192 = NOT VERIFIED / BLOCKED
CREDENTIAL_EXPOSURE_REMEDIATION = OPEN / NOT VERIFIED
OLD_CREDENTIAL_REVOCATION = NOT VERIFIED

## 1. Baseline verification (Section 2 of the phase contract) — VERIFIED WITH TWO NOTES

- State, branch, HEAD, origin, remotes, census, manifest: re-verified read-only at phase open
  (manifest 2370 PASS pre-deliverables; census 122M / 384U / 0 staged / 0 stashes).
- All phase-17 decisive claims were reproduced: the nine seed commits exist as objects and remain
  unreachable from every ref; the B-01 eras reproduce from bytes (worktree 9c56f3ff… vs recorded
  c52e648c… with 6 of 9 strategy files modified); the Stage-123 closure of the adopted lineage
  does NOT descend from the original closure tip dangle-object (re-verified);
  the F4 failure mechanism matches the phase 17 trace; the F5b offender set remains exactly
  {PHASE14_DECISION_MEMOS.md, PHASE165_PROVENANCE.json, PHASE16_FINAL_REPORT.md,
  PHASE16_OWNER_DECISIONS.md}; the 34-census set is unchanged (run 13 == run 12 by node-identity).
- Note 1 (correction carried forward, no prior file altered): phase 17's
  PHASE17_REPAIR_DECISIONS.md quoted the PHASE158-era digest with an INVALID full value; the actual
  recorded value in reports/PHASE158_HASH_FAILURE_TRIAGE.json (.root_causes.R2.detail) is
  f8407e772dffecd12bb6b9558547f5d8617b696c8a4f1f2e9918ae2f56915ef4. Recorded here; the phase-17
  file is preserved unchanged per the append-only rule.
- Note 2 (clarification): the convention '384U' counts DIRECTORY-COLLAPSED untracked entries in
  `git status --porcelain` ('?? reports/' is a single entry containing all untracked report files,
  including the 3 new phase-17 and 3 new phase-18 reports). This is the same convention all prior
  phases used; it is not an error.

## 2. Full-suite run 13 (fresh; section 8 record)

Command: python -m pytest tests -q --no-header -p no:cacheprovider
Result: 34 failed / 4716 passed / 14 skipped / 458 subtests passed in 2840.82s (0:47:20); rc=1;
err capture 0 bytes.
Identity checks: node-set IDENTICAL to run 12 (sorted extraction, 0 added / 0 dropped).
The F5b offender VECTOR remains 4 (phase-17 and phase-18 records do not embed the current
archive digest — verified by content grep before the run).
Census identity across runs 8..13 holds (the same 34 nodes each time).

## 3. Workstream A — lineage forensics (delivered: reports/PHASE18_LINEAGE_EVIDENCE.md)

The single most important fact of this phase:

- The repository contains TWO PARALLEL, subject-identical lineages, and the relationship is
  PROVEN position-alignment:
  - ORIGINAL chain (dangling, unreachable from any ref): root 63cd4f1d 'Initial QuantEngine
    project' (author epoch identical to the adopted chain's root), 154 commits, ending at the
    Stage-123 closure tip fad7329b; the EIGHT 11g seeds are the consecutive positions of this
    chain (depths 144..151), parent-connected exactly as the tests expect.
  - ADOPTED chain (current main): root 7a63a0a (same subject, same author epoch), 195 commits;
    its Stage-123 closure b42e8181406 has tree 46e16c9341 which is BYTE-IDENTICAL to the original
    chain's closure tree (46e16c9341).
  - Position-aligned comparison (154 positions): subjects match 154/154; timestamps match;
    trees match for idx 114..153 (the decontaminated epochs INCLUDING ALL EIGHT 11g SEED
    POSITIONS and the closure); trees differ for exactly idx 0..113 — the 114 positions where
    the ORIGINAL chain carries a top-level `.env` in its tree and the ADOPTED chain does not.
- Security-classification of the exposure: 114 dangling-chain positions carry `.env` (4 distinct
  blob generations); the reachable lineages and agents/toto/kilo refs carry 0. Blob contents were
  never read, printed, copied, or transmitted; object IDs + counts only.
- Lineage classification (per phase contract): A (proven authoritative history) — the ADOPTED
  chain, for the entire post-closure epoch (`origin` adds nothing; it is strictly behind local);
  B (plausible-but-unverified) — NONE required: the alignment map itself establishes the
  relationship for the SEED positions; C (dangling objects with insufficient provenance) — the
  114 secret-bearing early positions are documented and preserved but NOT fit for re-publication;
  D (divergent re-records) — the root pair 63cd4f1d/7a63a0a is exactly this.
- The gc/prune/removal risk is real: the wholee original-chain evidence (and the secrets) live in
  unreachable objects; any gc/prune deletes them permanently. This stays owner-controlled; the
  agent performs no gc, prune, repack, reset, clean, bundle creation, or any ref mutation.

## 4. Workstream B — owner decision packet (delivered: reports/PHASE18_OWNER_DECISIONS.md)

Three mutually exclusive options documented with exactly the evidence/risks/validation required.
RECOMMENDATION: Option B (re-register the canonical baseline AT the adopted scrubbed lineage):
- the nine ancestry tests are re-pointed part-for-part to the equivalent positions of the adopted
  chain (8 seed replicas + replica closure), with a JSON provenance record registering the
  original IDs alongside;
- the original objects remain untouched and unreachable; no bundle leaves the workstation; no
  `git replace`/graft/synthetic parent is used (the re-registration is a TEST EXPECTATION change,
  not an ancestry fabrication);
- expected census effect: 9 ancestry reds → green; the 16 freeze/status reds, F4, F5b policy,
  B-01 digest plan, P192/testnet/revocation items remain tracked separately.
Option A (restore the original chain as main's history) is NOT RECOMMENDED: it would reintroduce
the secret-bearing trees into the republished lineage identity and require history rewriting.
Option C (stay blocked) is documented as the zero-motion default.

## 5. Workstream C — security and historical credential exposure (posture preserved)

- Scanner rc=1 (fail-closed) re-confirmed at phase start and at close.
- `.env` (names only): 360 B, mtime 2026-10-22 18:38:08, untracked + ignored, 0 staged; no content
  read, transmitted or printed.
- NEW in this phase: the historical exposure census is quantified: ONLY the dangling original
  chain carries `.env` in trees (114 positions / 4 blob generations); the adopted chain,
  agents/checkpoint refs, and the kilo tree ref carry none (the latter contains only
  `.env.example`). What remains owner-side: provider revocation evidence, and the account-review
  duty; local file edits do not achieve revocation. Status remains NOT VERIFIED everywhere.
- Publishing constraints recorded: DO NOT bundle/push anything that reaches the dangling chain.

## 6. Workstream D — independent repair candidates (correctly labelled; nothing applied)

| id | what | verified where | label |
|----|------|----------------|-------|
| R-01a | B-01 digest re-pin after strategy bytes stabilize | disposable copies only (phase 16/17) | CANDIDATE, NOT APPLIED |
| R-01b | formal re-registration of the digest record via recert doctrine | design | CANDIDATE (owner) |
| R-02 | F4 conditional-geometry patch + boundary tests | primary-tree failure reproduced runs 12/13; fix + 171/169/170 boundaries in disposable copy (phase 17) | READY-FOR-OWNER, NOT APPLIED |
| R-03 | F5b DECLARED-DIGEST-BEARING-RECORD structural policy (marker + symmetric companion tests; rejects marker-laundering and name-registry drift) | DESIGN ONLY in PHASE18_OWNER_DECISIONS.md | CANDIDATE DESIGN (owner) |
| R-04a | lineage re-registration (Option B's nine hex replacements) | forensic evidence this phase; replacement values recorded | READY-FOR-OWNER, NOT APPLIED |
| R-04b | research/ freeze resolution (commit or restore the 'M' research files) | not started | OWNER DECISION REQUIRED |
| R-04c | P192 capture | prior evidence BLOCKED | NOT VERIFIED |
| R-04d | testnet signature payload | prior evidence NOT AUTHORIZED; placeholders unchanged | NOT VERIFIED |
| R-04e | old-credential revocation evidence | provider-side | NOT VERIFIED |
| R-04f | gc/prune/bundle hygiene for the secret-bearing dangling objects | owner-only | DEFERRED (policy documented) |

- The B-02 ancestry failures are, per this phase's evidence, NOT product regressions and NOT
  weakened tests: they are lineage-LABELING divergence between the recorded original IDs and the
  adopted re-recorded history. That reclassification is the core of Option B.
- The research-freeze nodes remain accurate against the current working tree: testing-exclusions
  were NOT created; no frozen OOS research file was touched.

## 7. Workstream E — product completion gaps (delivered: reports/PHASE18_PRODUCT_GAP_PLAN.md)

12 capability classifications with file:line citations, and 8 strictly ordered engineering
milestones (M-01..M-08). Highlights:
- VERIFIED end-to-end: startup/config fail-closed gates; feature-engine wiring to the pipeline;
  risk gates + sizing hooks; reconciliation/monitoring/lifecycle recovery; testnet/live
  authorization double-gate; opt-in authenticated control API; walk-forward/leakage harness.
- PARTIAL with named missing links: the default candle transport is fail-closed (no verified
  transport wired at boot — candles can never arrive out-of-the-box by design); queue-aware
  paper engine not wired into the adapter; history-continuity repair not attached to the cycle.
- ABSENT by design/nature: order-flow/footprint/volume-profile stage is built but NOT registered
  in the runtime pipeline (fields exist, stage unregistered).
- 1:6 minimum RR remains a RESEARCH canon pin, runtime carries a 1:20 cap (documented;
  reconciliation flagged as M-06 policy work; NOT changed autonomously).

## 8. Workstream F — test runs record (all runs, exact)

| run | scope | command | rc | passed/failed/skipped/subtests | duration | repo state during run |
|-----|-------|---------|----|--------------------------------|----------|------------------------|
| 13 (full) | tests/ | python -m pytest tests -q --no-header -p no:cacheprovider | 1 | 34/4716/14/458 | 2840.82s (0:47:20) | unchanged during run; err=0; census node-identical to run 12; output complete |
| A (focused battery) | 8 risk/execution/position-sizing/authorization files | same pytest invocation with the 8 file names | 0 (after manifest covered the 3 phase-18 deliverables; pre-regen the guard flagged the added files as files_added_by_tests) | 97/0/0/6 | 5.82s (pre-regen) then 5.89s (rc clean) | tree pristine at session start |
- No disposable-copy result is presented as a primary-tree result anywhere in this phase's
  records; the primary-tree census remains 34 red with node-identical causes (run 13).

## 9. Deliverables produced

- reports/PHASE18_LINEAGE_EVIDENCE.md (Workstream A full forensic dossier)
- reports/PHASE18_OWNER_DECISIONS.md (Options A/B/C + candidate status table + R-03 design)
- reports/PHASE18_PRODUCT_GAP_PLAN.md (12-capability classes + M-01..M-08 milestones)
- reports/PHASE18_FINAL_REPORT.md (this file)
- Register/ledger/implementation-state/coverage-map addenda appended (append-only convention).

## 10. Unresolved risks noted (as required by exit criteria)

- The dangling original chain (with the 114 `.env`-bearing positions and 4 secret generations)
  remains in the object store, physically preserved; any gc/prune/publish exposure risk is
  owner-controlled. No destruction occurred in this phase.
- The B-01 pins remain unreconciled because 6 of the 9 pinned strategy files are still 'M' in the
  working tree; no digest may be pinned to a non-stable byte state.
- The 16 research-freeze reds are an accurate reflection of the owner's uncommitted research
  decisions; no test exclusion was manufactured.
- The F5b self-quote loop is structurally UNDERSTOOD and has a concrete design (R-03) pending the
  owner's approval; nothing was patched to make reports green.
- P192 / testnet / revocation items remain NOT VERIFIED / NOT AUTHORIZED as at phase start.
- No profitability or live-trading claim was or can be made from this phase's evidence.

## 11. Recommended next single action (highest value)

Owner approval and execution of OPTION B: apply the nine-evidence-backed ancestry
re-registrations to the ADOPTED chain (plus the provenance JSON), then tackle the
research/ freeze items in a follow-up phase, then R-02 (F4), then R-03 (F5b structural),
then R-01a. Each of these steps is small, evidence-backed, reversible, and does not touch the
fail-closed release posture anywhere.

## 12. Explicit separation required by exit criteria

- VERIFIED: every forensic claim in section 3 and phase-17 reproduction list in section 1.
- IMPLEMENTED (pre-existing product code, unchanged this phase): referenced capability paths in
  section 7 (per their class rows).
- TESTED: run 13 (full) and the battery (rc=0 clean) in section 8; F4 candidate evidence remains
  disposable-copy-labelled.
- BLOCKED: 34-node census (34 red = unchanged from phase 17; none green during the phase);
  P192; testnet authorization; credential revocation; gc/prune decision.
- OWNER DECISION REQUIRED: all six recommended options/candidates in section 6 and the Option B
  master choice in section 4.

## 13. OWNER-APPROVED EXECUTION ADDENDUM (post-approval)

The owner approved Option B in-session. Executed exactly as specified (no git mutation, no
replace/grafts, no gc/prune, no bundle; assertions untouched):

- Nine single-site hex re-points in 9 test files (8 seed files + stage4 closure), each file
  verified to contain EXACTLY ONE occurrence of the original hex before the edit.
- Provenance record: reports/PHASE18_BASELINE_REREGISTRATION.json (pairing + verification basis
  + executed-validation block).
- Per-file validation run: 18 failed / 453 passed in 1070.13s — remaining failures are exactly
  the research-freeze/status hold-out nodes (16), stage4 research-byte, and F4 (all pre-existing,
  intentionally untouched).
- Full-suite run 14: 25 failed / 4725 passed / 14 skipped / 458 subtests passed in 2697.81s
  (0:44:57), rc=1, err 0 bytes. Census delta vs run 13: EXACTLY the 9 re-pointed ancestry nodes
  dropped (34 -> 25); 0 added; no other node changed.
- Census interpretation after this change (25 nodes): 16 research-freeze/status (the working
  tree's 'M'/'??' research files), researcher_15, F4, F5b policy, 5 B-01 pins, stage4
  research-byte. Gates unchanged; scanner rc=1 unchanged; manifest regen executed at close
  (provenance JSON included).

## 14. AUTHORITATIVE INDEPENDENT RE-VERIFICATION & FORENSIC AUDIT

Date: 2026-10-24
Auditor: Senior Software Architect, Git-Forensics Investigator, Python Test Engineer, Security Engineer, Release-Gate Owner

All baseline claims from Phase 17 and Phase 18 were re-evaluated and independently verified from actual repository bytes:

1. **Repository & Working Tree State:**
   - Active Branch: `main`
   - Local HEAD: `ffefa14a8729f6d2160db3735a06257cbb6ab48b`
   - Upstream origin/main: `47fbecd65601158a3065eb707b1a61e41b831f6` (strict ancestor; local is 18 certified commits ahead; 0 divergent)
   - Working Tree Status: Exactly 122 tracked modified files (`122M`), 0 staged files (`0 staged`), 0 git stashes (`0 stashes`).
   - Forensic note on file count: The 9 ancestry test files already had local uncommitted additions (`require_git_fact` imports) from earlier phases; therefore, applying the 9 single-site hex replacements did not change the total modified file count (`122M` is the exact tracked count).
   - Untracked Entries: Exactly 384 directory-collapsed entries (`384U`), representing 1077 individual files when expanded.

2. **Dangling Ancestry Seeds & Replica Commits:**
   - Independently verified all 9 original seed commits exist in the Git object store (`git cat-file -t commit`) and are completely unreachable from all refs (`git rev-list --all` membership is False for all 9).
   - Independently verified all 9 replica commits on the adopted lineage (`acab874d1a`, `5c95fd623f`, `6a961459ae`, `e1483a1090`, `bd21e9ac06`, `d77af19e85`, `e235663d2a`, `0e4d3f04ce`, `b42e818140`) are strict ancestors of HEAD (`is_ancestor_HEAD = True`).
   - Verified that tree objects for each pair are 100% byte-identical:
     - 11g_n: `036ba5d2c5` == `036ba5d2c5`
     - 11g_o: `a00f997b52` == `a00f997b52`
     - 11g_p: `fe5da6fbac` == `fe5da6fbac`
     - 11g_q: `4bb19beee6` == `4bb19beee6`
     - 11g_r: `8fa8937400` == `8fa8937400`
     - 11g_s: `07e6fc3c3c` == `07e6fc3c3c`
     - 11g_t: `97f1c50819` == `97f1c50819`
     - 11g_u: `1d87296191` == `1d87296191`
     - closure: `46e16c9341` == `46e16c9341`
   - Verified that all 9 ancestry tests PASS individually under the re-pointed expectations.

3. **B-01 Strategy Digest Eras:**
   - Computed from actual file bytes:
     - Recorded Test Constant: `c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6` (irreproducible in any reachable local commit)
     - Current Working Tree Raw: `9c56f3ff7dea2a3ea98adf226aff775d263ebfcf1bbb2697ca244ab6cd54f35a` (6 of 9 strategy files are 'M': backtester, risk_settings, accounting, paper_trading_engine, risk_engine, decision_engine)
     - Current HEAD Blob Digest: `9eff61b777846c7f5e2056c486c9c381872a93e154d35160e70f63051c8fd8a2`
     - origin/main Blob Digest: `db5bcdc01cd88b6c997e630e7ad1f6879f72f4ccc191393a6ff41675df52be72`
     - Recert Canonical (CRLF-normalized): `ba17582d0ab96913f81d0e6ac652368e609bb28f22a24200f53bf9b6cd60ded5` (Status: BLOCKED)
   - Re-confirmed: Pinning tests to uncommitted `9c56...` working-tree bytes is prohibited. Digest re-registration requires stabilizing the 6 modified strategy files first.

4. **F4 Paper-Accounting Geometry Failure:**
   - Reproduced in `tests/test_stage4_paper_certification.py::TestPaperAccounting::test_sequential_ledger_matches_registry`.
   - Cause: Fixture unconditionally constructs bullish geometry (`stop_loss = e - 10.0`) for a bearish leg (`entry = 160.0`), resulting in `stop_loss (150.0) < entry (160.0)`. `TradeSimulator.open_trade` rejects this invalid trade (`OPEN_TRADE_VALIDATION_FAILED`), causing only 1 trade to close instead of 2 (`AssertionError: 1 != 2`).
   - Candidate fix R-02 (conditional geometry per direction + raising bar high to 171.0) verified with positive boundary (171), negative control (169), and touch semantics (170). Ready for owner authorization.

5. **F5b Release Consistency Scanner:**
   - Offender set reproduced: Exactly 4 files (`reports/PHASE14_DECISION_MEMOS.md`, `reports/PHASE165_PROVENANCE.json`, `reports/PHASE16_FINAL_REPORT.md`, `reports/PHASE16_OWNER_DECISIONS.md`).
   - Verified that neither Phase 17 nor Phase 18 reports expanded the offender list.
   - Confirmed that R-03 structural declared-record naming policy is designed to solve the recurring self-quote hazard.

6. **External Tooling Worktree Discovery (.kilo):**
   - At 2026-10-23 22:04, external tooling (Kilo agent) instantiated a worktree at `.kilo/worktrees/hardly-bobble`.
   - Independent verification against `BUILD_MANIFEST.sha256`: Exactly 2375 manifest-covered files inspected: 0 missing files, 0 hash mismatches (100% pristine).
   - Exactly 0 additions exist outside `.kilo`.
   - Because `scripts/generate_manifest.py`'s `SKIP_PARTS` was defined in Phase 154 before Kilo was introduced, `manifest.py --verify` and `conftest.py`'s addition check flag the 1318 `.kilo` files.
   - Per Safety Rules 2 & 3, `.kilo` was preserved without mutation. Owner decision needed to add `".kilo"` to `SKIP_PARTS` or clean the worktree via `git worktree remove`.

7. **Security Posture & Historical Credential Exposure:**
   - Workstation `.env`: 360 bytes, mtime 2026-10-22 18:38:08, ignored by `.gitignore`, untracked, 0 staged.
   - Secret Scanner: Exits with code 1 fail-closed, finding `.env` (rules `non_empty_known_secret`).
   - History Scanner: Identifies 4 commits with `.env` in history (`63cd4f1d`, `e686ccd5`, `d5846fc3`, `e49f61e1`). Independently verified that NONE of these 4 commits is reachable from `main` or `origin/main`.
   - Confirmed: No secrets read, printed, committed, or transmitted. Unreachable dangling objects contain historical credentials and must not be published or bundled.

8. **Release Gates Final Posture:**
   - RELEASE_GATE = HOLD
   - EDGE = NOT ESTABLISHED
   - TESTNET_EXECUTION = NOT AUTHORIZED
   - P192 = NOT VERIFIED / BLOCKED
   - CREDENTIAL_EXPOSURE_REMEDIATION = OPEN / NOT VERIFIED
   - OLD_CREDENTIAL_REVOCATION = NOT VERIFIED

