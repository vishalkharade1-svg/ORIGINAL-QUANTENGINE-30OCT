# PHASE 16 — OWNER DECISIONS (Category B — all PROPOSED, NOT APPLIED)

Prepared by Phase 16 agent from HEAD `ffefa14a8729f6d2160db3735a06257cbb6ab48b`,
branch `main`, on 2026-10-23. Every item below requires an explicit, named owner
decision; nothing was applied in the primary working tree. Default state if the
owner does nothing: the current repository behavior persists exactly as
documented in `reports/PHASE16_FINAL_REPORT.md` (HOLD posture preserved).

Decision IDs: D-16-01 … D-16-08. Each lists: current evidence, exact proposed
change, affected files/lines, patch reference, focused validation result,
expected effect, risks/reversibility, what it changes (evidence / history /
test behavior / release metadata), exact owner action, default-if-nothing.

---

## D-16-01 — B-01 stale strategy pins (PATCH-1)

- **Current evidence:** the 5 red census nodes
  (test_oos_feasibility_17 identity, test_oos_validation_18 identity +
  no_strategy_mutation, test_oos_data_extension_19, test_readiness_16
  pinned) fail only because the frozen `c52e648c…` pin does not match the
  released/worktree bytes `9c56f3ff…` (recomputed this phase). The
  project's own re-certification boundary stands:
  `scripts/recertify_strategy_digest.py` → `matches_recorded=false`,
  `status=BLOCKED` (no recorded research re-execution; canonical CRLF→LF
  digest `ba17582d…` matches nothing recorded).
- **Exact proposed change:** 4 substitutions (tests × line 42/38/38 + JSON
  line 1029) `c52e648c…` → `9c56f3ff…`. Files:
  tests/test_oos_feasibility_17.py, tests/test_oos_validation_18.py,
  tests/test_oos_data_extension_19.py,
  research/results/phase14_executable_edge_forensics.json.
  The 8 historical reports-JSON references to `c52e…` (PHASE158 triage,
  PHASE162/163 blockers) stay untouched — they are frozen historical
  documentation of the mismatch itself.
- **Patch reference:** `reports/PHASE15_OWNER_PATCHES.md` PATCH-1 (diff
  block unchanged; still exactly 4 substitutions).
- **Focused validation (isolated copy, this phase):** applied in the
  disposable copy `C:\Users\Admin\AppData\Local\Temp\opencode\p16_val\repo`,
  copy-manifest regenerated (2365 entries), then
  `pytest <5 nodes>` → **7-object battery green: 5 passed of the pin set;
  guard `tree_pristine_at_session_start=true`; rc=0** for the node set run
  with PATCH-2/3-scope battery (see final report §6 for the exact battery
  line).
- **Expected effect:** the 5 nodes go green; release-lineage (tests ==
  shipped archives PHASE165-185) aligns. **This does NOT validate or
  re-certify any strategy; EDGE remains NOT ESTABLISHED either way.**
- **Risks/reversibility:** tiny, file-level, reversible by inverting the 4
  substitutions; archives/records unaffected.
- **Changes:** test behavior + the frozen research JSON's recorded digest
  field (a recorded VALUE correction with an audit trail in this file).
- **Owner action:** reply "APPROVE PATCH-1" (or decline). If approved, agent
  applies ONLY the 4 substitutions, then runs the documented test plan and
  regenerates the manifest.
- **Default-if-nothing:** nodes stay red with the current classification.

## D-16-02 — F4 Stage-4 accounting fixture defect (PATCH-2)

- **Current evidence:** node
  `tests/test_stage4_paper_certification.py::TestPaperAccounting::test_sequential_ledger_matches_registry`
  reproduces red in the primary tree (run-11 + isolated this phase). The
  fixture's BEARISH leg uses BULLISH-generate stop/tp limits and
  `high=161.0`, tripping `OPEN_TRADE_VALIDATION_FAILED` before any
  accounting happens. Rationale, exact diff and 1-alternative are in
  `reports/PHASE15_OWNER_PATCHES.md` PATCH-2 (conditional geometry in
  `mk()` + bar4 high `161.0`→`171.0`; 1:6 RR preserved in both legs).
