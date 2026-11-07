# PHASE 17 REPAIR DECISIONS (separate assessments, none applied)

Date: 2026-10-23
Every item is assessed ON ITS OWN evidence, gathered fresh this session. Nothing here is
applied to any tree (the census-freeze and decision letterboxes belong to the owner).
Cross-references: phase 15 (PATCH-1/2/3 definitions), phase 16 (isolated validations),
`reports/PHASE16_OWNER_DECISIONS.md` D-16-01..08.

## R-01  B-01 strategy digest re-registration (supersedes D-16-01 PATCH-1)

Nature of the 4 sites (verified this session, not inherited):

- tests/test_oos_feasibility_17.py L42 — hard-coded recorded constant
  `c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6`; computes the
  CURRENT 9-file concatenated per-file sha256 digest and asserts equality (stale
  expected-value, test computes truth dynamically).
- tests/test_oos_validation_18.py L38 — same construction (stale expectation).
- tests/test_oos_data_extension_19.py L38 — same construction (stale expectation).
- tests/test_readiness_16.py L534-558 — computes the CURRENT digest itself and asserts
  equality against the ARTIFACT's recorded value loaded from
  research/results/phase14_executable_edge_forensics.json (L557 assertEquals
  art["strategy_hash"] == digest; L558 art["strategy_files"] == files). Nature: the
  registry record itself is the pin, and it currently records c52e while the artifact is
  'M' in the working tree.
- research/results/phase14_executable_edge_forensics.json L1029 — the authoritative
  recorded "strategy_hash": c52e.

Era map (fresh, from bytes this session):

| Era | Digest | How established |
|-----|--------|-----------------|
| recorded c52e | c52e648c...f3d5a6 | recorded in artifact + 3 test pins; NOT reproducible from any local commit (see below) |
| recert canonical | ba17582d...60ded5 | LF-normalized recompute (recert doctrine, BLOCKED) |
| PHASE158-era | f8407e77... | recorded in PHASE158_HASH_FAILURE_TRIAGE.json L119 |
| HEAD blobs | 9eff61b7...8fd8a2 | computed from git HEAD blob bytes this session |
| origin/main | db5bcdc0...b6c | computed this session |
| stage123-closure tip fad7329b | 83786a18...8ec33 | computed this session |
| current worktree | 9c56f3ff...54f35a | computed this session; drifted because 6 of the 9 strategy files are 'M' (decision_engine.py, risk_engine.py, risk_settings.py, accounting.py, backtester.py, paper_trading_engine.py) |

Irreproducibility of the recorded era (the strongest new fact):

- The 9 strategy files were touched by exactly 15 commits in history
  (`git log -- <9 files>`): 10 are calculable (5 earliest pre-date some of the 9 files),
  and NONE of the 15 states reproduces c52e. HEAD == 1477bcf state (9eff61b7): the files
  were last committed 2026-09-21 and remained untouched until the current uncommitted
  modifications.
- Constructions tried for c52e: HEAD raw / HEAD LF->CRLF / origin/main raw / closure-tip
  raw — all four give four DIFFERENT non-matching digests. c52e-era bytes exist in no
  reachable local commit.

Verdict: the three test pins are STALE EXPECTATIONS against an effectivity state that
no longer exists in repository form; the research JSON is a FROZEN RESEARCH RECORD. A
PATCH-1 of the mechanical form "replace c52e with 9c56 at the 4 sites" (phase 15/16
proposal) is well-defined mechanically (byte-identical substitutions, proved in the
phase-16 disposable copy) but its SEMANTICS now carry an extra burden the phase 15/16
analyses did not surface: 9c56 is the digest of UNCOMMITTED working-tree bytes (6 files
M). Re-pinning tests to uncommitted bytes moves the strategy identity to a non-IS state.
The defensible repair sequence is therefore: (1) owner decision on the 6 modified
strategy files (commit or restore), (2) recompute the digest on the resulting STABLE
tree, (3) re-register all 4 sites through the recert path (recertify_strategy_digest.py,
currently BLOCKED) or by explicit deliberate re-registration, (4) only then expect the
5 census B-01 nodes to pass. Mechanical-only PATCH-1 remains available as the operator's
fallback, and phase 16 proved it works in an isolated copy — but the final re-registration
is deliberately not executed autonomously.

