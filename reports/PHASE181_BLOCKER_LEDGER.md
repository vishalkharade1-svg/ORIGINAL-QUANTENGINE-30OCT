# QUANTENGINE PHASE 181 — BLOCKER LEDGER

**Phase**: 181  
**Status**: NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED  
**Date**: 2026-10-20  

---

## Active Release Blockers

### `BLOCK-181-01`: Historical Strategy Digest Discrepancy
- **Classification**: `CONTRACTUALLY_RETAINED_FAILURE`
- **Severity**: BLOCKER (Prevents Gate-80 Production Sign-Off)
- **Status**: `UNRESOLVED` (Intentional Change Detector)
- **Impacted Tests (5)**:
  - `tests/test_oos_data_extension_19.py::TestFrozenBaseline::test_nine_file_hash_exact_match`
  - `tests/test_oos_feasibility_17.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
  - `tests/test_oos_validation_18.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
  - `tests/test_oos_validation_18.py::TestStrategyIdentity::test_no_strategy_mutation_after_runs`
  - `tests/test_readiness_16.py::TestFrozenRecords::test_strategy_hash_pinned`
- **Description**: Historical tests enforce Phase 14 Windows CRLF digest pins (`c52e648c...`). Gate-80 cost fixes post-Phase 4 modified strategy source files. The current disk digest is `9c56f3ff...` (and LF normalized `ba17582d...`).
- **Remediation Requirement**: Operator baseline update authorization or historical digest dual-attestation. Cannot be modified unilaterally by an auditor.

---

### `BLOCK-181-02`: Shallow Git Tree and Ancestry Limitations
- **Classification**: `ENVIRONMENT_LIMITATION`
- **Severity**: MEDIUM
- **Status**: `UNRESOLVED`
- **Impacted Tests (27)**:
  - 24 tests across `test_researcher_11g_n.py` through `test_researcher_11g_u.py`
  - 1 test in `test_researcher_15.py`
  - 2 tests in `test_stage4_paper_certification.py`
- **Description**: The handover package contains a shallow git clone without full commit graph ancestry back to initial researcher branches (`fad7329b...`).
- **Remediation Requirement**: Access to full upstream repository git history or packaging of full historical packfiles.

---

### `BLOCK-181-03`: Delta Exchange India Product ID 84 Multiplier Authority
- **Classification**: `PROVISIONAL_EVIDENCE`
- **Severity**: HIGH (Risk & Position Sizing Clearance)
- **Status**: `PROVISIONAL`
- **Description**: Delta Exchange India BTCUSD Product ID 84 uses contract multiplier `0.001` in calculation logic, which is mathematically verified in internal formulas. However, official exchange API specifications or authenticated symbol definition responses from Delta Exchange India must be archived to elevate from provisional to certified production evidence.
- **Remediation Requirement**: Authorized operator capture of live or authenticated API product catalog for Product ID 84.
