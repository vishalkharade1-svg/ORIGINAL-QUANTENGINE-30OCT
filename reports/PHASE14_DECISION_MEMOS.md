# PHASE 14 — DECISION MEMOS (workstreams D, plus earlier A/B/C packages)

Status: PROPOSED — NOT APPLIED. Every change below requires explicit owner approval.
Prepared by: Phase 14 agent (HEAD ffefa14a8729f6d2160db3735a06257cbb6ab48b, 2026-10-22).

## PHASE 15 REFRESH (2026-10-23) — all memos re-validated; two new facts folded in

1. Every reproducible claim in this file was re-verified on 2026-10-23 and
   stands unchanged (B-01 pin sites/digest, B-02 overlay behavior, F4/F5b
   reproductions, testnet fail-closed state, run-9 timing classification,
   P192 byte reality, scanner categories, zip isolation).
2. NEW for B-01: the project's own read-only procedure
   (`scripts/recertify_strategy_digest.py`) reports `matches_recorded=false`
   and `status=BLOCKED` — canonical digest (CRLF→LF construction) =
   `ba17582d0ab96913f81d0e6ac652368e609bb28f22a24200f53bf9b6cd60ded5`.
   The four-substitution PIN re-registration therefore remains a
   RELEASE-LINEAGE REPAIR (worktree == released bytes), not a strategy
   re-certification; `EDGE NOT ESTABLISHED` is unaffected either way.
3. NEW for B-09: the local `.env` has not changed since 2026-10-22 18:38:08
   (same shape/names audited in Phase 14) — the operator's replacement claim
   has no local evidence (`REPORTED BUT NOT REPRODUCED`); provider-side
   revocation has none either (`NOT VERIFIED`); history scope unchanged.
4. Exact apply-ready diffs for B-01/F4/F5b now live in
   `reports/PHASE15_OWNER_PATCHES.md` (PATCH-1/2/3, each with test plan and
   application protocol). Those diffs supersede the summary-level change
   descriptions below for execution purposes.

---

## MEMO F4 — stage4 sequential-ledger fixture per-direction geometry

- Exact failing test: `tests/test_stage4_paper_certification.py::TestPaperAccounting::test_sequential_ledger_matches_registry`
  (assert at line 319). Reproduced today: `AssertionError: 1 != 2`.
  Captured log: `ERROR core.backtesting.trade_simulator:trade_simulator.py:254 OPEN_TRADE_VALIDATION_FAILED setup_id=T-160.0 reason=Inconsistent BEARISH geometry: stop_loss (150.0) < entry (160.0).`
