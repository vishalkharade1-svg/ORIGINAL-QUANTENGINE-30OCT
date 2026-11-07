# Phase 165 Test Reconciliation Report

**Date**: 2026-10-19  
**Phase**: 165  
**Subject**: Reconciliation of Total Test Census, Pass/Skip Discrepancies, and Failure Multisets  

---

## 1. Reconciliation of Census Discrepancy

During the Phase 164 review, a numerical question was raised regarding:
* Reported collection count: `4,188`
* Reported full suite outcome: `4,126 passed, 56 skipped, 5 failed` (sum = `4,187`)
* Alternating mention of `4,127 passed` vs `4,126 passed`

### 1.1 Root Cause of the 1-Test Difference
The 1-test delta traces to `tests/test_release_records_phase161.py:144`:
```python
def test_detached_record_is_outside_the_package_and_agrees_with_the_archive(self):
    ...
    if not (archive.exists() and record.exists()):
        self.skipTest("no archive/detached record beside this tree ...")
```
* **State A (Sibling Phase 161 Deliverable Absent from `..`)**:
  * This test executes `skipTest()`.
  * Outcomes: **4,126 passed, 57 skipped, 5 failed** (Total = `4,188`).
* **State B (Sibling Phase 161 Deliverable Present in `..`)**:
  * `QuantEngine_PHASE161_RELEASE_CANDIDATE.zip` and `RELEASE_HASH_PHASE161.txt` exist in the delivery parent directory.
  * The test runs and evaluates the archive hash $\rightarrow$ **PASSED**.
  * Outcomes: **4,127 passed, 56 skipped, 5 failed** (Total = `4,188`).

The earlier phrasing `4,126 passed, 56 skipped, 5 failed` paired the pass count from State A (4,126) with the skip count from State B (56). In both states, the true collection count is strictly **4,188** tests.

---

## 2. Census Table for Phase 165

With the addition of `tests/test_strategy_identity_separation_phase165.py` (+4 tests), the new test collection count is **4,192**:

| Category | Count | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Passed Tests** | 4,131 | PASS | 4,127 prior passes + 4 new Phase 165 identity tests |
| **Skipped Tests** | 56 | SKIPPED | 40 gated Git facts (in archive mode), 6 product cache, 1 live net, 7 pre-pack siblings, 2 git-check |
| **Failed Tests** | 5 | FAIL (Expected) | The 5 frozen strategy-digest change detectors (`BLOCK-163-01`) |
| **Total Collected** | **4,192** | — | Strict sum: 4,131 + 56 + 5 = 4,192 |
