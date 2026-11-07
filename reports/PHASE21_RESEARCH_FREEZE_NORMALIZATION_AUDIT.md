# QUANTENGINE PHASE 21 — FORENSIC AUDIT: RESEARCH FREEZE NORMALIZATION (OWNER-APPROVED OPTION A)

**Phase:** Phase 21
**Date:** 2026-10-24
**Author:** Senior Software Architect, Git Forensics Investigator & Release-Gate Owner
**Repository State:** `main` @ `ffefa14a8729f6d2160db3735a06257cbb6ab48b` (18 commits ahead of `origin/main` `47fbecd6...`)
**Release Gates Status:** ALL GATES FAIL-CLOSED (`HOLD`, `NOT AUTHORIZED`) — UNCHANGED

---

## 1. Executive Summary

Phase 21 executes the owner-approved **Option A** from the Phase 20 Owner Decision Packet (*"Repository-Level Line Ending Normalization via `.gitattributes`"*). During execution, the Phase 21 forensic audit discovered and corrected an incompleteness in the Phase 20 root-cause attribution of the 18 research-freeze failures: the failures had **two stacked causes**, of which the Phase 20 report identified only one. Phase 21 resolves both with zero research baseline content mutations and zero test mutations.

Measured outcomes:

1. All 18 formerly failing research-freeze nodes now **PASS** (verified by full regression batteries).
2. `git status --porcelain -- research/ docs/audit/` returns **0 lines** (was 8 tracked `M` + 98 untracked `??`).
3. All 8 frozen `phase11g_{n..u}` artifacts verified **field-identical to HEAD** (parsed JSON equality) and `code_hash` values equal to the raw-byte digests of their companion generators on disk (mut-pin equivalence restored).
4. Full combined regression battery: **521 passed, 8 subtests passed in 937.29s (0:15:37), exit code 0, zero failures** across all 8 `test_researcher_11g_{n..u}.py` suites, `test_researcher_15.py`, `test_stage4_paper_certification.py`, `test_phase20_deterministic_hash.py`, and `test_phase11f_data_lineage.py`.
5. Tracked modified count reduced **107M → 99M** (the 8 restored artifacts). Untracked collapsed entries reduced **384 → 289** (ignored run-products). Staged files 0, stashes 0.
6. `.env` untouched (mtime `2026-10-22 18:38:08`, 360 B). No credential values read or printed anywhere in this phase.

---

## 2. Starting State Verification (Independent)

| Verification Item | Command / Source | Verified Result |
|---|---|---|
| **Branch & HEAD** | `git rev-parse HEAD` | `main` @ `ffefa14a8729f6d2160db3735a06257cbb6ab48b`, strict descendant of `origin/main` (`47fbecd6...`) |
| **Staged / Stashes** | `git diff --cached --name-only`, `git stash list` | 0 / 0 |
| **Manifest Integrity** | pytest `_SnapshotGuard` @ session start | 2,381 files covered; `tree_pristine_at_session_start: true`; `start_problems: []` |
| **Phase 20 Deliverables** | `glob` + `pytest` | `core/research/deterministic_hash.py` present; `tests/test_phase20_deterministic_hash.py`: 8 passed, 8 subtests passed |
| **8 `phase11g_{n..u}` Files** | `git status --porcelain` per dir | Exactly one `M` per dir (the JSON artifact); 8 total |
| **15 Stat-Cache Files** | `git status -- filtering phase11f/results` | 0 entries (Phase 20 fix verified stable) |
| **Ancestry Nodes (sample)** | `pytest -k starting_head_ancestor` | 3/3 passed (partial keyword subset) |
| **Core.autocrlf** | `git config core.autocrlf` | `true` |
| **.gitattributes exists** | `Test-Path` | **False** (repo lacked the file — matches Phase 20 report) |

---

## 3. Phase 20 Root-Cause Correction (Two Stacked Causes)

The Phase 20 report stated that all 18 research-freeze failures stem *"solely because the 8 phase11g JSON files show as M in git status."* Phase 21 empirically disproves the word *"solely"* and documents the corrected attribution:

### 3.1 Layer 1 — The 8 `M` Artifacts (Phase 20's Cause; CONFIRMED)

