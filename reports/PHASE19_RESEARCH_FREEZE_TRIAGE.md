# QuantEngine Phase 19: Research Freeze Diagnostic & Triage Report

**Phase:** Phase 19 (Controlled Repair, Manifest Hygiene, and Research Freeze Triage)  
**Author:** QuantEngine Senior Software Architect & Forensic Release Gate Owner  
**Date:** 2026-10-24  
**Classification:** Diagnostic Forensics & Release Integrity  
**Status:** Completed — Owner Action Packet  

---

## 1. Executive Summary

During Phase 18 and Phase 19 baseline verification, `git status` reported **23 modified files** under the `research/` tree. Under the standing research freeze policy (§11G freeze, Phase 15 non-expansion contract), any modification under `research/` triggers automated test failures in `test_researcher_11g_{n..u}.py`, `test_researcher_15.py`, and `test_stage4_paper_certification.py` (accounting for **18 failing test nodes** in the test census).

This report presents a file-by-file forensic inspection of all 23 files without auto-repairing or reverting.

### Key Forensic Findings:
1. **15 Files are 100% Byte-Identical to HEAD (`matches_head=True`)**:
   - All 10 files under `research/phase11f/` and all 5 files under `research/results/` have identical byte lengths, identical SHA-256 hashes, and produce **zero diff** (`git diff HEAD` is empty).
   - `git status` reported them as `modified` exclusively due to a stale Git stat cache (mtime/inode discrepancy in `.git/index`) created during prior environment extraction or tooling runs on Windows.
2. **8 Files Differ by Exactly 1 Line: `"code_hash"`**:
   - The 8 files in `research/phase11g_{n..u}/` (`feasibility.json`, `trigger_q.json`, `readiness_{p,r,s,t,u}.json`) match `BUILD_MANIFEST.sha256` 100%.
   - The only difference between working tree and Git HEAD is a single string field: `"code_hash"`.
   - Root cause: The builder scripts (`analyze.py`, `gate_r.py`, `monitor.py`) compute `result["code_hash"] = _sha256_bytes(Path(__file__).read_bytes())`. On Windows with CRLF checkouts, hashing `__file__` produces the Windows CRLF SHA-256 hash, whereas HEAD was committed with Linux LF line endings.
   - **Zero research data, parameters, cutoffs, datasets, or hypothesis definitions were altered.**
3. **100% Manifest Compliance**:
   - Every single one of the 23 files on disk matches its SHA-256 hash in `BUILD_MANIFEST.sha256`.

---

## 2. Comprehensive File Inventory & Hash Matrix

