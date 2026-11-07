# PHASE 18 LINEAGE EVIDENCE (read-only forensics, nothing mutated)

Date: 2026-10-23 | Branch: main | HEAD: ffefa14a8729f6d2160db3735a06257cbb6ab48b
origin/main: 47fbecd656f01158a3065eb707b1a61e41b831f6 (FULLY CONTAINED in local HEAD; local is 18 commits ahead; nothing pushed or merged)
Manifest at session start: MANIFEST_PASS (0 problems), 2370 entries; census 122M / 384U / 0 staged / 0 stashes.
No history-rewriting, no `git replace`, no grafts, no ref mutation was performed. Everything below is derived from read-only
object inspection (`cat-file`, `rev-list`, `ls-tree`, `log`, `fsck --unreachable`) on the local object store.

## 1. Refs inventory (18 refs total)

- `refs/heads/main` -> ffefa14a (this working lineage; 18 local commits ahead of `origin/main`, whose tip
  is `docs: record Phase 17 focused certification` and will be listed in section 6).
- `refs/remotes/origin/main`, `refs/remotes/origin/HEAD` -> 47fbecd (same object).
- `refs/heads/agents/todo-list-analysis-fix` -> 699ca762 'first commit' (28 own commits; none carries `.env`).
- 13 refs `refs/agents/be5197f0-565d-4978-91a5-c4ccd71565b2/checkpoints/turn/{0..12}` — agent-session
  checkpoints with 1..25 own commits each, none carrying `.env` in trees. The flagged
  `e49f61e16329…` 'Agent host session be5197f0-…' commit is one of these checkpoint objects,
  flagged by the local scanner (see section 5).
- `refs/kilo/materialize/463ad8f281ca5401087c0abbb0223f0ea932` -> 190bfbdfd33b (a TREE object,
  not a commit; contains only `.env.example` (template) plus other paths — no live `.env`).

## 2. The nine ancestry seeds and the closure tip (exact objects)

All nine expected seed commits EXIST as objects but are UNREACHABLE from every ref
(`git rev-list --all` membership checked; `git fsck --unreachable` agrees).

| label | object | tree | first subject | author/committer datetime (+0530) | history depth | tree files | parents |
|-------|--------|------|---------------|-----------------------------------|---------------|------------|---------|
| 11g_n | 004b2bcbe5f3ea8ab0b4d2be246bbb25dde61db2 | 036ba5d2c5 | research(phase11g): validate real orderflow on independent holdout | 2026-09-09 15:05:55 | 144 | 1120 | 1 |
| 11g_o | 7c9d156d6076b0cc974fb5e0cf24bbe40c2ec3d2 | a00f997b52 | audit fresh-data scale and research eligibility | 2026-09-09 15:42:47 | 145 | 1162 | 1 = 11g_n seed |
| 11g_p | 501f082d1b037f1d9461d243310d68b95282a2a7 | fe5da6fbac | certify fresh-data expansion and OOS readiness | 2026-09-09 16:11:42 | 146 | 1168 | 1 = 11g_o seed |
| 11g_q | 57c22e1c68dcf0480c37cebbad494eaf8490afe9 | 4bb19beee6 | accumulate fresh data and gate full OOS readiness | 2026-09-09 18:15:08 | 147 | 1173 | 1 = 11g_p seed |
| 11g_r | 29959c536610be610653bf34ac7fd331270d96fa | 8fa8937400 | certify fresh full walk-forward OOS execution | 2026-09-09 18:41:52 | 148 | 1178 | 1 = 11g_q seed |
| 11g_s | 217a82553cd91dd886cb060e7f7ebc8245b7caa2 | 07e6fc3c3c | accumulate fresh data for full OOS readiness | 2026-09-09 19:41:44 | 149 | 1183 | 1 = 11g_r seed |
| 11g_t | 2942b57f85957e7a48546f9baea935d6437f39bd | 97f1c50819 | recheck fresh data for full OOS readiness | 2026-09-09 20:41:35 | 150 | 1188 | 1 = 11g_s seed |
| 11g_u | e88c3a0b39997de440cc56543141c096ee4ed4f7 | 1d87296191 | monitor fresh data qualification | 2026-09-09 21:21:13 | 151 | 1194 | 1 = 11g_t seed |
| closure_tip | fad7329b24d614794b35deb0b6926e5dd138977a | 46e16c9341 | feat(stage123): production hardening closure - 1:6 RR authority, cost model, reconciliation, restart/WS/order safety | author 2026-09-10 17:22:13; committer 17:36:03 | 154 | 1208 | 1 |

All author/committer identity values in the chain: `Vishal Kharade <vshlkhrde44@gmail.com>`.
None of the nine seed/closure-tip TREES contains an `.env` entry (final trees were clean).

## 3. The decisive structure — two parallel, subject-identical lineages