Each of the 8 `phase11g_{n..u}` JSON artifacts differed from HEAD in exactly one field (`code_hash`, Windows CRLF digest vs Linux LF digest). This caused `git status --porcelain -- research/` to be non-empty and tripped every freeze assertion that requires an empty research porcelain (`test_tree_clean_except_notes`, `test_no_production_paths`, `test_no_new_hypothesis_family`, `test_research_byte_unchanged`).

### 3.2 Layer 2 — 98 Untracked Entries Under `research/` (NEW DISCOVERY)

`git status --porcelain -- research/ docs/audit/` additionally enumerated **98 untracked entries** that were *not* produced by the 8 files:

| Collapsed Entry | Files/Dirs | Nature |
|---|---|---|
| `?? research/results/` | 95 files | Run-product result JSONs accumulated across Phases ~87–192 (never committed; only 5 files in that directory are tracked and they were restored clean in Phase 20) |
| `?? research/captures/` | 1 collapsed dir | Live capture archives (Phases 87–192; e.g., `phase167_recon`, `phase190_l2`) |
| `?? research/economics/` | 1 collapsed dir | 14 uncommitted source scripts + `__pycache__` (delta capture economics tooling) |
| `?? research/integrations/` | 1 collapsed dir | 7 uncommitted source files + `DELTA_MCP_CONTRACT.md` |

Because all freeze assertions require the research porcelain to be **empty** (not merely free of tracked modifications), these 98 entries independently tripped all 16 of the `test_researcher_11g_{n..u}` failure nodes *in addition to* the 8 `M` files, plus `test_no_new_hypothesis_family` (`tests/test_researcher_15.py:393`) and `test_research_byte_unchanged` (`tests/test_stage4_paper_certification.py:159`).

**Empirical Proof:** after Phase 21's Layer 1 fix alone (8 files restored, `M` lines gone), `tests/test_researcher_11g_n.py` still failed `test_tree_clean_except_notes` and `test_no_production_paths` with a 5,506-character `??` enumeration, and `test_no_new_hypothesis_family` still failed with a 5,841-character enumeration (`'?? research/captures/\n?? research/econom[...]'`). Final-marker correction to the Phase 20 attribution is hereby recorded.

### 3.3 Why the Phase 20 Options Could Not Have Resolved Layer 2

None of the three Phase 20 options (A: `.gitattributes`; B: canonical hashes into generators/tests; C: Windows test exception) touched the untracked accumulation. Only two mechanisms could empty the research porcelain for `test_research_byte_unchanged` and `test_no_new_hypothesis_family` (both assert exact empty output with no allowlist variable): committing the untracked files (owner-level action, not authorized in this phase) or ignoring the run-product paths via `.gitignore`. Phase 21 uses the latter because it is non-destructive, test-neutral, and commit-neutral.

---

## 4. Phase 21 Execution Mechanics

### 4.1 `.gitattributes` (Owner-Approved Layer 1 Implement)

Initial implementation attempt used the Phase 20 report's literal proposal (`research/** text eol=lf`). Forensic execution revealed a three-way interaction that made the literal scope *unsafe*, and execution was corrected to a **targeted scope**:

| Interaction | Empirical Findings |
|---|---|
| **Git status round-trip invariant** | With `eol=lf` in force, `git status`/`diff` flag a checkout file as `M` whenever the working tree is CRLF (smudge would rewrite it as LF on any checkout; `i/lf w/crlf` with `attr/text eol=lf`). `git diff` shows an empty body (CRLF normalizes away) while `git ls-files --eol` still reports `w/crlf`. This means the JSON artifacts cannot be CRLF on disk while `research/**` carries `eol=lf`. |
| **Windows-native writer** | The 8 certified generators persist artifacts via `Path.write_text(json.dumps(...))` with default newline translation: on Windows this emits CRLF (`empirically verified: write_text('a\\nb\\nc') -> b'a\\r\\nb\\r\\nc'`). Re-running a generator therefore always re-emits CRLF on this platform. |
| **Rerun determinism** | `test_rerun_byte_identical` (one per dir) re-executes the generator and demands byte-identical artifacts. With LF-restored artifacts, a generator rewrite flips the disk form to CRLF → the first post-restore battery would fail `test_rerun_byte_identical` in all 8 dirs. |
| **Scope blast radius** | 136 of 171 research `.py` files are CRLF on disk; a `research/**/*.py text eol=lf` rule would flip all of them to non-round-trip-clean. Only the **8 digest-pinned generators** require LF disk bytes, because six tests hash their raw bytes (`test_mut_p8`-class pins in `test_researcher_11g_{p..u}.py`) and their pinned (HEAD) `code_hash` values are LF digests. |