| # | File Path | Work Bytes | HEAD Bytes | Work SHA-256 | HEAD SHA-256 | Manifest SHA-256 | Match HEAD | Match Manifest | Diff vs HEAD |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `research/phase11f/candidates.py` | 21,042 | 21,042 | `255d784f...` | `255d784f...` | `255d784f...` | **YES** | **YES** | None (0 lines) |
| 2 | `research/phase11f/contracts.py` | 11,064 | 11,064 | `75b60059...` | `75b60059...` | `75b60059...` | **YES** | **YES** | None (0 lines) |
| 3 | `research/phase11f/datasets.json` | 2,364 | 2,364 | `411eaa45...` | `411eaa45...` | `411eaa45...` | **YES** | **YES** | None (0 lines) |
| 4 | `research/phase11f/datasets.py` | 13,878 | 13,878 | `b78bb256...` | `b78bb256...` | `b78bb256...` | **YES** | **YES** | None (0 lines) |
| 5 | `research/phase11f/features.py` | 17,914 | 17,914 | `a3666b6c...` | `a3666b6c...` | `a3666b6c...` | **YES** | **YES** | None (0 lines) |
| 6 | `research/phase11f/fetch_universe.py` | 13,446 | 13,446 | `f9c15ff9...` | `f9c15ff9...` | `f9c15ff9...` | **YES** | **YES** | None (0 lines) |
| 7 | `research/phase11f/fibonacci.py` | 13,293 | 13,293 | `5f00e998...` | `5f00e998...` | `5f00e998...` | **YES** | **YES** | None (0 lines) |
| 8 | `research/phase11f/harness.py` | 18,228 | 18,228 | `9ee3d82a...` | `9ee3d82a...` | `9ee3d82a...` | **YES** | **YES** | None (0 lines) |
| 9 | `research/phase11f/hypotheses.json` | 14,295 | 14,295 | `348fcd32...` | `348fcd32...` | `348fcd32...` | **YES** | **YES** | None (0 lines) |
| 10 | `research/phase11f/metrics.py` | 13,103 | 13,103 | `031e428c...` | `031e428c...` | `031e428c...` | **YES** | **YES** | None (0 lines) |
| 11 | `research/phase11g_n/feasibility.json` | 4,217 | 4,028 | `ab944ff6...` | `98d63a34...` | `ab944ff6...` | NO | **YES** | `code_hash` only |
| 12 | `research/phase11g_o/feasibility_o.json` | 4,896 | 4,680 | `af944dcd...` | `5c928424...` | `af944dcd...` | NO | **YES** | `code_hash` only |
| 13 | `research/phase11g_p/readiness_p.json` | 4,597 | 4,396 | `cf4b69a9...` | `7fe5730e...` | `cf4b69a9...` | NO | **YES** | `code_hash` only |
| 14 | `research/phase11g_q/trigger_q.json` | 3,608 | 3,442 | `0448852c...` | `a76db519...` | `0448852c...` | NO | **YES** | `code_hash` only |
| 15 | `research/phase11g_r/readiness_r.json` | 3,690 | 3,521 | `addff247...` | `10f19f54...` | `addff247...` | NO | **YES** | `code_hash` only |
| 16 | `research/phase11g_s/readiness_s.json` | 3,703 | 3,533 | `a8c9d0d6...` | `98356522...` | `a8c9d0d6...` | NO | **YES** | `code_hash` only |
| 17 | `research/phase11g_t/readiness_t.json` | 2,628 | 2,522 | `29faecac...` | `27ed088a...` | `29faecac...` | NO | **YES** | `code_hash` only |
| 18 | `research/phase11g_u/readiness_u.json` | 2,782 | 2,669 | `519e7b2a...` | `935d9c05...` | `519e7b2a...` | NO | **YES** | `code_hash` only |
| 19 | `research/results/phase14_executable_edge_forensics.json` | 34,132 | 34,132 | `30f633fd...` | `30f633fd...` | `30f633fd...` | **YES** | **YES** | None (0 lines) |
| 20 | `research/results/phase15_evidence_readiness.json` | 28,372 | 28,372 | `044e9e2c...` | `044e9e2c...` | `044e9e2c...` | **YES** | **YES** | None (0 lines) |
| 21 | `research/results/phase17_oos_feasibility.json` | 8,013 | 8,013 | `2de23e5d...` | `2de23e5d...` | `2de23e5d...` | **YES** | **YES** | None (0 lines) |
| 22 | `research/results/phase18_oos_validation.json` | 20,252 | 20,252 | `95cef027...` | `95cef027...` | `95cef027...` | **YES** | **YES** | None (0 lines) |
| 23 | `research/results/phase19_oos_data_extension.json` | 9,875 | 9,875 | `95537d42...` | `95537d42...` | `95537d42...` | **YES** | **YES** | None (0 lines) |

---

## 3. Subsystem Breakdown and Detailed Analysis

### Group A: Phase 11F Exploration Tooling & Contracts (10 files)
- **Files:** `candidates.py`, `contracts.py`, `datasets.json`, `datasets.py`, `features.py`, `fetch_universe.py`, `fibonacci.py`, `harness.py`, `hypotheses.json`, `metrics.py`
- **Integrity Status:** **100% UNCHANGED**.
- **Evidence:** 
  - `git diff HEAD -- research/phase11f/` returns empty string.
  - Byte-by-byte comparison against `git show HEAD:research/phase11f/<file>` evaluates to `True` for every file.
  - Working tree SHA-256 matches both `HEAD` and `BUILD_MANIFEST.sha256`.
- **Why Git status flags them:** The operating system's filesystem timestamp or file stat metadata in `.git/index` is dirty. Git marks files as modified when stat info changes until re-indexed.

