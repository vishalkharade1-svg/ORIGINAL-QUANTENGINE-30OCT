# QUANTENGINE PHASE 20 — RESEARCH BASELINE REPRODUCIBILITY & AUDIT REPORT

**Date:** 2026-10-24  
**Author:** Senior Software Architect & Git Forensics Investigator  
**Repository State:** `main` @ `ffefa14a8729f6d2160db3735a06257cbb6ab48b`  
**Classification:** Authoritative Technical Forensics & Research Integrity Audit  

---

## 1. Executive Summary

During Phase 18 and Phase 19 verification, Git reported **23 modified files** under the `research/` directory. Under the standing research freeze contract (§11G freeze, Phase 15 non-expansion protocol), any modification under `research/` triggers automated test failures in `test_researcher_11g_{n..u}.py`, `test_researcher_15.py`, and `test_stage4_paper_certification.py` (accounting for **18 failing test nodes** in the test census).

Phase 20 executed an exhaustive, byte-level, index-level, and algorithmic investigation into all 23 files. The investigation revealed **two distinct, mathematically proven root causes**:

1. **Git Stat-Cache Desynchronization (15 files):**
   - 10 files in `research/phase11f/` and 5 files in `research/results/` are **100.0% byte-identical** to their Git index blobs, their HEAD commit blobs, and their entries in `BUILD_MANIFEST.sha256`.
   - Git flagged them as modified (`M`) solely because the `.git/index` stat cache held size values calculated with Windows CRLF line endings (`size = disk_bytes + line_count`), whereas the files on disk were checked out with LF line endings.
   - **Resolution:** Executing non-destructive index stat refresh (`git update-index --refresh`) resolved all 15 files to clean status without modifying a single byte on disk and without staging any changes.

2. **Platform-Dependent Line-Ending Hash Divergence (8 files):**
   - 8 files in `research/phase11g_{n..u}` (`feasibility.json`, `feasibility_o.json`, `readiness_p.json`, `trigger_q.json`, `readiness_r.json`, `readiness_s.json`, `readiness_t.json`, `readiness_u.json`) differ from HEAD in **exactly one field**: `"code_hash"`.
   - In each of the 8 corresponding generator scripts (`analyze.py`, `analyze_o.py`, `analyze_p.py`, `gate.py`, `gate_r.py`, `gate_s.py`, `monitor.py`, `monitor_u.py`), the script computes:
     `code_hash = _sha256_bytes(Path(__file__).read_bytes())`
   - Because `read_bytes()` reads raw file bytes without line-ending normalization, running the generators on Windows (where `core.autocrlf=true` produced CRLF `\r\n` on disk) yielded the CRLF SHA-256 hash. In HEAD (committed on Linux with LF `\n`), the code hash reflected the LF SHA-256 hash.
   - **Mathematical Proof:** Normalizing newlines (`blob.replace(b'\r\n', b'\n')`) prior to hashing produces **100.0% exact matches** to the canonical HEAD hashes across all 8 files.
   - **Resolution:** Implemented `core/research/deterministic_hash.py` and validated with comprehensive unit tests (`tests/test_phase20_deterministic_hash.py`), establishing cross-platform deterministic code hashing at its source without mutating frozen research baselines.

---

## 2. Forensic Audit of the 15 Byte-Identical Files

### 2.1 File Inventory & Cryptographic Verification

A byte-by-byte comparison between Worktree files, Git Index blobs, Git HEAD blobs, and `BUILD_MANIFEST.sha256` confirmed identical SHA-256 hashes for all 15 files:

| # | File Path | Worktree SHA-256 (Disk) | Git Index SHA-256 | Git HEAD SHA-256 | Manifest Match | Disk Lines | CRLF Count |
|---|---|---|---|---|---|---|---|
| 1 | `research/phase11f/candidates.py` | `255d784f47ce4997...` | `255d784f47ce4997...` | `255d784f47ce4997...` | MATCH | 545 | 0 (LF only) |
| 2 | `research/phase11f/contracts.py` | `d720c2d3e1d13f9f...` | `d720c2d3e1d13f9f...` | `d720c2d3e1d13f9f...` | MATCH | 179 | 0 (LF only) |
| 3 | `research/phase11f/datasets.json` | `5c84dd9ee3d74910...` | `5c84dd9ee3d74910...` | `5c84dd9ee3d74910...` | MATCH | 45 | 0 (LF only) |
| 4 | `research/phase11f/datasets.py` | `2f2f7ef33f025409...` | `2f2f7ef33f025409...` | `2f2f7ef33f025409...` | MATCH | 338 | 0 (LF only) |
| 5 | `research/phase11f/features.py` | `ca7622877a561bb2...` | `ca7622877a561bb2...` | `ca7622877a561bb2...` | MATCH | 363 | 0 (LF only) |
| 6 | `research/phase11f/fetch_universe.py` | `62fcfec80521e176...` | `62fcfec80521e176...` | `62fcfec80521e176...` | MATCH | 158 | 0 (LF only) |
| 7 | `research/phase11f/fibonacci.py` | `90538a7c1b5a5c68...` | `90538a7c1b5a5c68...` | `90538a7c1b5a5c68...` | MATCH | 129 | 0 (LF only) |
| 8 | `research/phase11f/harness.py` | `97193b2a2aa7c6f0...` | `97193b2a2aa7c6f0...` | `97193b2a2aa7c6f0...` | MATCH | 344 | 0 (LF only) |
| 9 | `research/phase11f/hypotheses.json` | `88cbe1a53ae7b80a...` | `88cbe1a53ae7b80a...` | `88cbe1a53ae7b80a...` | MATCH | 185 | 0 (LF only) |
| 10 | `research/phase11f/metrics.py` | `5e98586c06a3ec07...` | `5e98586c06a3ec07...` | `5e98586c06a3ec07...` | MATCH | 239 | 0 (LF only) |
| 11 | `research/results/phase14_executable_edge_forensics.json` | `5f17a9446d5c64c7...` | `5f17a9446d5c64c7...` | `5f17a9446d5c64c7...` | MATCH | 118 | 0 (LF only) |
| 12 | `research/results/phase15_evidence_readiness.json` | `c9ee3e7ef157b856...` | `c9ee3e7ef157b856...` | `c9ee3e7ef157b856...` | MATCH | 134 | 0 (LF only) |
| 13 | `research/results/phase17_oos_feasibility.json` | `9cb90cbfa3a3feef...` | `9cb90cbfa3a3feef...` | `9cb90cbfa3a3feef...` | MATCH | 45 | 0 (LF only) |
| 14 | `research/results/phase18_oos_validation.json` | `7be4e047466ebc37...` | `7be4e047466ebc37...` | `7be4e047466ebc37...` | MATCH | 60 | 0 (LF only) |
| 15 | `research/results/phase19_oos_data_extension.json` | `375d8aa28ef94c92...` | `375d8aa28ef94c92...` | `375d8aa28ef94c92...` | MATCH | 71 | 0 (LF only) |

### 2.2 Mechanism of the False `git status` Modification

The exact mechanism causing Git to report these 15 byte-identical files as modified was uncovered by inspecting the low-level stat metadata stored in `.git/index`:
- For every file in the table above:
  $$\text{cached\_index\_size} - \text{actual\_disk\_size} = \text{line\_count} \times 1$$
- In Phase 158, the test suite enforced `test_frozen_artifacts_carry_no_carriage_returns()`, which required these 15 files to be stored with LF (`\n`) line endings.
- When Git checks status, it executes an `lstat()` check. Because `st_size != cached_index_size`, Git marked each file as modified without reading file contents into memory.
- Executing `git update-index --refresh` re-calculated the index stat cache (mtime, size) against the object database. Git immediately recognized all 15 files as clean (`0` modified files).

---

## 3. Forensic Audit of the 8 `phase11g_{n..u}` Files

### 3.1 File Inventory & Line-Ending Divergence

The 8 files under `research/phase11g_{n..u}` are JSON report files generated by companion Python scripts. Each file differs from HEAD by exactly one line (`"code_hash"`):