- **Patch reference:** PATCH-2 (diff block; only this fixture function).
- **Focused validation (isolated copy, this phase):** applied via the
  anchored splice; in the copy,
  `pytest tests/test_stage4_paper_certification.py::TestPaperAccounting -q`
  → **5 passed** (node green; whole accounting class green; guard
  pristine after copy-manifest regen).
- **Expected effect:** node green; asserts move past validation to the
  intended ledger-vs-registry accounting path; asserts remain identical.
- **Risks/reversibility:** none beyond the single function (grep-scoped);
  fully reversible.
- **Changes:** test behavior only (frozen Stage-4 test); production
  accounting: zero changes.
- **Owner action:** reply "APPROVE PATCH-2" (or decline / pick the 1-line
  alternative described in PATCH-2).
- **Default-if-nothing:** node stays red (34-census member).

## D-16-03 — F5b provenance-boundary defect (PATCH-3, REVISED ANALYSIS)

- **Current evidence (deeper than Phase 15):** run-10/11 offender list =
  **TWO** files, not one:
  `['reports/PHASE14_DECISION_MEMOS.md', 'reports/PHASE165_PROVENANCE.json']`.
  Both embed the PHASE162 zip sha by raw digest (Phase 22 converted to the
  named reference: `DELIVERY/RELEASE_HASH_PHASE162.txt`, record sha256
  `19668c805b1364a51dd8d993ff8eed123810d17035453b876f47aec7ff3542dc`):
  memos line 75 is my Phase-14 quote of the provenance input block;
  provenance line 63 is the original external-input doc. 6 further repo
  files embed the CURRENT shipped sha `5ce1025e…` (IMPLEMENTATION_STATE.md,
  NEXT_ACTIONS.md, reports/PHASE186_FORENSIC_AUDIT_REPORT.md,
  reports/PHASE186_RELEASE_INTEGRITY.md, reports/PHASE187_RELEASE_SECURITY_DIFF.md,
  tests/test_phase186_forensic_reconciliation.py) — release-record
  documentation, which the invariant would also flag IF its constants were
  advanced to the current candidate. The node's constants
  (ARCHIVE_NAME/DETACHED_NAME = "QuantEngine_PHASE162_*") lag 23 builds
  behind the shipped PHASE185 candidate, so the node currently greps for a
  HISTORICAL hash and red-flags legitimate historical documentation.
- **Exact proposed change (narrowest defensible):** in
  tests/test_release_consistency_phase155.py self-embed node, insert after
  the BUILD_MANIFEST skip (correctly scoped at the `continue` level):
  ```
  if "reports" in rel.parts and rel.name.endswith("_PROVENANCE.json"):
      continue
  ```
  AND, only if the owner also wants the node green, explicitly add the
  exact filename (not a class):
  ```
  if path.name == "PHASE14_DECISION_MEMOS.md":
      continue
  ```
  (comments citing this decision record). NO directory/class exclusions;
  positive test below proves real violations are still detected.
- **Patch reference:** `reports/PHASE15_OWNER_PATCHES.md` PATCH-3 (v1) +
  this D-16-03 revision (v2 = v1 + exact memos-file skip).
- **Focused validation (isolated copy, this phase):** v1 applied, real
  PHASE162 zip placed beside the copy, synthetic offender
  (reports/PHASE16SANDBOX_SYNTHETIC_OFFENDER.json embedding the real
  sha) — node FAILS listing the synthetic (visual: the assert message
  listed the offender set INCLUDING the synthetic while provenance was
  exempt; direct-python replication returned exactly
  `['reports/PHASE14_DECISION_MEMOS.md']` with v1-only) — i.e.:
  positive proof = genuine violations still detected; negative proof =
  the provenance record is handled correctly (exempt). v1 ALONE leaves the
  memos offender → node red; v1+memos-skip turns it green (owner choice).
- **Expected effect:** v1 = honest partial (documents why one offender
  remains); v1+exact-skip = node green with invariant intact for every
  other file; the 185-embed question is explicitly deferred to a separate
  owner decision on constant-advance policy (out of scope here).