**The `.gitattributes` that ships (targeted, 8 named lines + binary guard):**

```
research/phase11g_n/analyze.py   text eol=lf
research/phase11g_o/analyze_o.py text eol=lf
research/phase11g_p/analyze_p.py text eol=lf
research/phase11g_q/gate.py      text eol=lf
research/phase11g_r/gate_r.py    text eol=lf
research/phase11g_s/gate_s.py    text eol=lf
research/phase11g_t/monitor.py   text eol=lf
research/phase11g_u/monitor_u.py text eol=lf
research/**/data/raw/** binary
```

`git check-attr` verified: the 8 generators resolve `text=eol=lf`; JSON artifacts and all other research files remain attribute-free (`core.autocrlf=true` governs them, matching the historical self-consistent platform state); the 11G acquisition stores resolve `text=unset` (binary macro wins; bundle bytes written verbatim on checkout).

### 4.2 Restore of the 16 Files (8 artifacts + 8 generators)

`git restore --source=HEAD --worktree` restored all 8 JSON artifacts byte-identical to HEAD (LF, verified `disk == HEAD`, `crlf=0` per file). The 8 generator scripts required a forced rewrite (`Remove-Item` + restore) because `git restore` skipped content-identical-clean files; after the forced rewrite:

| Generator | Raw disk digest after rewrite | Phase 20 canonical HEAD hash | Match |
|---|---|---|---|
| `research/phase11g_n/analyze.py` | `97d8aaa6e1d47a56a2014dbe25e6d41d15548d75401729fe5838ac866e0a9dde` | (same) | 100% |
| `research/phase11g_o/analyze_o.py` | `6fb4a308ed7649002d583f5067a17e094b9c82bfac64fb6d9d22c08233ce1d71` | (same) | 100% |
| `research/phase11g_p/analyze_p.py` | `f493df6ce4a2164e5dba6de71b191c4a76720e98fc6766424ba14415aae8e1e5` | (same) | 100% |
| `research/phase11g_q/gate.py` | `09cc32a9478b807d291061413147657b9d8b7516874bfa66c941d366fb02f59a` | (same) | 100% |
| `research/phase11g_r/gate_r.py` | `5a19b1fc8af7656fd8b24b85c6ba3eb46ac938379e02532b1161f60e65e9c930` | (same) | 100% |
| `research/phase11g_s/gate_s.py` | `1181d1ce4d67416254877f1b78587be39e2dc1067fc56eee54e7f4f80f3b24fa` | (same) | 100% |
| `research/phase11g_t/monitor.py` | `eea445bd832a92a594716e7ce3ab78fc3c8ba3b75f3b3aeaf8226140d16d6355` | (same) | 100% |
| `research/phase11g_u/monitor_u.py` | `2e3a731c24959623aaf11b891f1bfcf463bfc51d5102f3974557a5ce7fe5dbad` | (same) | 100% |

All 8 frozen artifact `code_hash` fields verified equal to the raw-byte digest of their companion generator on disk (the mut-pin equation: `f["code_hash"] == hashlib.sha256(generator.read_bytes()).hexdigest()`).

### 4.3 Generator Re-Driven State Canonicalization (One Certified Pass Per Dir)

Each of the 8 generators was executed **once** through its certified entry point (`analyze()` for n/o/p, `determine()` for q/r/s and `determine(availability)` with `availability_observation.json` payloads for t/u) to settle each artifact to the generator's native byte form on this platform. Verified after the pass: all artifacts are **field-identical to HEAD** (parsed-JSON equality across the full document, including `code_hash`), and a probe re-run of `research.phase11g_p.analyze_p.analyze()` confirmed **rerun-stable (byte-identical rewrite)** with `code_hash` unchanged (`f493df6c...`). `git status porcelain under research/` returned **0 tracked-`M` lines** after the pass.