## R-02  F4 simulator accounting (continues D-16-02 PATCH-2)

Failure (run 12, re-read from trace): tests/test_stage4_paper_certification.py
TestPaperAccounting::test_sequential_ledger_matches_registry —
`AssertionError: 1 != 2` preceded by
`log: OPEN_TRADE_VALIDATION_FAILED setup_id=T-160.0 reason=Inconsistent BEARISH
geometry: stop_loss (150.0) < entry (160.0)`.

Root cause (fixture, L305-311): `mk()` builds BULLISH geometry for any direction
(stop_loss=e-10, take_profit=e+60). The second leg is BEARISH (entry 160) with stop BELOW
entry (150), which the simulator correctly rejects as inconsistent geometry; the trade
never enters; the registry closes with 1 trade instead of 2.

PATCH-2 (validated live this session in the disposable copy, re-applied from the
phase-16 driver):

- conditional geometry per direction: stop_loss=(e-10.0) if BULLISH else (e+10.0);
  take_profit=(e+60.0) if BULLISH else (e-60.0) — preserves 1:6 RR.
- boundary seam raised: high 161.0 -> 171.0 in the bar that closes the BEARISH leg
  (stop 170.0 must be touchable).

Fresh boundary/negative proofs (this session, all in the disposable copy, manifest
regenerated before each run — snapshot guard consistent):

| high | outcome | meaning |
|------|---------|---------|
| 171.0 | PASS | positive control (leg closes at stop) |
| 169.0 | FAIL (1 != 2, line 321) | NEGATIVE CONTROL: leg must NOT close when stop not touched; no validation error, clean no-trade |
| 170.0 | PASS | exact-boundary: the simulator fires the stop when `high >= stop` (touch semantics); the leg closes at the stop |

Conclusions: PATCH-2 does not weaken the gate (169 still fails loudly); the exact-boundary
pass documents the simulator's stop-touch convention (`high >= stop`), which is a
simulator convention to be aware of for edge accounting (fill-at-stop), not a new defect.
RECOMMENDATION: apply PATCH-2 at owner approval; it is the one census node that is a
genuine product-code test defect.

## R-03  F5b archive self-embed scan (continues D-16-03 PATCH-3)

Run-12 state (fresh read): offenders = 4
['reports/PHASE14_DECISION_MEMOS.md', 'reports/PHASE165_PROVENANCE.json',
'reports/PHASE16_FINAL_REPORT.md', 'reports/PHASE16_OWNER_DECISIONS.md'].

CRITICAL self-truth: the two NEW offenders are the PHASE 16 records themselves —
written after run 11, quoting the archive digest as evidence (the memos/provenance
quotes pattern repeated). The offender list grows every time a phase record quotes the
digest; unless the scan policy is structurally decided, every future phase report will
add itself to the census. This is now a RECURRING hazard, not a one-off.

Independent re-validation this session (disposable copy, all steps manifest-regenerated):