- **Risks/reversibility:** minimal; test-file edit only; both skips are
  explicit name-level filters with recorded rationale.
- **Changes:** test behavior only.
- **Owner action:** choose one: (i) APPROVE PATCH-3 v1 (node stays red on
  memos), (ii) APPROVE PATCH-3 v2 (green), (iii) DECLINE both.
- **Default-if-nothing:** node stays red; classification stands.
- **Phase 22 RESOLUTION (supersedes both PATCH-3 options above):** the
  Named-Reference protocol was adopted — no tree text artifact embeds the
  byte digest of its own delivery archive; archives are referenced by
  name plus their detached hash record. Raw quoting in
  `PHASE14_DECISION_MEMOS.md`, `PHASE165_PROVENANCE.json` and
  `PHASE16_FINAL_REPORT.md` was converted to the named form;
  `tests/test_release_consistency_phase155.py` stays UNCHANGED (no skips
  added) and `tests/test_phase22_archive_hash_contract.py` adds the
  regression battery (repeated builds, deterministic ordering,
  meaningful content change, historical report handling).

## D-16-04 — B-02 Git ancestry (three options; owner chooses)

- **Current evidence (this phase, read-only):** two hand-recreated
  "Initial QuantEngine project" roots exist sharing identical
  author/committer timestamps (2026-07-24 22:06:07 +0530): delivery root
  `7a63a0a1493…` and orphan root `63cd4f1d8a9e…`; the Stage-123 closure
  tip `fad7329b24d6…` (subject matches the ancestry contract's own
  expectation, 2026-09-10 17:22) is not an ancestor of HEAD; trees of
  7a63a0a vs fad7329b differ by 8,406 diff lines (the restart root is not
  a tree-copy). `git replace -l` in the primary repo is EMPTY (no overlay
  applied). Full analysis + the 9 pinned tips + all affected node names
  are in the Phase-12/13 register sections and PHASE15afferent memos.
- **Corrected overlay (verified repeatedly in disposable copies only):**
  `git replace --graft 7a63a0a1493… fad7329b24d6…` → 9 ancestor assertions
  rc=0 + stage4 ancestry node PASS; `git replace -d` → red again
  (reversible; nothing committed to the primary .git).
- **Options (comparison; do not choose for the owner):**
  1. **NONE:** keep the 34-census behavior; overlay only ever in
     disposable copies. Cost: 25 nodes remain structurally red.
  2. **LOCAL DIAGNOSTIC OVERLAY:** owner-authorized local replacement-ref
     in the .git, freshly re-validated then left in place, tracked in the
     manifest-adjacent records. CAUTION: pulls the orphan lineage
     (`.env`-bearing commits e686ccd5/d5846fc3, root 63cd4f1d) into
     default `git log` views — sequencing says complete B-09/history
     decision FIRST (or consciously accept the widened exposure). Bypass
     semantics: `GIT_NO_REPLACE_OBJECTS=1`.
  3. **AUTHORITATIVE RECOVERY:** owner-controlled process to establish the
     true history (e.g., re-basing/finalize the delivery lineage from the
     recovered packs + evidence-backed parent determination). This is a
     HISTORY write — only with explicit instruction, out of agent scope.