### Group B: Phase 11G Fresh Data Gate & Readiness Files (8 files)
- **Files:** `feasibility.json` (n), `feasibility_o.json` (o), `readiness_p.json` (p), `trigger_q.json` (q), `readiness_r.json` (r), `readiness_s.json` (s), `readiness_t.json` (t), `readiness_u.json` (u)
- **Integrity Status:** **DATA AND LOGIC UNCHANGED; CODE_HASH STRING REGENERATED ON WINDOWS**.
- **Evidence:**
  - The diff against HEAD in all 8 files consists solely of:
    ```diff
    - "code_hash": "<linux_lf_hash>",
    + "code_hash": "<windows_crlf_hash>",
    ```
  - Example (`research/phase11g_n/feasibility.json`):
    ```json
    - "code_hash": "97d8aaa6e1d47a56a2014dbe25e6d41d15548d75401729fe5838ac866e0a9dde",
    + "code_hash": "4f4ed985629e9747c16b34e01a0189ca08fb7bb3f7b0315f5c0f184c5e3e03f8",
    ```
  - Forensic reproduction:
    - `hashlib.sha256(open('research/phase11g_n/analyze.py', 'rb').read().replace(b'\r\n', b'\n')).hexdigest()` = `97d8aaa6...` (matches HEAD).
    - `hashlib.sha256(open('research/phase11g_n/analyze.py', 'rb').read()).hexdigest()` = `4f4ed985...` (matches Working Tree & Manifest).
  - All contiguity metrics (e.g. `2676`), symbol lists (`BTCUSDT`, `ETHUSDT`), timestamps (`1788912000`), and gate counters remain 100% identical.

### Group C: Phase 14-19 Forensic Results & Evidence (5 files)
- **Files:** `phase14_executable_edge_forensics.json`, `phase15_evidence_readiness.json`, `phase17_oos_feasibility.json`, `phase18_oos_validation.json`, `phase19_oos_data_extension.json`
- **Integrity Status:** **100% UNCHANGED**.
- **Evidence:**
  - `git diff HEAD -- research/results/` returns empty string.
  - Byte-by-byte comparison matches `HEAD` and `BUILD_MANIFEST.sha256` 100%.

---

## 4. Test Suite Impact Analysis

The presence of these files in `git status --porcelain` is the **sole reason for 18 test failures** across the test suite:

1. **`test_researcher_11g_{n..u}.py` (16 failures: 2 per file x 8 files)**:
   - `TestRepositoryHead::test_tree_clean_except_notes`:
     Fails at line: `if path.startswith("research/"): self.fail("frozen research modified: %s" % line)`
   - `TestProductionIsolation::test_no_production_paths`:
     Fails at line: `self.assertEqual(subprocess.run(["git", "status", "--porcelain", "--", "research/", "docs/audit/"]).stdout.strip(), "")`
2. **`test_researcher_15.py` (1 failure)**:
   - `TestMultipleTestingPreserved::test_no_new_hypothesis_family`:
     Fails at line: `self.assertEqual(subprocess.run(["git", "status", "--porcelain", "--", "research/"]).stdout.strip(), "")`
3. **`test_stage4_paper_certification.py` (1 failure)**:
   - `TestRepoIntegrity::test_research_byte_unchanged`:
     Fails at line: `self.assertEqual(git("status", "--short", "--", "research/").stdout.strip(), "")`

**Crucial Insight:** None of these 18 tests fail due to bad calculations, missing fixtures, logic bugs, or data corruption. They fail **exclusively because `git status` reports lines matching `research/`**.

---

## 5. Owner Decision & Action Options

| Option | Description | Action Required | Risk Assessment | Test Suite Outcome |
|---|---|---|---|---|
| **Option A (Preserve & Re-index)** | Keep current files exactly as-is. Run `git update-index --refresh` to clear false-positive stat dirty bits for 15 byte-identical files. Commit the Windows CRLF `code_hash` for the 8 `phase11g` files as the authoritative release state. | Owner approval required to commit `phase11g_{n..u}` `code_hash` updates. | **Minimal Risk**: No research data changes; preserves exact bytes matching `BUILD_MANIFEST.sha256`. | Resolves all 18 test failures. |
| **Option B (Restore LF Hash)** | Discard working tree changes in `phase11g_{n..u}` (`git checkout HEAD -- research/phase11g_*/`) to match HEAD's LF hashes. Regenerate `BUILD_MANIFEST.sha256`. | Discards Windows `code_hash` values in favor of LF values. | **Low Risk**: Reverts to original HEAD bytes, but tests running locally on Windows will regenerate CRLF hashes during test execution unless normalization is applied. | Resolves all 18 test failures until test builders run again. |
| **Option C (Leave Untouched / Strict Hold)** | Maintain current status without git commits or restores. Keep hold-out failure classification active in failure register. | No git mutation. | **Zero Risk of Unintended Mutation**, but 18 tests remain red due to strict `git status` assertions. | 18 tests remain on Hold. |

**Architect Recommendation:** Option A. All 23 files on disk already match `BUILD_MANIFEST.sha256`. Committing the refreshed `code_hash` strings formally documents the Windows platform baseline and restores clean green status across all 18 research-freeze test nodes.