| state | F5b node result |
|-------|-----------------|
| unpatched | FAIL, offenders 2 (memos + provenance — the copy predates the phase 16 reports) |
| PATCH-3 v1 (skip reports/*_PROVENANCE.json) | FAIL, offenders 1 (memos only) |
| PATCH-3 v2 (v1 + exact-name memos skip) | PASS |
| v2 + synthetic offender file | FAIL, offenders 1 = the synthetic (detection preserved) |
| v2 + annotated offender (file embedding digest plus explicit EXEMPT annotation) | FAIL, offenders 1 = the annotated file (annotation-based exemption REFUTED empirically) |

Findings:

- The scan is a byte-substring check (`actual in text`); ANY annotation scheme that
  preserves the digest text cannot suppress detection. Annotation-based exemption is
  structurally impossible; the only cure is a structural skip (exact-name/pattern) or
  moving digests out of scanned files (for example .sha256/DETACHED sidecar files not in
  the scan set).
- v2 as drafted is INSUFFICIENT for the current tree: it skips provenance + memos but
  would leave PHASE16_FINAL_REPORT.md and PHASE16_OWNER_DECISIONS.md as offenders AND
  would immediately add every future phase report that quotes a digest.
- v3 candidate (for the owner to choose): v2 + exact-name skips for
  PHASE16_FINAL_REPORT.md, PHASE16_OWNER_DECISIONS.md, PHASE17_FINAL_REPORT.md,
  PHASE17_PRODUCT_COMPLETION_MATRIX.md, PHASE17_REPAIR_DECISIONS.md — or better, a
  DECLARED-EVIDENCE naming convention (any reports/PHASE*_{FINAL_REPORT,OWNER_DECISIONS,
  REPAIR_DECISIONS,DECISION_MEMOS}.md and *_PROVENANCE.json is a declared digest-bearing
  record and is skipped by NAME, keeping synthetic arithmetic detection intact). The
  decision and its wording belong to the owner; nothing is applied.

## R-04  B-02 git ancestry/freeze family (continues D-16-04, no repair authored)

Per-node mechanics (exact, from source this session):

- 8 ancestry nodes assert `git merge-base --is-ancestor <SEED> HEAD` returncode 0:
  11g_n -> 004b2bcbe5f3ea8ab0b4d2be246bbb25dde61db2; 11g_o -> 7c9d156d6076b0cc974fb5e0cf24bbe40c2ec3d2;
  11g_p -> 501f082d1b037f1d9461d243310d68b95282a2a7; 11g_q -> 57c22e1c68dcf0480c37cebbad494eaf8490afe9;
  11g_r -> 29959c536610be610653bf34ac7fd331270d96fa; 11g_s -> 217a82553cd91dd886cb060e7f7ebc8245b7caa2;
  11g_t -> 2942b57f85957e7a48546f9baea935d6437f39bd; 11g_u -> e88c3a0b39997de440cc56543141c096ee4ed4f7;
  stage4 -> fad7329b24d614794b35deb0b6926e5dd138977a (stage123 closure tip).
- 8 no-production-path nodes + 8 tree-freeze nodes + researcher_15 freeze + stage4
  research-byte-diff: all assert `git status --porcelain -- research/ [docs/audit/]` (or
  diff --stat) is EMPTY; they fail because the CURRENT tracking state contains
  modifications (notably research/phase11f/candidates.py and
  research/phase11g_n|o|p|q feasibility/readiness jsons; the census explicitly
  names candidates.py).

Object-level fact (NEW this session, decisive for the ancestry half):

- ALL NINE seed heads exist in the object store (`git cat-file -t` = commit) but are
  UNREACHABLE from every ref (`git rev-list --all` membership check). The current HEAD
  lineage does not contain any of the nine; the merge-base checks invert to returncode 1
  and each node fails with `AssertionError: 1 != 0`.
- The stage123-closure tip fad7329b — previously readable via `git log -1` (objects are
  readable whether reachable or not) — fails the same reachability membership test this
  session: it is a DANGLING object from every ref as well.

Verdict: the ancestry failures are not repairable by any code/test change: they state
that the historical lineage must FIRST be recovered (or the expectations re-registered to
the rebuilt lineage) by an owner-authenticated decision (already letterboxed as
D-16-04). The freeze nodes clear ONLY when the research/ tree modifications are resolved
(the 122M tracked state is largely owner-oriented; none of it is autonomously clearable).
No repair is authored; the phase 16 options remain the complete option set.

## R-05  Standing owner items (reaffirmed, nothing new this session)

- P192 path capture: NOT VERIFIED / BLOCKED (corpus unchanged; phantom capture absent).
- Testnet execution authorization: NOT AUTHORIZED; doc placeholders for
  operator_identity / PGP fingerprint / signature payload unchanged (lines 68-76).
- Credential exposure remediation: OPEN / NOT VERIFIED (scanner fail-closed rc=1
  intentionally; .env posture: 360 B, mtime 2026-10-22 18:38:08, untracked+ignored,
  0 staged).
- Old credential revocation: NOT VERIFIED (provider-side evidence never supplied).
- 1:6 vs 1:20 RR authority reconciliation (see matrix area-5 note): owner policy choice.

## Sequencing law for the owner

The repairs are NOT commutative; the only defensible order is:

1. Authoritative git/lineage decision (R-04/B-02) — the B-09/.env-bearing history decision
   comes with it (widest exposure first, per phase 16 records).
2. research/ freeze resolution (commit or restore the modified research records).
3. Strategy identity re-registration (R-01) AFTER the strategy byte-state is stable.
4. F4 PATCH-2 and the F5b structural policy decision (R-03) can go in either order
   AFTER the freeze resolution, and both are proof-required in a disposable copy first.