- **Truthfulness status:** the proposed parent relationship
  (7a63a0a → fad7329b) is SUPPORTED (chronology: "Initial" root created
  2026-07-24 has the same stamp as the orphan initial root; fad7329b is
  the pre-restart era's final closure) but is NOT a recorded git fact;
  only the owner can certify it as authoritative.
- **Owner action:** pick option 1/2/3 explicitly.
- **Default-if-nothing:** option 1 (NONE) persists.

## D-16-05 — P192 evidence decision

- **Current evidence:** byte audit reproduced (246/104/53 frames;
  237,803/118,802/83,636 B; 16-prefix hashes `fb583558…`, `46443062…`,
  `bc3ea0f2…`; phantom `raw_l2_capture_20261021T091410Z.jsonl` ABSENT;
  claim A row + totals rows preserved verbatim in
  `reports/PHASE193A_DATASET_CORPUS_AUDIT.md`).
- **Paths (unchanged):** (1) narrowly-defined packet/provenance-path
  amendment, (2) block the record until the evidence is supplied, (3)
  leave the decision explicitly pending. No fabrication, no silent
  verification, no record rewrite.
- **Owner action:** declare PATH 1/2/3 (or provide the missing artifact /
  evidence and ask for re-verification).
- **Default-if-nothing:** `P192 = NOT VERIFIED / BLOCKED`.

## D-16-06 — Testnet authorization

- **Current evidence:** `reports/PHASE193A_TESTNET_AUTHORIZATION.md`
  unchanged (lines 5/6/67 fail-closed state; packet fields STILL missing:
  `operator_identity` [OPERATOR_IDENTITY_REQUIRED…], PGP fingerprint
  [PGP_FINGERPRINT_REQUIRED], `operator_signature`
  [OPERATOR_DETACHED_OR_INLINE_SIGNATURE_PAYLOAD_REQUIRED] — doc lines
  68-76). Offline gate validation (mock-only) green this phase
  (invariant battery + gated-exec mock suite); explicitly NOT proof of
  exchange interaction. No exchange writes attempted; none permitted.
- **Owner action:** either sign the approved packet (operator identity +
  PGP fingerprint + signature payload into the placeholder fields) or
  leave testnet not authorized.
- **Default-if-nothing:** `TESTNET_EXECUTION = NOT AUTHORIZED`.

## D-16-07 — Provider-side revocation evidence + B-09 closure checklist

- **Owner must supply/confirm (dated, provider-side):** (a) that the OLD
  production-named credentials tied to the 4 history commits
  (e49f61e1, d5846fc3, e686ccd5, 63cd4f1d) are REVOKED/disabled on the
  provider dashboard; (b) the replacement timeline (which key replaced
  which, when); (c) any provider incident/audit reference. NEVER the
  secret values themselves; never a re-transmission to the agent.
- **Local status (this phase):** `.env` unchanged since 2026-10-22
  18:38:08 (360 B, 9 assignments, DELTA_INDIA_TESTNET names present,
  0 malformed); scanner rc=1 (2 operator-local + 4 historical findings,
  unchanged); packaging/manifest exclusions verified intact;
  `OLD_CREDENTIAL_REVOCATION = NOT VERIFIED`.
- **B-09 closure needs (both pillars):** this D-16-07 checklist PLUS the
  B-08 history-remediation evidence (or an owner-authorized decision ON
  the history record itself — D-16-08). Do not close B-09 on rotation
  alone; historical blob exposure is a separate remediation problem.
- **Owner action:** provide the provider-side evidence; optionally
  confirm the local replacement report.
- **Default-if-nothing:** `CREDENTIAL_EXPOSURE_REMEDIATION = OPEN /
  NOT VERIFIED`.

## D-16-08 — Authoritative history remediation (B-08 pack)

- **Current evidence:** the Phase-13 history-remediation package remains
  the operative guidance; orphan lineage known (root 63cd4f1d reachable
  via `refs/heads/agents/todo-list-analysis-fix`, tip 699ca762…;
  originating lineage disjoint from origin/main tip 47fbecd…).
- **Owner action:** authorize a specific history path (NONE / overlay /
  authoritative recovery = D-16-04 choice) or provide the supplier-side
  decision if a remote repository action is required (fetch/push is
  agent-prohibited without explicit instruction; provider-side history
  cannot be verified locally).
- **Default-if-nothing:** history stays as-is; B-09 remains open.

---

## Non-choices the agent makes (recorded, not decided)

- `RELEASE_GATE = HOLD` stays; `EDGE = NOT ESTABLISHED` stays; testnet
  stays NOT AUTHORIZED; P192 stays blocked; B-09 stays open (see final
  report for the exact gates).
- No scanner/test weakening; no OOS/protocol edits; no fabricated
  artifacts; no secret disclosure; no destructive git operations; no
  network exchange contact.
