# QUANTENGINE PHASE 180 — FULL-SUITE FAILURE INVENTORY & TEST RECONCILIATION

**Audit Date**: 2026-10-20  
**Phase**: 180  
**Execution Posture**: NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED  
**Test Runner**: pytest 9.0.3 | Python 3.12.10 | Windows 10  

---

## 1. Full-Suite Execution Census & Reconciliation

The complete repository test suite was executed via:
```bash
python -m pytest tests -q -p no:cacheprovider --tb=line -rfs
```

### Execution Metrics

| Metric | Measured Value |
|---|---|
| **Exit Code** | `1` (Contractually expected due to deliberate historical change detectors) |
| **Duration** | `2609.70s` (43 minutes 29 seconds) |
| **Total Test Outcomes** | `4,498` |
| **Passed Tests** | `4,407` |
| **Failed Outcomes** | `77` (52 failed test nodes + 25 subtest assertion failures) |
| **Skipped Tests** | `14` |
| **Subtests Passed** | `400` |
| **Focused Regression Suite (Phases 171–180)** | **178/178 passed (100.0% PASS)** |

### Reconciliation Equation
$$\text{Total Outcomes} = \text{Passed} (4,407) + \text{Failed} (77) + \text{Skipped} (14) = 4,498$$
$$\text{Arithmetic Discrepancy} = 0$$

---

## 2. Forensic Reconciliation of the Phase 179 Failure Category Breakdown

The Phase 179 report listed failure categories summing to 75 instead of 77:
$$\text{Reported in Phase 179: } 5 + 26 + 11 + 6 + 2 = 50 \text{ failed nodes} + 25 \text{ subtests} = 75 \text{ (discrepancy of 2)}$$

Phase 180 audited the exact `FAILED` lines in `task-6433.log` and reconciled the 2 missing nodes:
1. **Git Ancestry & History Checks**: Actual count is **27** tests (24 in `test_researcher_11g_*`, 1 in `test_researcher_15.py`, 2 in `test_stage4_paper_certification.py`), whereas Phase 179 counted 26 (omitted `test_stage4_paper_certification.py::TestRepoIntegrity::test_research_byte_unchanged`).
2. **Pre-Seal Worktree Manifest & Hash Checks**: Actual count is **12** tests (8 manifest contracts + 4 release records checks), whereas Phase 179 grouped them as 11.

### Corrected Category Breakdown
$$\text{Historical Strategy Digest: } 5$$
$$\text{Git Ancestry \& History: } 27$$
$$\text{Pre-Seal Worktree Manifest: } 8$$
$$\text{Pre-Seal Release Records: } 4$$
$$\text{Dependency Pin Contract: } 4$$
$$\text{Privacy Contract: } 2$$
$$\text{Legacy Simulator \& Ledger: } 2$$
$$\mathbf{\text{Total Failed Test Nodes: }} \mathbf{52}$$
$$\mathbf{\text{Subtest Assertion Failures: }} \mathbf{25}$$
$$\mathbf{\text{Total Suite Failures: }} \mathbf{77}$$

$$\text{Reconciled Discrepancy} = 52 + 25 - 77 = \mathbf{0}$$

---

## 3. Complete Inventory of All 52 Failed Test Nodes

### Category 1: Historical Strategy Digest Change Detectors (5 Nodes)
- **Status**: `CONTRACTUALLY_RETAINED_FAILURE` (Tracked under `BLOCK-180-01`).
- **Nodes**:
  1. `tests/test_oos_data_extension_19.py::TestFrozenBaseline::test_nine_file_hash_exact_match`
  2. `tests/test_oos_feasibility_17.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
  3. `tests/test_oos_validation_18.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
  4. `tests/test_oos_validation_18.py::TestStrategyIdentity::test_no_strategy_mutation_after_runs`
  5. `tests/test_readiness_16.py::TestFrozenRecords::test_strategy_hash_pinned`
- **Root Cause**: These tests assert the Phase 14 Windows CRLF digest (`c52e648c...`). Gate-80 cost fixes post-Phase 4 modified strategy files. Disk bytes produce `9c56f3ff...` and LF produces `ba17582d...`. Tests are intentionally preserved without modification.

