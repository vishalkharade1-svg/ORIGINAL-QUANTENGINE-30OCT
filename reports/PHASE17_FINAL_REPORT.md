# PHASE 17 FINAL REPORT — CANONICAL BASELINE CLOSURE + PRODUCT COMPLETION GATE

Date: 2026-10-23
Branch: main | HEAD: ffefa14a8729f6d2160db3735a06257cbb6ab48b | origin/main: 47fbecd65601158a3065eb707b1a61e41b831f6 (origin ahead; never merged autonomously)
All workstreams executed; nothing autonomous applied to shipped gates or records beyond the three phase-17 report deliverables.

## 1. Baseline verification (WS1)

- Branch/HEAD/origin re-verified; census 122 M / 384 untracked / 0 stashes; manifest
  --verify => MANIFEST_PASS (0 problems) at 2367 entries (phase-16 close counts).
- Gate tape at open: RELEASE_GATE = HOLD | EDGE NOT ESTABLISHED | TESTNET_EXECUTION
  NOT AUTHORIZED | P192 NOT VERIFIED / BLOCKED | CREDENTIAL_EXPOSURE_REMEDIATION OPEN /
  NOT VERIFIED | OLD_CREDENTIAL_REVOCATION NOT VERIFIED. All unchanged at close.

## 2. Full-suite run 12 (WS1, fresh, never copied)

Command: python -m pytest tests -q --no-header -p no:cacheprovider (full inventory).
Result: 34 failed / 4716 passed / 14 skipped / 458 subtests passed in 2721.35s
(0:45:21); rc=1; err capture 0 bytes; output decoded from UTF-16.

Run identity checks (sorted node-set extractions, this session):
- run 12 vs run 11: EXACT identity (34 == 34; 0 added, 0 dropped).
- Group totals equal runs 8/9/10/11 (34/4716/14/458).
- ONE census component changed: the F5b offender VECTOR inside
  test_release_consistency_phase155 expanded from 2 files to 4 — the two new offenders
  are the PHASE 16 records themselves (PHASE16_FINAL_REPORT.md,
  PHASE16_OWNER_DECISIONS.md), which quote the archive digest. Node count unchanged; a
  documentation-feedback loop now exists (see WS5).

## 3. Per-node root causes (WS2; full parse from run-12 tracebacks)

34 nodes, 7 root-cause classes, dependency graph strictly by class:

| Class | Node owner | Count | Root cause (one line each) |
|-------|-----------|-------|-----------------------------|
| A | test_oos_feasibility_17.py::TestStrategyIdentity::test_nine_file_hash_exact_match | 1 | recorded digest c52e != current 9-file worktree digest 9c56 (test computes current, asserts recorded) |
| A | test_oos_validation_18.py::TestStrategyIdentity::test_nine_file_hash_exact_match | 1 | same |
| A | test_oos_validation_18.py::TestStrategyIdentity::test_no_strategy_mutation_after_runs | 1 | same |
| A | test_oos_data_extension_19.py::TestFrozenBaseline::test_nine_file_hash_exact_match | 1 | same |
| A | test_readiness_16.py::TestFrozenRecords::test_strategy_hash_pinned | 1 | recorded ARTIFACT strategy_hash (c52e) != computed current digest |
| B | test_stage4_paper_certification.py::TestPaperAccounting::test_sequential_ledger_matches_registry | 1 | fixture builds BULLISH geometry for BEARISH leg; simulator rejects (stop 150 < entry 160); ledger closes 1 of 2 |
| C | test_release_consistency_phase155.py::TestReleaseConsistency155::test_no_text_artifact_embeds_own_archive_hash | 1 | 4 files embed current archive digest (2 self-inflicted phase-16 quote artifacts) |
| D | test_researcher_15.py::TestMultipleTestingPreserved::test_no_new_hypothesis_family | 1 | freeze assertion: git status non-empty on research/ (tree modifications) |
| E | test_researcher_11g_n..u (8 files x 3 nodes) | 24 | per file: (1) no_production_paths — status --porcelain -- research/ docs/audit/ non-empty; (2) ancestry — merge-base --is-ancestor SEED..HEAD == 1; (3) tree-freeze (tree_clean_except_notes / tree_only_expected) — research/ freeze assertion fails on current modifications |
| F | test_stage4_paper_certification.py::TestRepoIntegrity::test_head_is_stage123_closure_descendant | 1 | merge-base --is-ancestor fad7329b..HEAD == 1 (stage123 closure tip dangling) |
| F | test_stage4_paper_certification.py::TestRepoIntegrity::test_research_byte_unchanged | 1 | git diff --stat -- research/ non-empty (phase11g_n/o/p feasibility + readiness jsons) |