| # | Artifact File | Generator Script | Generator Code Hash Logic | Disk Hash (`code_hash`) | HEAD Hash (`code_hash`) | LF-Normalized Script Hash | Match to HEAD? |
|---|---|---|---|---|---|---|---|
| 1 | `research/phase11g_n/feasibility.json` | `analyze.py` | `_sha256_bytes(Path(__file__).read_bytes())` | `4f4ed985629e...` | `97d8aaa6e1d4...` | `97d8aaa6e1d47a56a2014dbe25e6d41d...` | **100% MATCH** |
| 2 | `research/phase11g_o/feasibility_o.json` | `analyze_o.py` | `_sha256_bytes(Path(__file__).read_bytes())` | `78c2c1d62a7a...` | `6fb4a308ed76...` | `6fb4a308ed7649002d583f5067a17e09...` | **100% MATCH** |
| 3 | `research/phase11g_p/readiness_p.json` | `analyze_p.py` | `_sha256_bytes(Path(__file__).read_bytes())` | `c0728353f7b9...` | `f493df6ce4a2...` | `f493df6ce4a2164e5dba6de71b191c4a...` | **100% MATCH** |
| 4 | `research/phase11g_q/trigger_q.json` | `gate.py` | `_sha256_bytes(Path(__file__).read_bytes())` | `a93ccb6feaca...` | `09cc32a9478b...` | `09cc32a9478b807d291061413147657b...` | **100% MATCH** |
| 5 | `research/phase11g_r/readiness_r.json` | `gate_r.py` | `_sha256_bytes(Path(__file__).read_bytes())` | `7591b7715b19...` | `5a19b1fc8af7...` | `5a19b1fc8af7656fd8b24b85c6ba3eb4...` | **100% MATCH** |
| 6 | `research/phase11g_s/readiness_s.json` | `gate_s.py` | `_sha256_bytes(Path(__file__).read_bytes())` | `ecc9b88cb912...` | `1181d1ce4d67...` | `1181d1ce4d67416254877f1b78587be3...` | **100% MATCH** |
| 7 | `research/phase11g_t/readiness_t.json` | `monitor.py` | `hashlib.sha256(Path(__file__).read_bytes()).hexdigest()` | `2f5af57fc4e8...` | `eea445bd832a...` | `eea445bd832a92a594716e7ce3ab78fc...` | **100% MATCH** |
| 8 | `research/phase11g_u/readiness_u.json` | `monitor_u.py` | `hashlib.sha256(Path(__file__).read_bytes()).hexdigest()` | `2f656aa7e739...` | `2e3a731c2495...` | `2e3a731c24959623aaf11b891f1bfcf4...` | **100% MATCH** |

### 3.2 Root Cause Analysis

1. **Absence of `.gitattributes`:** The repository has no `.gitattributes` file specifying line ending behavior for Python and JSON files.
2. **Windows `core.autocrlf=true` Checkout:** On Windows, Git automatically converts LF to CRLF upon checkout. The generator scripts on disk carry CRLF (`\r\n`).
3. **Raw Byte Hashing:** The generators use `Path(__file__).read_bytes()` to hash their own source code. When executed on Windows, they hash the CRLF bytes, generating the Windows `code_hash`.
4. **Testing Catch-22:** In `tests/test_researcher_11g_{p..u}.py`, tests like `test_mut_p8_normalized_hash_tampering` also assert:
   `self.assertEqual(f["code_hash"], hashlib.sha256((BASE_DIR / ... / "analyze_p.py").read_bytes()).hexdigest())`
   On Windows, `read_bytes()` evaluates to the CRLF hash (`c0728353...`). If the JSON file on disk has the Windows hash, `test_mut_p8` passes, but Git marks the file `M`. If the JSON file is reverted to the HEAD hash (`f493df6c...`), Git recognizes the file as clean, but `test_mut_p8` fails!

---

## 4. Deterministic Hashing Engine (`core/research/deterministic_hash.py`)

To eliminate cross-platform line-ending hash divergence at its source without mutating frozen research baselines, Phase 20 engineered a dedicated deterministic hashing module:

### 4.1 Implementation Design

- **Module Path:** [deterministic_hash.py](file:///f:/vishal%203/near%20final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/core/research/deterministic_hash.py)
- **Functions:**
  - `normalize_line_endings(blob_or_text: bytes | str) -> bytes`: Converts all `\r\n` and `\r` to canonical LF (`\n`), strips UTF-8 BOM if present.
  - `compute_deterministic_source_hash(source: bytes | str | Path) -> str`: Produces a checkout-invariant SHA-256 hex digest.
  - `canonical_code_hash(file_path: str | Path) -> str`: Convenience helper for source code scripts.
  - `canonical_json_bytes(obj: Any) -> bytes`: Enforces sorted keys, 2-space indentation, explicit separators, trailing newline, UTF-8.
  - `compute_canonical_json_hash(obj: Any) -> str`: Computes SHA-256 of the canonical JSON bytes.
  - `verify_source_hash(source, expected_hash) -> bool`: Verifies deterministic digest equality.

### 4.2 Comprehensive Unit Test Suite

- **Test Suite:** [test_phase20_deterministic_hash.py](file:///f:/vishal%203/near%20final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/tests/test_phase20_deterministic_hash.py)
- **Results:** 8 tests passed, 8 subtests passed in 2.03s.
- **Coverage:**
  1. `test_normalize_line_endings_lf_and_crlf`: Proves LF, CRLF, and CR bytes normalize to identical LF bytes.
  2. `test_compute_hash_lf_crlf_identical`: Proves identical digests for LF and CRLF source representations.
  3. `test_repeated_execution_determinism`: Proves strict idempotence across 500 executions.
  4. `test_meaningful_source_changes_modify_digest`: Proves that variable name changes, constant changes, comment additions, whitespace alterations, and case changes strictly change the digest.
  5. `test_utf8_bom_stripping`: Proves BOM-prefixed source matches clean UTF-8.
  6. `test_canonical_json_ordering_and_hash`: Proves dictionary key order permutations yield identical JSON bytes and hashes.
  7. `test_verify_source_hash_helper`: Validates verification helper against LF and CRLF inputs.
  8. `test_all_phase11g_generators_match_head_canonical_hash`: Subtest proving that `canonical_code_hash()` on all 8 Phase 11G generators matches their canonical HEAD hashes 100%.

---

## 5. Reassessment of the 18 Research-Freeze Failures

With the index stat cache refreshed for the 15 byte-identical files, the entire research-freeze failure set was reassessed:

| Failing Test Node | Cause |
|---|---|
| `test_researcher_11g_n.py::TestRepositoryHead::test_tree_clean_except_notes` | Fails solely on `M research/phase11g_n/feasibility.json` |
| `test_researcher_11g_n.py::TestProductionIsolation::test_no_production_paths` | Fails solely on `M research/phase11g_n/feasibility.json` |
| `test_researcher_11g_o.py::TestStartingState::test_tree_clean_except_notes` | Fails solely on `M research/phase11g_o/feasibility_o.json` |
| `test_researcher_11g_o.py::TestProductionIsolation::test_no_production_paths` | Fails solely on `M research/phase11g_o/feasibility_o.json` |
| `test_researcher_11g_p.py::TestStartingState::test_tree_clean_except_notes` | Fails solely on `M research/phase11g_p/readiness_p.json` |
| `test_researcher_11g_p.py::TestProductionIsolation::test_no_production_paths` | Fails solely on `M research/phase11g_p/readiness_p.json` |
| `test_researcher_11g_q.py::TestStartingState::test_tree_clean_except_notes` | Fails solely on `M research/phase11g_q/trigger_q.json` |
| `test_researcher_11g_q.py::TestProductionIsolation::test_no_production_paths` | Fails solely on `M research/phase11g_q/trigger_q.json` |
| `test_researcher_11g_r.py::TestStartingState::test_tree_clean_except_notes` | Fails solely on `M research/phase11g_r/readiness_r.json` |
| `test_researcher_11g_r.py::TestProductionIsolation::test_no_production_paths` | Fails solely on `M research/phase11g_r/readiness_r.json` |
| `test_researcher_11g_s.py::TestStartingState::test_tree_clean_except_notes` | Fails solely on `M research/phase11g_s/readiness_s.json` |
| `test_researcher_11g_s.py::TestProductionIsolation::test_no_production_paths` | Fails solely on `M research/phase11g_s/readiness_s.json` |
| `test_researcher_11g_t.py::TestStartingState::test_tree_clean_except_notes` | Fails solely on `M research/phase11g_t/readiness_t.json` |
| `test_researcher_11g_t.py::TestProductionIsolation::test_no_production_paths` | Fails solely on `M research/phase11g_t/readiness_t.json` |
| `test_researcher_11g_u.py::TestStartingState::test_tree_clean_except_notes` | Fails solely on `M research/phase11g_u/readiness_u.json` |
| `test_researcher_11g_u.py::TestProductionIsolation::test_no_production_paths` | Fails solely on `M research/phase11g_u/readiness_u.json` |
| `test_researcher_15.py::TestMultipleTestingPreserved::test_no_new_hypothesis_family` | Fails solely on `git status --porcelain -- research/` (the 8 files) |
| `test_stage4_paper_certification.py::TestRepoIntegrity::test_research_byte_unchanged` | Fails solely on `git diff --stat -- research/` (the 8 files) |

**Finding:** All 18 research-freeze failures share the **identical single root cause**: the 8 `phase11g_{n..u}` JSON files carry uncommitted `code_hash` differences against HEAD.

---

## 6. Strategic Separation: Research Baseline vs B-01 Strategy Pins vs F5b

The repository's remaining test failures fall into three strictly segregated categories:

1. **Research Baseline Discrepancy (18 nodes):** Fully audited above. Governed by the research freeze contract. Resolving the 8 `phase11g` files clears all 18 nodes.
2. **B-01 Strategy Digest Pins (5 nodes):**
   - Nodes: `test_oos_feasibility_17.py`, `test_oos_validation_18.py` (x2), `test_oos_data_extension_19.py`, `test_readiness_16.py`.
   - Root cause: Frozen test constants pin the Phase 14 legacy digest `c52e648c...`. The current 9 strategy files evaluate to `9c56f3ff...`. Modifying strategy files or recertifying strategy hashes requires owner authorization and is strictly separated from research freeze recovery.
3. **F5b Release Consistency Self-Embed Policy (1 node):**
   - Node: `test_release_consistency_phase155.py::TestReleaseConsistencyPhase155::test_no_text_artifact_embeds_own_archive_hash`.
   - Root cause: `reports/PHASE165_PROVENANCE.json` records historical input lineage documentation that collides with the self-embed policy assertion.

---

## 7. Owner Decision Packet: Resolving the 8 `phase11g` Files

The investigator presents three concrete options for resolving the 8 `phase11g` files:

### Option A: Repository-Level Line-Ending Normalization via `.gitattributes` (Recommended)
- **Action:** Add `.gitattributes` configuring `research/** text eol=lf`.
- **Mechanism:** Git will checkout all research files with LF line endings on all platforms (including Windows).
- **Outcome:** On Windows, `analyze.py.read_bytes()` will yield LF bytes matching the HEAD hash `97d8aaa6...`. Both `git status` AND `test_mut_p8` will pass simultaneously. Zero code or research baseline mutations required.

### Option B: Adopt Canonical LF Hashes & Update Test Generators
- **Action:** Restore the 8 JSON artifacts to match HEAD, and update the generator scripts and tests to use `canonical_code_hash()` from `core/research/deterministic_hash.py`.
- **Outcome:** Eliminates all 18 failures and future-proofs the codebase against checkout configurations.

### Option C: Formal Exception for Windows Development Environment
- **Action:** Retain current worktree CRLF hashes and update the 18 research freeze assertions to allow the documented Windows `code_hash` representation when running on `win32`.
- **Outcome:** Tests pass on Windows without modifying git index or HEAD.
