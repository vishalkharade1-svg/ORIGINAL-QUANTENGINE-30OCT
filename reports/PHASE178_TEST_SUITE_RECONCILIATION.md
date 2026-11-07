# QuantEngine Phase 178 — Test Suite Reconciliation Report

## Executive Summary

This report reconciles the full test collection across unit tests, focused regression suites, and contractually preserved historical change-detectors.

---

## 1. Test Suite Accounting Summary

| Suite Category | Tests Collected | Passed | Failed | Skipped | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Phase 178 Artifact & Stop-Rounding** | 16 | 16 | 0 | 0 | `PASSED` |
| **Phase 177 Tick Remediation** | 24 | 24 | 0 | 0 | `PASSED` |
| **Phase 176 Contract Semantics** | 41 | 41 | 0 | 0 | `PASSED` |
| **Phase 175 Instrument Economics** | 10 | 10 | 0 | 0 | `PASSED` |
| **Phase 175 Release Records** | 8 | 8 | 0 | 0 | `PASSED` |
| **Phase 174 Economics Reconciliation** | 10 | 10 | 0 | 0 | `PASSED` |
| **Phase 173 Audit Reproduction** | 9 | 9 | 0 | 0 | `PASSED` |
| **Phase 172 Adversarial Maker** | 23 | 23 | 0 | 0 | `PASSED` |
| **Phase 171 Maker Baseline** | 8 | 8 | 0 | 0 | `PASSED` |
| **Total Focused Regression Batch** | **149** | **149** | **0** | **0** | `PASSED` |
| **Historical Change-Detectors** | 118 | 113 | 5 | 0 | `CONTRACTUALLY_RETAINED` |
| **Full Workspace Test Collection** | **4,439** | — | — | — | `COLLECTED` |

---

## 2. Reconciliation of the 5 Historical Failures

The 5 historical change-detector failures are:
1. `tests.test_oos_feasibility_17.TestStrategyIdentity.test_nine_file_hash_exact_match`
2. `tests.test_oos_validation_18.TestStrategyIdentity.test_nine_file_hash_exact_match`
3. `tests.test_oos_validation_18.TestStrategyIdentity.test_no_strategy_mutation_after_runs`
4. `tests.test_oos_data_extension_19.TestFrozenBaseline.test_nine_file_hash_exact_match`
5. `tests.test_readiness_16.TestFrozenRecords.test_strategy_hash_pinned`

### Root Cause & Justification:
- These tests assert an uncommitted pre-Phase-4 Windows CRLF digest (`c52e648c...`) over 9 strategy files.
- Under Unix LF conventions, the digest is `9c56f3ff...`.
- In accordance with Safety Rule #7, historical strategy pins and digests are preserved without modification. They are contractually tracked under `BLOCK-178-01`.
