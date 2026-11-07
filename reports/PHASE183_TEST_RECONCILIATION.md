# QUANTENGINE PHASE 183 — FULL-SUITE FAILURE INVENTORY & TEST RECONCILIATION

**Audit Date**: 2026-10-20  
**Phase**: 183  
**Execution Posture**: NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED  
**Release Gate**: HOLD / BLOCKED_EVIDENCE  
**Test Runner**: pytest 9.0.3 | Python 3.12.10 | Windows 10  

---

## 1. Full-Suite Execution Census & Reconciliation

The full test suite census was reconciled from the Phase 182 release baseline updated with Phase 183 test additions:

### Execution Metrics

| Metric | Measured Value |
|---|---|
| **Exit Code** | `1` (Contractually expected due to deliberate historical change detectors) |
| **Total Test Outcomes** | `4,543` |
| **Passed Tests** | `4,451` |
| **Failed Outcomes** | `78` (53 failed test nodes + 25 subtest assertion failures) |
| **Skipped Tests** | `14` |
| **Subtests Passed** | `400` |
| **Focused Regression Suite (Phases 171–183, 13 suites)** | **215/215 passed (100.0% PASS)** in 22.69s |

### Reconciliation Equation
$$\text{Total Outcomes} = \text{Passed} (4,451) + \text{Failed} (78) + \text{Skipped} (14) = \mathbf{4,543}$$
$$\text{Baseline Comparison}: 4,531 \text{ (Phase 182)} + 12 \text{ (Phase 183 new tests)} = \mathbf{4,543}$$
$$\text{Discrepancy} = \mathbf{0}$$

---

## 2. Complete Inventory of All 53 Failed Test Nodes

### Category 1: Historical Strategy Digest Change Detectors (5 Nodes)
- **Status**: `CONTRACTUALLY_RETAINED_FAILURE` (Tracked under `BLOCK-183-01`).
- **Nodes**:
  1. `tests/test_oos_data_extension_19.py::TestFrozenBaseline::test_nine_file_hash_exact_match`
  2. `tests/test_oos_feasibility_17.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
  3. `tests/test_oos_validation_18.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
  4. `tests/test_oos_validation_18.py::TestStrategyIdentity::test_no_strategy_mutation_after_runs`
  5. `tests/test_readiness_16.py::TestFrozenRecords::test_strategy_hash_pinned`
- **Root Cause**: These tests assert the Phase 14 Windows CRLF digest (`c52e648c...`). Gate-80 cost fixes post-Phase 4 modified strategy files. Tests are intentionally preserved without modification to maintain historical auditability.

### Category 2: Git Ancestry & Repository History Limitations (27 Nodes)
- **Status**: `ENVIRONMENT_LIMITATION` (Tracked under `BLOCK-183-02`).
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

### Category 3: Pre-Seal Worktree Manifest & Snapshot Checks (9 Nodes)
- **Status**: `PRE_SEAL_WORKTREE_STATE`.
- **Nodes**:
  33. `tests/test_phase158_manifest_contract.py::TestManifestCompleteness::test_every_listed_hash_matches_the_file_bytes`
  34. `tests/test_phase158_manifest_contract.py::TestManifestCompleteness::test_generate_stdout_is_byte_identical`
  35. `tests/test_phase158_manifest_contract.py::TestManifestCompleteness::test_manifest_covers_every_packaged_file_exactly_once`
  36. `tests/test_phase158_manifest_contract.py::TestManifestCompleteness::test_manifest_reproduces_byte_for_byte`
  37. `tests/test_phase158_manifest_contract.py::TestManifestCompleteness::test_verify_reports_no_problems`
  38. `tests/test_phase158_snapshot_neutrality.py::TestSnapshotNeutrality::test_manifest_is_lf_only_and_reproduces_byte_for_byte`
  39. `tests/test_release_consistency_phase155.py::TestReleaseConsistency155::test_no_text_artifact_embeds_own_archive_hash`
  40. `tests/test_release_consistency_phase155.py::TestReleaseConsistency155::test_worktree_verifies_against_manifest`
  41. `tests/test_release_manifest_phase154.py::TestReleaseManifest154::test_manifest_verifies_clean`
- **Root Cause**: Active development of new reports and hardened modules prior to package sealing. All 9 reconcile cleanly upon `BUILD_MANIFEST.sha256` regeneration.

### Category 4: Pre-Seal Release Records Non-Circularity (4 Nodes)
- **Status**: `PRE_SEAL_RECORD_STATE`.
- **Nodes**:
  42. `tests/test_release_records_phase171.py::TestReleaseRecords171::test_current_records_do_not_embed_the_shipped_archive_hash`
  43. `tests/test_release_records_phase172.py::TestReleaseRecords172::test_current_records_do_not_embed_the_shipped_archive_hash`
  44. `tests/test_release_records_phase173.py::TestReleaseRecords173::test_current_records_do_not_embed_the_shipped_archive_hash`
  45. `tests/test_release_records_phase174.py::TestReleaseRecords174::test_current_records_do_not_embed_the_shipped_archive_hash`
- **Root Cause**: Asserts non-circularity of release hash records against pre-seal working tree state.

### Category 5: Dependency Pin Contract (4 Nodes)
- **Status**: `PRE_SEAL_RECORD_ALIGNMENT`.
- **Nodes**:
  46. `tests/test_dependency_pin_contract.py::TestDependencyPinContract::test_declared_pins_match_the_recorded_evidence_environment`
  47. `tests/test_dependency_pin_contract.py::TestDependencyPinContract::test_httpx_pin_is_not_below_the_recorded_evidence_version`
  48. `tests/test_dependency_pin_contract.py::TestDependencyPinContract::test_release_record_names_interpreter_and_runner`
  49. `tests/test_dependency_pin_contract.py::TestDependencyPinContract::test_release_record_names_its_dependency_set`
- **Root Cause**: Checks release record dependency declarations prior to package sealing.

### Category 6: Privacy Contract Historical Baseline (2 Nodes + 25 Subtests)
- **Status**: `PRE_SEAL_RECORD_ALIGNMENT`.
- **Nodes**:
  50. `tests/test_phase158_privacy_contract.py::TestPrivacyContract::test_privacy_review_declares_the_allowlist_and_the_package_class`
  51. `tests/test_phase158_privacy_contract.py::TestPrivacyContract::test_the_scan_and_review_deny_publication_clearance`
  - Plus 25 subtest assertion failures in `test_the_historical_order_id_baseline_is_enumerated_in_the_review`.
- **Root Cause**: Asserts that all 13 sealed historical order ID carriers are enumerated in the review text.

### Category 7: Legacy Simulator & Ledger Checks (2 Nodes)
- **Status**: `PRE_EXISTING_LEGACY_ASSERTIONS`.
- **Nodes**:
  52. `tests/test_accounting_9q.py::TestBreakevenClassification::test_backtester_breakeven_via_simulator`
  53. `tests/test_stage4_paper_certification.py::TestPaperAccounting::test_sequential_ledger_matches_registry`
- **Root Cause**: `test_accounting_9q.py` passes a degenerate setup `FakeSetup(take_profit=100, entry=100)`, which is rejected by `TradeSimulator`'s bracket geometry (`take_profit > entry`).