- The DANGLING chain: root = 63cd4f1d8a9ee840f53d66557551df2627245575, subject
  'Initial QuantEngine project', author epoch 1784910967 (2026-07-24 22:06:07 +0530), 154 commits,
  ending at the closure_tip fad7329b. The 11g_n..11g_u seeds are the consecutive phase-11g state
  positions of this chain (depths 144..151) and the chain is fully parent-connected
  (each seed's parent is the previous seed).
- The REACHABLE chain (current main): root = 7a63a0a1493ea81e58fc1bff809c09062250cc33, SAME subject,
  SAME author epoch 1784910967; 195 commits; its stage-123 closure commit is
  b42e8181406091bf06af18e312508a93924dcc37 ('feat(stage123): production hardening closure…',
  same subject; parent b9245fab73da).
- Position-by-position alignment (oldest→newest, comparing subjects):
  - Subjects: 154 of 154 aligned positions IDENTICAL (the reachable chain contains the same
    chronological storyline; its 41 additional commits are the post-closure phases).
  - Timestamps aligned: same author epoch values at matched positions (checked at idx 0..5, 143..153).
  - TREES: positions idx 114..153 (40 positions; the decontaminated mid/late history, including all
    eight 11g seed positions idx 143..150 and the Stage-123 closure idx 153) are EXACTLY
    TREE-EQUAL between the two chains (`b42e818` tree == `fad7329b` tree == 46e16c9341).
  - TREES: positions idx 0..113 (114 positions) DIFFER — and ONLY in exactly the positions where the
    dangling chain's tree contains a top-level `.env` while the reachable chain's tree does not:

| run-length pattern (aligned index runs) | count | treeEq | .env in orig-tree | .env in repl-tree |
|------------------------------------------|-------|--------|-------------------|-------------------|
| idx 0..113 | 114 | false | TRUE | FALSE |
| idx 114..153 | 40 | true | FALSE | FALSE |

  - Reachable chain (195 commits): 0 of 195 commit trees contain `.env` (verified directly).
  - Dangling chain: 114 of 154 commit trees contain `.env` (the original development era carried the
    working environment file inside every tree of that period; idx 0..113; then the state drops it —
    a normal removal-style transition — for idx 114..153).

Conclusion of the structure: the reachable lineage is a SUBJECT-ALIGNABLE, TIMESTAMP-PRESERVING,
TREE-DECONTAMINATED REBUILD of the original development lineage (the `.env` scrubbed from every
early commit state), continued forward with 41 post-closure commits. The 11g-phase TESTS still
reference the ORIGINAL seed object IDs, so their ancestry assertions (`merge-base --is-ancestor
<seed> HEAD`) invert to `1 != 0`. This is NOT a test defect: it is a lineage-labeling divergence
between the recorded expectations and the adopted (scrubbed) history.

## 4. Object classification (per the phase contract)

- 63cd4f1d / 7a63a0a roots: CLASS D pair (same subject+epoch, different trees — divergent
  re-records; the reachable one is the decontaminated copy).
- 11g seeds n..u + fad7329b: CLASS B+D hybrid — they are genuine historical project states with
  verifiable SUBJECT-CHAIN and TREE-CONTINUITY to the adopted lineage, but their IDENTITY-based
  lineage (reachable-from-ref ancestry) is broken relative to the current main. They are not
  'invented' objects; they are the original-era nodes that survived a lineage re-record.
- Agent checkpoint commits (13 refs) and 699ca762 'first commit' branch: CLASS A for themselves
  they are what their subject claims (agent session snapshots), unrelated to the 11g lineage chain.
- The kilo TREE ref: non-commit, safe, contains only the `.env.example` template.

## 5. Historical secret-exposure risk (names and object IDs only; no contents read or printed)

- The ONLY `.env`-bearing commit trees in the entire object store are the 114 DANGLING-chain
  positions (idx 0..113). Distinct `.env` blob objects found in those trees: 4
  (8e41290abe7b…, 3aa585334e81…, f94455980016…, 7275411a704f…) — blob IDs recorded as OBJECT IDs
  only; their contents were NOT read, printed, copied, or transmitted. Blob lifetimes:
  1, 1, 27, and 85 commits respectively (indicating at least 4 distinct historical env file states).
- Reachable lineages (main 195, origin/main, agents checkpoints, todo-list branch): 0 `.env`
  tree entries. The current working `.env` remains untracked + ignored (posture unchanged from
  prior phases; mtime/size re-verified earlier this session in WS-C).
- Therefore: AGENT-side risk is that these dangling objects CONTAIN ORIGINAL credential states;
  they are not reachable by any normal clone/fetch (no ref points into the chain), but they REMAIN
  physically present in the local object store and could be recovered by forensic tooling.
  Publishing any object bundle that includes them would be an exposure event: DO NOT create
  bundles/pushes that include unreachable objects without an owner decision (see
  PHASE18_OWNER_DECISIONS.md Option A/B security rows).

## 6. Relationship between local HEAD and origin/main (verified, not merged)

- `git rev-list --count HEAD ^origin/main` = 18; `origin/main ^HEAD` = 0 → origin/main IS an
  ancestor of local HEAD; local is 18 commits AHEAD (the phase 1..14-era certified commits:
  '2de2bb0 Phase 1 …', '…Phase 14: contract fail-closed certification…', 'd04fe83 External
  evidence: genuine Delta public products snapshot…', '6ca5628 Delta sandbox environment
  separation…', '8b530f2 Real-market-data paper preview…', '81aa7cc …paper_preview.py…',
  'ffefa14 Serve dashboard shell without bearer token…'). Nothing was pushed; no merge needed;
  no divergence exists. Origin therefore provides NO separate lineage authority — the entire
  authoritative-question reduces to the LOCAL object store.

## 7. Provenance conclusion

- An authoritative ORIGINAL LINEAGE EXISTS in the object store (the dangling 154-commit chain),
  and its content semantics for the mid/late history (idx 114..153) is IDENTICAL (tree-equal) to
  the adopted lineage. The early history differs from the adopted one ONLY by the presence
  of `.env` inside its trees.
- The adopted lineage (current main) is a decontaminated re-record of it. This makes the lineage
  question DECIDABLE by the owner with full evidence: the expected 11g seed objects are
  demonstrably the same narrative positions in the adopted chain (8 aligned idx 143..150 AND
  closure idx 153, tree-equal + subject-equal + timestamp-equal), so 'authoritative lineage' for
  the LATE history is effectively PRESERVED; what is NOT preservable without a rewrite is
  the ORIGINAL (pre-scrub) early history, which CARRIES THE SECRETS.
- Trustworthy sources evaluated: local object store only (origin adds nothing: ancestor-of-local
  only; no bundles/archives present that carry a `.git` directory worth comparing during this
  session — the delivery zips are source archives without `.git` per `tests/evidence_mode.py`
  documentation).

## 8. Safest next actions and NOT-EXECUTED mutations

- SAFEST immediate action (read-only, already performed): record this document; keep the
  unreachable objects in place (do not run `git gc`/`git prune`/`git repack` — any of those could
  DESTROY the historical evidence chain and is OWNER-CONTROLLED).
- Mutations that would move the repository FORWARD are listed for the owner ONLY; NONE executed:
  1. `git bundle create QuantEngine_lineage_original.bundle fad7329b24d614794b35deb0b6926e5dd138977a` —
     would emit a bundle containing the full original chain INCLUDING the 114 `.env`-bearing commits.
     SECURITY: DO NOT transmit/publish; physical-inspection artifact only (marked NOT EXECUTED).
  2. Owner-approved re-registration (Option B in PHASE18_OWNER_DECISIONS.md) would patch the NINE
     ancestry expectations to the aligned replica positions
     (11g_n -> acab874d1a, 11g_o -> 5c95fd623f, 11g_p -> 6a961459ae, 11g_q -> e1483a1090,
     11g_r -> bd21e9ac06, 11g_s -> d77af19e85, 11g_t -> e235663d2a, 11g_u -> 0e4d3f04ce,
     closure -> b42e8181406) — NOT EXECUTED; requires owner approval and a provenance record.
  3. Owner-approved full recovery (Option A) would require HISTORY REWRITE on main
     (`git filter-repo`/`filter-branch` or re-rooting), releasing the original chain as refs —
     NOT EXECUTED; carries the 114 `.env`-bearing states forward and therefore conflicts with the
     standing decontamination decision.
- gc/prune/repair warnings: `git fsck --unreachable` output enumerated the dangling commits —
  a hard crash or gc could permanently destroy them. The 11g originals would then be
  UNRECOVERABLE (no remote/backups carry them: verified above). This is the PRIMARY preservation
  risk right now: autonomous gc is forbidden, and owner preservation actions are urgent-ish but
  not immediate.

## 9. Whether authoritative recovery is technically and evidentially possible — CONCLUSION

- POSSIBLE, with sharply limited scope and a security constraint: the original chain exists and is
  fully traversable; the adopted chain aligns with it position-for-position with
  subject+timestamp+tree equality over the last 40 positions (all 8 11g seeds + closure included).
- TECHNICAL REQUEST (Option A as written) would reintroduce the removed secrets into any
  recovery-made lineage — the recommended path is therefore Option B (re-register the canonical
  baseline at the SCRUBBED lineage) plus a documented preservation record of the original chain
  object IDs (this document), and NOT the raw recovery path.
- If the owner prefers preservation without any tree or test mutation: Option C remains blocked and
  the nine ancestry nodes stay red by design, with this document as the explanation.