Totals 5+1+1+1+24+2 = 34. No class is cross-dependent; the matrix maps each class to
exactly one owner letterbox (see PHASE17_REPAIR_DECISIONS.md).

## 4. B-01 three-era verification + nature of the 4 sites (WS3)

New facts (this session, computed from bytes):
- 6 of the 9 pinned strategy files are MODIFIED in the current working tree
  (decision_engine, risk_engine, risk_settings, accounting, backtester, paper_trading_engine).
- The HEAD-blob digest (9eff61b7…) is a NEW, fourth digest value (distinct from recorded
  c52e, PHASE158-era f8407e77, recert canonical ba17582d, origin/main db5bcdc0,
  closure-tip-state 83786a18, and worktree 9c56).
- Irreproducibility: across ALL 15 commits that ever touched the 9 files (10 calculable
  states, 5 pre-date some files), NONE reproduces the recorded c52e. Direct constructions
  (HEAD raw/HEAD CRLF-normalized, origin/main, closure tip) all give distinct non-matching
  values. The c52e era's byte-state exists in NO reachable local commit.

Nature of the 4 pin sites (see PHASE17_REPAIR_DECISIONS.md R-01 for the full per-site read):
3 stale test expectations + 1 artifact registry record; readiness_16 computes the current
digest and asserts against the artifact record, so the ARTIFACT is the load-bearing pin.

## 5. F4 trace + boundary/negative validation (WS4)

Trace reconfirmed from run 12 (OPEN_TRADE_VALIDATION_FAILED on the BEARISH leg; 1 != 2).
PATCH-2 re-validated in the disposable copy with fresh boundary proofs:
- 171: PASS (positive). 169: FAIL 1!=2 (negative control — no silent weakening).
- 170: PASS — documents the simulator stop-touch convention (fires when high >= stop).
Gated evidence recorded in PHASE17_REPAIR_DECISIONS.md R-02.

## 6. F5b v1/v2 independent evaluation + annotation-vs-exemption (WS5)

- v1 (skip *_PROVENANCE.json in reports/): revalidated — offenders 2 -> 1 (memos only).
- v2 (v1 + exact-name memos skip): revalidated — PASS.
- Detection preservation: synthetic offender file still caught under v2 (positive proof).
- Annotation-based exemption: REFUTED empirically — a file embedding the digest plus an
  explicit EXEMPT annotation still offends and fails the node. Byte-scan cannot be
  annotation-driven; only structural skips (or moving digests to sidecar files) can bound
  the offender set.
- Structural finding: offenders grew 2 -> 4 because the PHASE16 records quoted the digest
  after the run-11 snapshot; every phase report that quotes digests adds itself. v2 as
  drafted is insufficient for the current tree; a v3 (declared-digest-bearing-record
  naming convention) is sketched for the owner in PHASE17_REPAIR_DECISIONS.md R-03.

## 7. B-02 per-node explanations (WS6)

Exact per-node assertion mechanics read from source (not inferred): 8 ancestry nodes
(each names its own SEED; full list in R-04), each asserting merge-base --is-ancestor
SEED..HEAD == 0; 8 no-production-path nodes asserting `git status --porcelain --
research/ docs/audit/` empty; 8 tree-freeze nodes asserting frozen-research
modification absence; stage4 adds the closure-descendant ancestry node and the
research-diff-diff node. NEW decisive fact: all 9 expected seed heads EXIST in the
object store but are UNREACHABLE from every ref (dangling). No code change can satisfy
them; only an owner-level lineage decision (D-16-04 options) applies.

