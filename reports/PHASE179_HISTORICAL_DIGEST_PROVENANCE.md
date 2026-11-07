# QuantEngine Phase 179 — Historical Strategy Digest Provenance Report

## Executive Summary

Phase 179 conducted a comprehensive forensic audit into the five historical change-detector failures asserting the historical digest `c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6`.

The audit resolved the exact files, byte representations, line-ending interactions, commit provenance, and architectural status of this historical pin.

---

## 1. Forensic Audit Findings

### A. Exact Files Hashed
The historical 9-file composite digest concatenates the SHA-256 hex digests of the following files in strict order:
1. `core/execution/entry_model.py`
2. `core/setup/trade_setup_builder.py`
3. `core/setup/decision_engine.py`
4. `core/execution/execution_engine.py`
5. `core/risk/risk_engine.py`
6. `core/backtesting/accounting.py`
7. `backtesting/backtester.py`
8. `core/paper_trading/paper_trading_engine.py`
9. `config/risk_settings.py`

### B. Representation: Raw Disk Bytes vs Normalized Line Endings
- In all five failing tests (`test_oos_feasibility_17.py`, `test_oos_validation_18.py` (2 tests), `test_oos_data_extension_19.py`, `test_readiness_16.py`), the test implementation directly calls `(ROOT / name).read_bytes()`.
- It hashes the **raw bytes on disk** without line-ending normalization (`\r\n` vs `\n`).
- If any file contains Windows CRLF line endings, its individual SHA-256 digest changes, causing the composite digest to diverge.

### C. Provenance of the Expected Digest (`c52e648c...`)
- **Origin:** Commit `3f198956abdd6f758da7960ba0cbb063fb424947` (Phase 14, September 12, 2026), documented in `research/results/phase14_executable_edge_forensics.json`.
- **Environment:** Recorded on a Windows development workstation where all 9 files were checked out with Windows CRLF (`\r\n`) line endings prior to post-Phase-4 corrections.
- **Subsequent Modifications:** In Phase 4, verified corrections to gate-80 and the cost seam were introduced. In Phase 8, `scripts/recertify_strategy_digest.py` confirmed that the canonical LF digest diverged and determined that re-certifying or modifying the pin is `BLOCKED` unless an operator conducts a full re-execution of the research protocol.
- **Current Disk State:** On disk, 3 files currently contain CRLF (`entry_model.py`, `trade_setup_builder.py`, `execution_engine.py`) and 6 files contain Unix LF, producing the raw digest:
  `9c56f3ff7dea2a3ea98adf226aff775d263ebfcf1bbb2697ca244ab6cd54f35a`
- **Canonical LF Representation:** When all 9 files are normalized to Unix LF (`.replace(b"\r\n", b"\n")`), the canonical LF digest is:
  `ba17582d0ab96913f81d0e6ac652368e609bb28f22a24200f53bf9b6cd60ded5`

---

## 2. Five Failing Test Nodes Census

| Test Node ID | File | Assertion | Root Cause | Classification |
| :--- | :--- | :--- | :--- | :--- |
| `TestStrategyIdentity.test_nine_file_hash_exact_match` | `test_oos_feasibility_17.py` | `digest == STRATEGY_HASH` | Asserts raw disk bytes against CRLF pin `c52e648c...` | `CONTRACTUALLY_RETAINED` |
| `TestStrategyIdentity.test_nine_file_hash_exact_match` | `test_oos_validation_18.py` | `digest == STRATEGY_HASH` | Asserts raw disk bytes against CRLF pin `c52e648c...` | `CONTRACTUALLY_RETAINED` |
| `TestStrategyIdentity.test_no_strategy_mutation_after_runs` | `test_oos_validation_18.py` | `after_hash == STRATEGY_HASH` | Asserts post-run hash against CRLF pin `c52e648c...` | `CONTRACTUALLY_RETAINED` |
| `TestFrozenBaseline.test_nine_file_hash_exact_match` | `test_oos_data_extension_19.py` | `digest == STRATEGY_HASH` | Asserts raw disk bytes against CRLF pin `c52e648c...` | `CONTRACTUALLY_RETAINED` |
| `TestFrozenRecords.test_strategy_hash_pinned` | `test_readiness_16.py` | `digest == art['strategy_hash']` | Asserts raw disk bytes against CRLF pin `c52e648c...` | `CONTRACTUALLY_RETAINED` |

---

## 3. Policy & Preservation Rules

1. **Safety Rule #7 Strict Adherence:**
   - Historical strategy pins and digests are **never rewritten**, modified, or bypassed to force a green test suite.
   - The five failures are contractually preserved under `BLOCK-179-01`.
2. **Phase 165 Identity Architecture:**
   - `core/research/strategy_identity.py` decoupled strategy alpha logic from execution scaffolding:
     - `strategy_core` (6 files): `7cef0d21...`
     - `runtime_infrastructure` (3 files): `d5f9546e...`
     - `canonical_lf_composite`: `ba17582d...`
     - `historical_phase14_pinned_hash`: `c52e648c...`
3. **Formal Resolution Path:**
   - Any future migration to a unified canonical LF baseline requires explicit operator sign-off and recorded re-execution of the research protocol.