- Current assertion: `self.assertEqual(len(closed), 2)` after two sequential
  open/update rounds; per-trade net-PnL identity
  (`pnl == net_pnl(gross_pnl(...), commission, slippage)`) at lines 320-325.
  Fixture `mk()` is direction-agnostic: `stop_loss=e-10.0`, `take_profit=e+60.0`
  (lines 308-309); leg 2 is `mk("BEARISH", 160.0, i="T")` → stop 150.0 < entry
  160.0 and tp 220.0 ≥ entry 160.0, refused by the frozen fail-closed guard
  `core/backtesting/trade.py:184-192` ("BEARISH stop must sit above entry and
  TP below entry"), so the short leg never opens and only 1 trade closes.
- Intended invariant: sequential ledger == registry net accounting across two
  in-bar-closed legs (bookkeeping integrity, NOT geometry rejection semantics).
- Smallest change (test-only, 2 lines, preserves the BEARISH leg):
  1. `mk()` becomes direction-conditional — BULLISH: `stop_loss=e-10.0`,
     `take_profit=e+60.0` (unchanged); BEARISH: `stop_loss=e+10.0`,
     `take_profit=e-60.0` (same 1:6 R geometry, `risk_reward=6.0` literal stays).
  2. Second update bar high `161.0` → `171.0` so the short's stop (170.0) is
     hit and the leg closes in-bar (close/low values untouched); exit at
     170.0 → gross `(160-170)*2 = -20`, net identity unchanged.
  1-line alternative (weaker, not recommended): flip leg 2 to BULLISH —
  keeps bar 4 untouched but stops exercising a BEARISH sequential leg.
- Affected tests/artifacts: this single function (blast-radius grep: `mk`
  lambda and `T-160.0` referenced nowhere else in tests/). No engine change,
  no production-code risk, no RR/sizing change. Optional follow-up (separate
  decision): add an explicit rejection-semantics test for the BEARISH guard;
  not required by this memo.
- Value if approved: node green without weakening (the invariant tested is
  what it ever intended: sequential + net identity). If rejected: node stays
  red; record as known fixture-drift failure in
  `EVIDENCE/PHASE19X_FORENSIC/PHASE11_FAILURE_REGISTER.md`.

## MEMO F5b — Phase155 self-reference scan vs provenance input documentation

- Exact failing test: `tests/test_release_consistency_phase155.py::TestReleaseConsistency155::test_no_text_artifact_embeds_own_archive_hash`
  (assert at lines 129-130). Reproduced today:
  `offender: ['reports/PHASE165_PROVENANCE.json']`.
- Current assertion: no packaged text artifact (`*.md|*.json|*.txt|*.py|*.sha256`,
  except `BUILD_MANIFEST.sha256` and `QuantEngine_*.zip`, lines 116-121)
  embeds the SHA-256 of the CURRENT archive (`QuantEngine_PHASE162_RELEASE_CANDIDATE.zip`,
  constants at lines 45-46 advance each rebuild).
- Actual offender: `reports/PHASE165_PROVENANCE.json` lines 61-64 —
  `"input": {"archive": "QuantEngine_PHASE162_RELEASE_CANDIDATE.zip",
  "sha256": "<archive digest, now referenced by name + detached record:
  DELIVERY/RELEASE_HASH_PHASE162.txt, record sha256
  19668c805b1364a51dd8d993ff8eed123810d17035453b876f47aec7ff3542dc>"}`
  — a legitimate INPUT provenance pin (what the provenance record was
  computed from), which happens to equal the current archive's hash.
- Intended invariant: ban unprovable SELF-reference (a file claiming to hash
  the very archive it ships inside — the Phase154 stale-hash defect). A
  provenance record's input-pin describes an external artifact and is
  documentation, not self-embedding.
- Smallest change (test-only, scan-boundary refinement mirroring the existing
  structural skips): add `reports/*_PROVENANCE.json` to the skip list at
  lines 111-121 (same mechanism as `BUILD_MANIFEST.sha256` / `QuantEngine_*.zip`).
  The provenance record itself stays byte-frozen. Alternative (equally
  accepted): strip the `"input"` key before hashing the searched text —
  narrower but more code. NOT acceptable: editing the frozen provenance JSON.
- Affected tests/artifacts: `tests/test_release_consistency_phase155.py` only.
  Companion node `test_worktree_verifies_against_manifest` (lines 66-68) is
  red solely because of the pre-existing one-file manifest mismatch
  (`tests/test_phase192_multiprocess_ledger.py`) and resolves with the Phase 14
  final manifest regeneration — not part of this memo.
- Value if approved: closes the release-consistency-family red without
  weakening (bounded, documented skip, not a removal). If rejected: keep red
  and document as scan-boundary collision in the register.
- Phase 22 RESOLUTION (supersedes the test-only proposal above): the
  Named-Reference protocol — no tree text artifact may embed the byte
  digest of its own delivery archive; archives are referenced by name
  plus their detached hash record (`DELIVERY/RELEASE_HASH_PHASE162.txt`,
  record sha256 `19668c805b1364a51dd8d993ff8eed123810d17035453b876f47aec7ff3542dc`),
  which lives outside the tree and joins no fixpoint. The raw quoting in
  this memo, `PHASE165_PROVENANCE.json`, `PHASE16_FINAL_REPORT.md` and
  `PHASE16_OWNER_DECISIONS.md` was converted to the named form;
  `tests/test_release_consistency_phase155.py` stays UNCHANGED (no skip)
  and `tests/test_phase22_archive_hash_contract.py` adds the regression
  battery (repeated builds, deterministic ordering, meaningful content
  change, historical report handling).

---

## (carry-over) MEMO B-01 — stale strategy digest re-registration

Verified (test construction: per-file sha256 → hex-join → sha256 of joined
string, `tests/test_oos_feasibility_17.py:107-116`):
- worktree digest == PHASE185 archive digest: `9c56f3ff7dea2a3ea98adf226aff775d263ebfcf1bbb2697ca244ab6cd54f35a`
- HEAD-committed digest: `9eff61b777846c7f5e2056c486c9c381872a93e154d35160e70f63051c8fd8a2`
- pinned constant today (STALE): `c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6`
- PHASE165..185 all embed the `9c56f3ff…` epoch (21 zips verified); the
  pre-165 epoch `f8407e77…` explains the pin's age, not a strategy change.
Proposed change (owner approval required; suggested diff ready, not applied):
- `tests/test_oos_feasibility_17.py:42`, `tests/test_oos_validation_18.py:38`,
  `tests/test_oos_data_extension_19.py:38`: `c52e648c…` → `9c56f3ff…`
- `research/results/phase14_executable_edge_forensics.json:1029`
  (`strategy_hash`): `c52e648c…` → `9c56f3ff…`
- `tests/test_readiness_16.py` needs NO source edit; its assert fails only
  while the forensics artifact still carries the stale hash.
After approval this turns 5 currently-red nodes green
(oos_17 identity, oos_18 identity + no_strategy_mutation, oos_19:95,
readiness_16:557). Per-file digests match the Phase 13 table exactly; the
earlier "aggregate mismatch" was an agent computation bug (14-file join),
withdrawn. Files are CRLF in worktree vs LF in HEAD blobs (autocrlf); only
`tests/test_readiness_16.py` carries a real (non-eol) worktree diff.

## (carry-over) MEMO B-02 — reachability overlay for orphan lineage

Verified facts: 9 pinned commits chain gap-free to re-created root
`63cd4f1d8a9ee840f53d66557551df2627245575` (same author/committer/date/message
as delivery root `7a63a0a1493ea81e58fc1bff809c09062250cc33`, different tree).
Graphs disjoint; pins reachable from no ref; `63cd4f1d` reachable ONLY from
`refs/heads/agents/todo-list-analysis-fix`; secret-bearing commits `e686ccd5`
("Build 2.7 - REST Client v2") and `d5846fc3` ("Build 2.8 - Market Registry")
sit inside the pinned lineage; tip of that lineage is
`fad7329b24d614794b35deb0b6926e5dd138977a` (stage123 closure).

Phase 13's proposed command (`git replace --graft 7a63a0a 63cd4f1d`) was
tested in a disposable copy and is INSUFFICIENT: it improves root ancestry but
all 9 pin-vs-HEAD ancestor assertions stay red. The corrected command passed
the actual pytest nodes (25-node F1 family; representative subset run today):

    git replace --graft 7a63a0a1493ea81e58fc1bff809c09062250cc33 \
                        fad7329b24d614794b35deb0b6926e5dd138977a

Disposable-copy pytest results (branch `main` checked out at ffefa14):
- before graft: ancestor nodes red (`9 failed`)
- with graft: `8 passed, 1 failed` — the 1 failure was only
  `branch --show-current != main` caused by my detached probe worktree;
  re-run on a named-branch worktree: `1 passed` under graft, `1 failed` after
  `git replace -d` (reversible; overlay is the sole effect).
- bypass: `GIT_NO_REPLACE_OBJECTS=1` or `--no-replace-objects` (rc 1),
  so the overlay cannot silently leak into isolation runs that opt out.
Reversal: `git replace -d 7a63a0a1493ea81e58fc1bff809c09062250cc33`.
Risks sequenced BEFORE any adoption: the overlay pulls the orphan lineage
(incl. `63cd4f1d` whose tree contains `.env`, and the Build-2.x secret
commits) into main's default `git log`/`rev-list` views. Credential
remediation (B-09) should be completed FIRST, or consciously accepted.
Test evidence from an overlay stays a test about the overlay, not recovered
history (per rule 9). PROPOSED — NOT APPLIED anywhere (primary repo has no
refs/replace; disposable copy left replace-free, worktrees pruned).

## (carry-over) MEMO A — run-9 `test_03_lock_contention_and_bounded_timeout`

Classification: TEST SYNCHRONIZATION DEFECT (test-only false positive).
- run-9 (`C:\Users\Admin\AppData\Local\Temp\opencode\pytest_full9.log`) ran the
  OLD test bytes: 50×0.02s=1.0s advisory `ready_flag` window; slow child start
  (1.02/1.2/1.5s in forced-slow probes) always misses it →
  `AssertionError: LockTimeoutError not raised` (exact run-9 symptom,
  reproduced 6/6 under load with `repro_compare.py`).
- current worktree bytes (untracked, edited post-run-9 by an unknown party —
  ledger inconsistency, not our edit): kernel-lock witness
  `_lock_is_held_elsewhere` loop, 150×0.02s=3.0s window → 5/5 pass isolated,
  5/5 under 4-spinner load, 6/6 PASS-EQUIV in forced-slow probes; node passes
  in the full file run (12/12, 5.07s).
- production lock (`core/execution/testnet_authorization_gate.py`,
  `CrossProcessFileLock` L148, bounded kernel-lock polling, thread-local
  reentrancy) verified sound; no engine change needed.
- NOTE: this is the single `BUILD_MANIFEST.sha256` mismatch; final Phase 14
  manifest regeneration (owner-planned end step) will pin the hardened bytes.
NO repo change made by Phase 14 agent on this workstream.
Repro harnesses kept at `C:\Users\Admin\AppData\Local\Temp\opencode\p14_repro\`.

---

## MEMO B-09/E — credential exposure remediation: verification results + operator checklist

Verification performed by Phase 14 agent (no values printed anywhere; names,
sizes, commit ids, counts only):

- `python scripts/security/scan_secrets.py --check-history` → exit 1 (fail
  closed, by design): 2 worktree findings on the operator-local root `.env`
  (lines 1-2, rule `non_empty_known_secret`) and 4 unsafe history commits:
  `e686ccd56fd0…` (249 B), `d5846fc38815…` (323 B), `e49f61e16329…` (323 B),
  `63cd4f1d8a9e…` (185 B) — each containing non-empty `DELTA_API_KEY` +
  `DELTA_API_SECRET` assignments. No other credential names flagged
  (`OPENAI/ANTHROPIC/OPENROUTER/CONTROL_API_TOKEN/REMOTE_*` clean).
- Tracked tree: `git ls-tree ffefa14 -- .env` → empty; `.env` ignored via
  `.gitignore:6`, unstaged, operator-local. Object graph (`rev-list --objects
  --all`) contains only the single safe element `.env.example` plus the
  `.env` blobs of the 4 commits above.
- Delivery packages: all 23 zips (`PHASE161,162,165..185`) verified with
  tar listings — ZERO `.git/` members and ZERO live `.env` members; the
  single `.env`-pattern hit per zip is `.env.example` (the safe template).
  → previously shipped artifacts did NOT carry live credentials.
- Live worktree `.env` (360 B) holds the india-testnet pair
  (`DELTA_INDIA_TESTNET_API_KEY` + `DELTA_INDIA_TESTNET_API_SECRET`).

OPERATOR CHECKLIST (owner-only, none executed by the agent):
1. ROTATE the production-named pair (`DELTA_API_KEY`, `DELTA_API_SECRET`):
   they have been materialized in 4 git blobs (oldest `e686ccd5`) and must
   be treated as burned. Issue fresh keys on the provider and never write
   them to a file inside this repository tree again.
2. ROTATE the live india-testnet pair as well if any external copy of the
   workstation or repo folder could exist (conservative default: rotate).
3. Choose the history posture (owner decision):
   a. accept + document (Phase 9 posture — repo not published);
   b. filter-repo rewrite of the orphan chain (`agents/todo-list-analysis-fix`)
      — invalidates every recorded pin hash and stalls B-01/B-02 adoption;
      must not run silently;
   c. delete `refs/heads/agents/todo-list-analysis-fix` + the 13 agent
      checkpoint refs, then `git reflog expire --expire=now --all` and
      `git gc --prune=now` — makes `rev-list --all` clean for the history
      gate, but destroys reflog evidence and checkpoint refs.
   Sequencing: if B-02 (overlay) is adopted, complete credential remediation
   FIRST, because the overlay widens default-view exposure of the orphans.
4. Shred temp copies after sign-off: `C:\Users\Admin\AppData\Local\Temp\opencode\p14_b02\`
   (gitcopy + probe worktrees replicate the full object graph including the
   4 secret blobs).
5. Acceptance gate: rerun
   `python scripts/security/scan_secrets.py --check-history` → expect
   0 history commits and 0 worktree findings (after rotation and cleanup).
Status stays `CREDENTIAL_EXPOSURE_REMEDIATION = OPEN / NOT VERIFIED` until
owner signs off.

---

## WORKSTREAM F — testnet authorization readiness review (observations only)

- State re-read: `reports/PHASE193A_TESTNET_AUTHORIZATION.md` lines 5-6 remain
  `PENDING_OPERATOR_APPROVAL` / `STRICTLY_BLOCKED / NOT_AUTHORIZED_FOR_EXECUTION`;
  zero-reorder invariant line 8 intact; audit table (lines 83-88) unamended.
- Fail-closed confirmed at all three enforcement sites:
  - `scripts/bounded_testnet_order_experiment.py`: auth-doc parse + state
    check at lines 129-139 (`EXPERIMENT_REFUSED` unless operator-approved),
    endpoint validation via `validate_endpoints("india_testnet")` lines
    143-148, constructed-endpoint re-check line 157-158, and dedicated
    testnet-credential requirement lines 149-152.
  - `scripts/bounded_testnet_reconciled_experiment.py` lines 118-143 (same
    gate pattern, `EXPERIMENT_REFUSED` on execution branch).
  - `scripts/funding_settlement_hold.py` line 32 (`AUTH_DOC_PATH` =
    PHASE193A, superseding the stale Phase-189 reference).
- Endpoint separation (static): experiment scripts hard-code
  `https://cdn-ind.testnet.deltaex.org` / `wss://socket-ind.testnet.deltaex.org`
  (`bounded_testnet_order_experiment.py:58-59`); production endpoints appear
  only in read-only market-data capture scripts and the environment registry
  (`research/economics/delta_environment.py:17-19`), never in the
  order-write path.
- Credentials (checklist item 14): worktree `.env` carries ONLY the
  india-testnet pair names (`DELTA_INDIA_TESTNET_API_KEY`,
  `DELTA_INDIA_TESTNET_API_SECRET`); production-pair names are absent from
  the live file (values never printed/inspected by the agent).
- Test evidence (checklist item 4): focused run
  `pytest tests -k "phase189 or phase190 or phase191 or phase192 or phase193"`
  → **173 passed / 0 failed / 27 subtests passed (45.65s)** — exceeds the
  doc's 118-test precondition. One pre-existing red remains tracked
  elsewhere: the single BUILD_MANIFEST mismatch (`test_phase192_
  multiprocess_ledger.py`, hardened post-run-9 bytes — Workstream A).
- Operator-only items (2,3,5,6,7,8 of the doc's checklist: live account
  audit, live book tracker, ledger init state) are NOT executable by the
  agent and remain open.
- OPERATOR EXECUTION READINESS: **PENDING** — unchanged from Phase 12/13.
  Nothing was executed against any endpoint; no `--dry-run` or `--execute`
  was invoked by the agent. The 15-row validation checklist in the packet
  proposal stays blocked at row 1 (`state:` flip) until the operator signs.

---

## WORKSTREAM G — P192 provenance verification (refresh, decision unchanged)

Re-audited today at byte level (strict reads; no network):

- `research/captures/phase192_l2/` contains exactly one raw capture:
  `raw_l2_capture_20261021T085017Z.jsonl` — 83,636 B,
  sha256 `bc3ea0f233c89010c08f81afa324bf433975f71cb7d66915cd307d11a4ca9c2e`,
  **53 data frames**, strict-UTF-8 decodable, pairwise JSONL-parseable.
  The phantom `raw_l2_capture_20261021T091410Z.jsonl` is ABSENT.
- Extended full hashes for the other two audited captures:
  `phase190`: `fb5835589028693bd6a8bfcf1b72d6515c622e91804d4c41d37acc027279076d`
  (237,803 B, **246 frames**); `phase191`:
  `464430627e6fc38835bbe2f7d9dcebe6c120e0cb2bfa746416fe1a866e28d1aa`
  (118,802 B, **104 frames**). All strict-UTF-8/JSONL-parseable. Each dir
  also holds its `l2_quality_summary_*.json` (present).
- Corpus totals recomputed: 237,803 + 118,802 + 83,636 = **440,241 B**;
  246 + 104 + 53 = **403 frames** — exactly the corrected totals in the
  Phase 12 packet.
- Claim A confirmed VERBATIM still in
  `reports/PHASE193A_DATASET_CORPUS_AUDIT.md` row 19 (121,682 /
  `c7bf98c56fa244196d44ae4b54e3d93fd9fc177f10b777a83492576b911b332b` /
  104 frames) and totals row 20 (478,287 B / 454 frames). Claim B short
  form (`c7bf98c56fa769dbe06eeeb4e28e4693a129037cbe113ea4b81585223dd588b3`)
  remains recorded in the packet proposal section. NEITHER hash attaches to
  any file in this tree.
- Decision unchanged (owner-only): `DEC-P192-1/2/3` stand exactly as written
  in `reports/PHASE193A_TESTNET_AUTHORIZATION_PACKET_PROPOSAL.md`
  ("P192 DECISION RECORD"); option 1 remains the recommended traceable
  amendment (append-only; no capture bytes synthesized). Until the owner
  decides, P192 stays `NOT VERIFIED / BLOCKED` and the audit totals stay
  uncorrected by the agent.