## 8. Separate repair assessments (WS7)

Delivered as reports/PHASE17_REPAIR_DECISIONS.md — R-01..R-05, each assessed separately
with its own evidence, sequencing law (lineage first, freeze second, re-registration
third), and nothing applied.

## 9. Product capability matrix (WS8)

Delivered as reports/PHASE17_PRODUCT_COMPLETION_MATRIX.md — the 18 areas traced with
file/function/test citations. 14 of 18 REAL; honest partials: dataset.py direct test
absent; config validation entry point absent; volume-profile engine tests absent (only
the designed-negative integration); order-flow imbalance unverified. Indicator roster
verbatim (area 18): product-level indicators {ADX, ATR, EMA, RSI, SMA}; ABSENT at
product level: VWAP; RESEARCH-LEVEL: Wyckoff, Fibonacci, Bollinger, OBV; footprint as
designed-negative; OFI unverified.

## 10. Completion contract (WS9 — Gates A-D)

- Gate A (every red node explained individually): MET — 34 nodes mapped in section 3
  with per-node mechanics in section 4-7 and R-01..R-04; zero unexplained census members.
- Gate B (no bundled repair assessments): MET — each of R-01..R-05 carries independent
  verification; no assessment borrows evidence from another without re-derivation.
- Gate C (no phantom capability areas): MET — every matrix row cites files/functions
  actually read this session; partials declared rather than filled.
- Gate D (no new security posture change): MET — scanner remain rc=1 fail-closed;
  .env byte/mtime unchanged; testnet placeholders unchanged; no exchange contact made.

## 11. Security state (WS10, names only)

- Scanner rc=1 (fail-closed signature) — unchanged; .env 360 B, mtime
  2026-10-22 18:38:08, 9 assignments (names not printed), untracked+ignored, 0 staged.
- P192 and testnet placeholder states unchanged (see R-05).

## 12. Focused suites + runs record (WS11)

- Battery (8 files: risk_gates_12, phase183 stop-rounding, risk_execution_contract,
  phase188 gated mock, phase193a safety gate, post_cost_rr_13, position_sizing_9q,
  phase190 authorization audit): 97 passed + 6 subtests, rc=0, tree pristine,
  manifest-cover 2367. Reaffirms the offline risk/execution gates are green.
- Full-suite runs ledger: run 8/9/10/11 historical; run 12 this phase (45:21).
- Disposable-copy validations: F4 boundary/negative (171/169/170 + regen each step),
  F5b v1/v2/synthetic/annotated (each step regenerated) — disposable work only, no
  shipped-tree effect.

## 13. Deliverables

- reports/PHASE17_PRODUCT_COMPLETION_MATRIX.md (WS8)
- reports/PHASE17_REPAIR_DECISIONS.md (WS7)
- reports/PHASE17_FINAL_REPORT.md (this file)
- Registry addenda appended by this phase: register (failure census delta), session
  ledger (runs + validations), IMPLEMENTATION_STATE (phase 17 section), coverage map
  (phase 17 delta rows).

## 14. Posture at close

RELEASE_GATE = HOLD | EDGE NOT ESTABLISHED | TESTNET_EXECUTION NOT AUTHORIZED |
P192 NOT VERIFIED / BLOCKED | CREDENTIAL_EXPOSURE_REMEDIATION OPEN / NOT VERIFIED |
OLD_CREDENTIAL_REVOCATION NOT VERIFIED.

## 15. Single highest-value next action

Approve and execute the LINEAGE RECOVERY decision (D-16-04/B-02, letterboxed) FIRST, in
the phase 16 documented option set: recover the authoritative lineage (including the 9
dangling seed heads and the .env-bearing history exposure), or formally re-register the
effective lineage in the tests. Everything else — freeze clearance, digest
re-registration (R-01), F4 (R-02), F5b policy (R-03) — is sequenced AFTER it: each of
those items consumes either the recovered lineage or one of its artifacts (the stable
git state that clears the freeze nodes), and none of them can be validated against a
stable lineage until that decision is made.