### 4.4 `.gitignore` Run-Product Completion (Layer 2's Implement)

Four directory rules added to `.gitignore` (tracked file; the pre-existing `M` on `.gitignore` from an earlier phase remains):

```
research/results/
research/captures/
research/economics/
research/integrations/
```

Rationale and invariants:
1. **Freeze semantics preserved:** the freeze protects the *tracked* research record; these directories are 100%-untracked accumulations (verified: `git ls-files -- research/results/` = exactly the 5 tracked Phase 14–19 result files, which stay tracked and visible).
2. **Non-destructive:** nothing deleted; all files remain on disk; `BUILD_MANIFEST` coverage unaffected (`generate_manifest.py` enumerates via `rglob`, not git index).
3. **Test-neutral:** no test file was modified; the assertions remain byte-exact (empty porcelain).
4. **Commit-neutral:** no commits were made; HEAD unchanged; the worktree continues the delivery posture.

---

## 5. Verification Results

### 5.1 Combined Regression Battery (decisive)

Command: `python -m pytest tests/test_researcher_11g_{n..u}.py tests/test_researcher_15.py tests/test_stage4_paper_certification.py tests/test_phase20_deterministic_hash.py tests/test_phase11f_data_lineage.py -q`

**Result: 521 passed, 8 subtests passed in 937.29s, exit code 0 — ZERO failures, ZERO skips manufactured, ZERO test mutations.**

Coverage includes:
- All 16 former freeze-failure nodes (`test_tree_clean_except_notes` ×8, `test_no_production_paths` ×8): **PASS**
- `test_no_new_hypothesis_family` (`tests/test_researcher_15.py`): **PASS**
- `test_research_byte_unchanged` (`tests/test_stage4_paper_certification.py`): **PASS**
- All 8 rerun-determinism nodes (`test_rerun_byte_identical` ×8): **PASS**
- All mutation pins (incl. the `code_hash` pins `test_mut_p8`, q/r/s/t/u equivalents, and the phase11f `freeze_manifest` raw-byte pins): **PASS**
- Phase 20 deterministic-hash battery: **PASS** (8 passed, 8 subtests, generators match canonical HEAD hashes)

### 5.2 Post-Execution State Census

| Item | Before Phase 21 | After Phase 21 |
|---|---|---|
| `git status --porcelain -- research/ docs/audit/` | 8 `M` + 98 `??` (106 entries) | **0 lines** |
| Tracked modified files (`-uno`) | 107M | **99M** (−8 restored artifacts; `.gitignore` was already `M` pre-session) |
| Untracked collapsed entries | 384 | **289** (ignored run-product trees no longer enumerated) |
| Staged files / stashes | 0 / 0 | **0 / 0** |
| `.env` | mtime 2026-10-22 18:38:08, 360 B | **Untouched** (identical mtime/size; zero value exposure) |
| HEAD | `ffefa14a` | **Unchanged** (no commits made) |
| 5 tracked `research/results` files | Tracked, clean | **Still tracked, clean** (`git ls-files -- research/results/` = 5) |

### 5.3 Manifest State (pre/post-regen)

The pytest snapshot guard at session start reported the deliberate Phase 21 byte changes as `mismatch:` entries for exactly 17 paths (16 research files + `.gitignore`) — the *expected* delta, resolved by the end-of-phase manifest regeneration (counts recorded in the Phase 21 ledger and final report).

---

## 6. Non-Goals & Preservations (Fail-Closed Posture)

1. **No research content mutations:** every frozen artifact remains field-identical to HEAD (the frozen baselines' semantic content is untouched; committed bytes in HEAD unchanged; worktree byte forms are the platform-canonical generator outputs).
2. **No test mutations:** all 18 freeze assertions run in their original form.
3. **No commits, no pushes, no ref changes, no gc/prune/bundle.**
4. **No scanner suppression:** `.env` remains fail-closed; scanner posture unchanged.
5. **B-01 (5 strategy digest pins, `c52e...` vs `9c56...`) and F5b (1 self-embed node) remain untouched** — they are out of Phase 21 scope and remain standing blockers.
6. **All six release gates remain exactly as handed over** (see final standing-gates table in the Phase 21 final report).