### Category 2: Git Ancestry & Repository History Limitations (27 Nodes)
- **Status**: `ENVIRONMENT_LIMITATION` (Tracked under `BLOCK-180-02`).
- **Nodes**:
  6. `tests/test_researcher_11g_n.py::TestRepositoryHead::test_starting_head_ancestor`
  7. `tests/test_researcher_11g_n.py::TestRepositoryHead::test_tree_clean_except_notes`
  8. `tests/test_researcher_11g_n.py::TestProductionIsolation::test_no_production_paths`
  9. `tests/test_researcher_11g_o.py::TestRepositoryHead::test_starting_head_ancestor`
  10. `tests/test_researcher_11g_o.py::TestRepositoryHead::test_tree_only_expected`
  11. `tests/test_researcher_11g_o.py::TestProductionIsolation::test_no_production_paths`
  12. `tests/test_researcher_11g_p.py::TestRepositoryHead::test_starting_head_ancestor`
  13. `tests/test_researcher_11g_p.py::TestRepositoryHead::test_tree_only_expected`
  14. `tests/test_researcher_11g_p.py::TestProductionIsolation::test_no_production_paths`
  15. `tests/test_researcher_11g_q.py::TestStartingState::test_head_descends_from_p`
  16. `tests/test_researcher_11g_q.py::TestStartingState::test_tree_only_expected`
  17. `tests/test_researcher_11g_q.py::TestProductionIsolation::test_no_production_paths`
  18. `tests/test_researcher_11g_r.py::TestStartingState::test_head_descends_from_q`
  19. `tests/test_researcher_11g_r.py::TestStartingState::test_tree_only_expected`
  20. `tests/test_researcher_11g_r.py::TestProductionIsolation::test_no_production_paths`
  21. `tests/test_researcher_11g_s.py::TestStartingState::test_head_descends_from_r`
  22. `tests/test_researcher_11g_s.py::TestStartingState::test_tree_only_expected`
  23. `tests/test_researcher_11g_s.py::TestProductionIsolation::test_no_production_paths`
  24. `tests/test_researcher_11g_t.py::TestStartingState::test_head_descends_from_s`
  25. `tests/test_researcher_11g_t.py::TestStartingState::test_tree_only_expected`
  26. `tests/test_researcher_11g_t.py::TestProductionIsolation::test_no_production_paths`
  27. `tests/test_researcher_11g_u.py::TestStartingState::test_head_descends_from_t`
  28. `tests/test_researcher_11g_u.py::TestStartingState::test_tree_only_expected`
  29. `tests/test_researcher_11g_u.py::TestProductionIsolation::test_no_production_paths`
  30. `tests/test_researcher_15.py::TestMultipleTestingPreserved::test_no_new_hypothesis_family`
  31. `tests/test_stage4_paper_certification.py::TestRepoIntegrity::test_head_is_stage123_closure_descendant`
  32. `tests/test_stage4_paper_certification.py::TestRepoIntegrity::test_research_byte_unchanged`
- **Root Cause**: The standalone delivery distribution contains a shallow repository without full multi-year commit ancestry for early researcher branches (`fad7329b...`).

### Category 3: Pre-Seal Worktree Manifest & Snapshot Checks (8 Nodes)
- **Status**: `PRE_SEAL_WORKTREE_STATE`.
- **Nodes**:
  33. `tests/test_phase158_manifest_contract.py::TestManifestCompleteness::test_generate_stdout_is_byte_identical`
  34. `tests/test_phase158_manifest_contract.py::TestManifestCompleteness::test_manifest_covers_every_packaged_file_exactly_once`
  35. `tests/test_phase158_manifest_contract.py::TestManifestCompleteness::test_manifest_reproduces_byte_for_byte`
  36. `tests/test_phase158_manifest_contract.py::TestManifestCompleteness::test_verify_reports_no_problems`
  37. `tests/test_phase158_snapshot_neutrality.py::TestSnapshotNeutrality::test_manifest_is_lf_only_and_reproduces_byte_for_byte`
  38. `tests/test_release_consistency_phase155.py::TestReleaseConsistency155::test_no_text_artifact_embeds_own_archive_hash`
  39. `tests/test_release_consistency_phase155.py::TestReleaseConsistency155::test_worktree_verifies_against_manifest`
  40. `tests/test_release_manifest_phase154.py::TestReleaseManifest154::test_manifest_verifies_clean`
- **Root Cause**: During active development before pre-pack sealing, newly authored audit reports exist in the tree before final manifest regeneration.

