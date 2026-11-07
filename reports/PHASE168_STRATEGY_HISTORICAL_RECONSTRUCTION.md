# Phase 168 Strategy Historical Identity Reconstruction Report

**Date:** 2026-10-19  
**Status:** RECONSTRUCTED_AUDITED  
**System Status:** `NOT_PRODUCTION_READY`  
**Strategy Status:** `EDGE NOT ESTABLISHED`  

---

## 1. Context & Forensic Objective

The historical strategy baseline pins a 9-file composite SHA-256 digest:
`c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6`

Five historical change-detector tests assert exact match against this value:
- `tests/test_oos_data_extension_19.py::TestFrozenBaseline::test_nine_file_hash_exact_match`
- `tests/test_oos_feasibility_17.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
- `tests/test_oos_validation_18.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
- `tests/test_oos_validation_18.py::TestStrategyIdentity::test_no_strategy_mutation_after_runs`
- `tests/test_readiness_16.py::TestFrozenRecords::test_strategy_hash_pinned`

Rather than rewriting or forcing pins green, Phase 168 forensically reconstructs the strategy's historical identity across Git commits and uncommitted disk state using `core/research/historical_reconstruction.py`.

---

## 2. Historical Milestone Reconstructions

The 9 legacy files were inspected across milestones in the restored Git database:

| Milestone / Source | Commit | Composite LF Digest | Composite Raw Digest | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 14 Baseline Mint** | `3f19895` | `db5bcdc01cd88b6c...` | `db5bcdc01cd88b6c...` | Git blobs stored canonical LF |
| **Phase 14 Runtime Boundary** | `fbeb860` | `9eff61b777846c7f...` | `9eff61b777846c7f...` | Introduced runtime broker & executor gates |
| **Git HEAD (Current Branch)** | `ffefa14` | `9eff61b777846c7f...` | `9eff61b777846c7f...` | Current committed repository HEAD |
| **Current Disk Working Tree** | `DISK` | `ba17582d0ab96913...` | `9c56f3ff7dea2a3e...` | Windows CRLF on 3 files + local fixes |
| **Historical Test Pin** | `PIN` | N/A | `c52e648ca24fb03b...` | Uncommitted Windows tree prior to `3f19895` |

---

## 3. File-by-File Decomposition & Layer Mapping

The legacy 9-file composite combined quantitative trading rules with simulation scaffolding. In Phase 165/168, these are mapped into decoupled layers:

### Layer A: Alpha Strategy Core (6 Files)
1. `core/execution/entry_model.py`:
   - SHA-256 (LF): `8cb0fb2f654b17a12bce1e8e04b407a514d4ef6331a9ca3b3b44b82bc265e311`
   - State: **Identical to Phase 14 baseline** (LF canonical).
2. `core/setup/trade_setup_builder.py`:
   - SHA-256 (LF): `f780310c85c2c5443a60a7246bcf3a137ce74ca5d5069f9e31d4e0e5a65df19f`
   - State: **Identical to Phase 14 baseline** (LF canonical).
3. `core/setup/decision_engine.py`:
   - SHA-256 (LF): `81183fd8db8098c1995874288009bbbe8b8b082fe286699fc285090f772fc643`
   - State: Modified in Phase 4 (shadow `MIN_CONFIDENCE=70` verification gate).
4. `core/execution/execution_engine.py`:
   - SHA-256 (LF): `19a469e1c2e26ea42a1789c17dfaa7cb0625c2763f350c371077717d23d8c11e`
   - State: **Identical to Phase 14 baseline** (LF canonical).
5. `core/risk/risk_engine.py`:
   - SHA-256 (LF): `c0f4a1b32bb4a123f1ce4b3b18593eb4620025fa8964d57c79e78a08be0402e1`
   - State: **Identical in Git**; uncommitted Phase 13 refinement.
6. `config/risk_settings.py`:
   - SHA-256 (LF): `7c38bd8915003b6d21659a8507ba9a4190c4bf49122fa45e31f0cf37dcfe04d4`
   - State: **Identical in Git**; local configuration setting.

**Alpha Strategy Core (v1.1) LF Digest:**
`7cef0d21631b57e15a4c07e41cf6aec8400c4048dd350ed862caf22992fa7d9e`

### Layer B: Runtime & Execution Infrastructure (3 Files)
1. `core/backtesting/accounting.py`:
   - SHA-256 (LF): `e668a77eb6be336a441df86db330c6a5ae6bb7540a92d77d70d2f09d6fbb6b3e`
   - State: Phase 132-C cost wiring and post-cost recalculation fix.
2. `backtesting/backtester.py`:
   - SHA-256 (LF): `c92b07d9b99092496e5792d47d065ce70e9f7435f3089d81373595ea11db896d`
   - State: Phase 4 `cost_spec` parameter threading.
3. `core/paper_trading/paper_trading_engine.py`:
   - SHA-256 (LF): `7aa2518e38f9024f22c153715d0fcb3b7bb6903274294ca8f5539fa9e1a8a25d`
   - State: Phase 164 `_mark_order_filled` consistency fix (registered paper orders as filled on terminal event).

**Runtime Infrastructure (v1.1) LF Digest:**
`d5f9546e0b30b498556b4d0eb58d048e75e9c0a31785bf202ae37f7a599ad3da`

---

## 4. Integrity Decision & Preservation Contract

1. **Why `c52e648c...` is Preserved**:
   The 5 tests are active change detectors. Altering their pins to match `9c56f3ff...` (raw disk) or `ba17582d...` (LF canonical) without running the complete out-of-sample research pipeline would fabricate research recertification.
2. **Contract Decision**:
   The 5 tests are **retained as red by contract** under `BLOCK-168-01`.
3. **Decoupled Future-Proof Architecture**:
   New regression suites test `Alpha Strategy Core (v1.1)` and `Runtime Infrastructure (v1.1)` independently via `core/research/strategy_identity.py`, allowing runtime bugfixes to proceed without corrupting quantitative strategy identity.