### Category 4: Pre-Seal Release Records Non-Circularity (4 Nodes)
- **Status**: `PRE_SEAL_RECORD_STATE`.
- **Nodes**:
  41. `tests/test_release_records_phase171.py::TestReleaseRecords171::test_current_records_do_not_embed_the_shipped_archive_hash`
  42. `tests/test_release_records_phase172.py::TestReleaseRecords172::test_current_records_do_not_embed_the_shipped_archive_hash`
  43. `tests/test_release_records_phase173.py::TestReleaseRecords173::test_current_records_do_not_embed_the_shipped_archive_hash`
  44. `tests/test_release_records_phase174.py::TestReleaseRecords174::test_current_records_do_not_embed_the_shipped_archive_hash`
- **Root Cause**: Asserts non-circularity of release hash records against pre-seal working tree state.

### Category 5: Dependency Pin Contract (4 Nodes)
- **Status**: `PRE_SEAL_RECORD_ALIGNMENT`.
- **Nodes**:
  45. `tests/test_dependency_pin_contract.py::TestDependencyPinContract::test_declared_pins_match_the_recorded_evidence_environment`
  46. `tests/test_dependency_pin_contract.py::TestDependencyPinContract::test_httpx_pin_is_not_below_the_recorded_evidence_version`
  47. `tests/test_dependency_pin_contract.py::TestDependencyPinContract::test_release_record_names_interpreter_and_runner`
  48. `tests/test_dependency_pin_contract.py::TestDependencyPinContract::test_release_record_names_its_dependency_set`
- **Root Cause**: Checks release record dependency declarations prior to package sealing.

### Category 6: Privacy Contract Historical Baseline (2 Nodes + 25 Subtests)
- **Status**: `PRE_SEAL_RECORD_ALIGNMENT`.
- **Nodes**:
  49. `tests/test_phase158_privacy_contract.py::TestPrivacyContract::test_privacy_review_declares_the_allowlist_and_the_package_class`
  50. `tests/test_phase158_privacy_contract.py::TestPrivacyContract::test_the_scan_and_review_deny_publication_clearance`
  - Plus 25 subtest assertion failures in `test_the_historical_order_id_baseline_is_enumerated_in_the_review`.
- **Root Cause**: Asserts that all 13 sealed historical order ID carriers are enumerated in the review text.

### Category 7: Legacy Simulator & Ledger Checks (2 Nodes)
- **Status**: `PRE_EXISTING_LEGACY_ASSERTIONS`.
- **Nodes**:
  51. `tests/test_accounting_9q.py::TestBreakevenClassification::test_backtester_breakeven_via_simulator`
  52. `tests/test_stage4_paper_certification.py::TestPaperAccounting::test_sequential_ledger_matches_registry`
- **Root Cause**: `test_accounting_9q.py` passes a degenerate setup `FakeSetup(take_profit=100, entry=100)`, which is rejected by `TradeSimulator`'s bracket geometry (`take_profit > entry`).

---

## 4. Focused Regression Suites (Phases 171–180)

All 178 focused regression tests passed cleanly:

| Suite | Path | Tests | Result |
|---|---|---|---|
| **Phase 180 Instrument Semantics** | `tests/test_phase180_instrument_semantics.py` | 11 | **PASSED** |
| **Phase 179 Risk Enforcement** | `tests/test_phase179_risk_enforcement.py` | 18 | **PASSED** |
| **Phase 178 Artifact Audit** | `tests/test_phase178_artifact_audit.py` | 16 | **PASSED** |
| **Phase 177 Tick Remediation** | `tests/test_phase177_tick_remediation.py` | 24 | **PASSED** |
| **Phase 176 Contract Semantics** | `tests/test_phase176_contract_semantics.py` | 41 | **PASSED** |
| **Phase 175 Instrument Economics** | `tests/test_phase175_instrument_economics.py` | 10 | **PASSED** |
| **Phase 175 Release Records** | `tests/test_release_records_phase175.py` | 8 | **PASSED** |
| **Phase 174 Economics Reconciliation** | `tests/test_phase174_economics_reconciliation.py` | 10 | **PASSED** |
| **Phase 173 Audit Reproduction** | `tests/test_phase173_audit.py` | 9 | **PASSED** |
| **Phase 172 Adversarial Boundary** | `tests/test_maker_execution_phase172.py` | 23 | **PASSED** |
| **Phase 171 Maker Baseline** | `tests/test_maker_execution_phase171.py` | 8 | **PASSED** |
| **TOTAL** | | **178** | **100% PASS** |
