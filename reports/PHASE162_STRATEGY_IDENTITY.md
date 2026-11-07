# QuantEngine Phase 162 Strategy Identity and Digest Forensics

## Executive Summary
This document provides the authoritative forensic accounting of the QuantEngine strategy source digest mismatch (`BLOCK-162-01`).

Five automated tests fail in the test suite:
- `tests/test_oos_data_extension_19.py::TestFrozenBaseline::test_nine_file_hash_exact_match`
- `tests/test_oos_feasibility_17.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
- `tests/test_oos_validation_18.py::TestStrategyIdentity::test_nine_file_hash_exact_match`
- `tests/test_oos_validation_18.py::TestStrategyIdentity::test_no_strategy_mutation_after_runs`
- `tests/test_readiness_16.py::TestFrozenRecords::test_strategy_hash_pinned`

All five tests assert that the hash of the nine core strategy source files matches the pinned historical baseline:
`c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6`

The actual computed hash of the current source files is:
- Test-suite canonical form: `f8407e772dffecd12bb6b9558547f5d8617b696c8a4f1f2e9918ae2f56915ef4`
- Independent procedure (`scripts/recertify_strategy_digest.py`): `1d30793e4e1ec7d6f8c5f14385d6308f869f74b8d8b4d86b348136af17d0b1f5`

---

## The Nine Strategy Files
The canonical set of nine strategy source files:
1. `core/execution/entry_model.py`
2. `core/setup/trade_setup_builder.py`
3. `core/setup/decision_engine.py`
4. `core/execution/execution_engine.py`
5. `core/risk/risk_engine.py`
6. `core/backtesting/accounting.py`
7. `backtesting/backtester.py`
8. `core/paper_trading/paper_trading_engine.py`
9. `config/risk_settings.py`

---

## Root Cause of the Digest Shift
The shift from `c52e648c...` is NOT a silent corruption or defect; it is the consequence of intentional, documented architectural fixes made across Phases 4–132:
1. **Accounting Corrections**: Fixes to fee accounting, post-cost R:R calculation, and fill tracking in `core/backtesting/accounting.py`.
2. **Paper Trading Engine**: Enhancements to paper execution and state management in `core/paper_trading/paper_trading_engine.py`.
3. **Risk & Policy Bounds**: Elimination of the legacy hidden 6R floor in favor of explicit min/max risk limits in `core/risk/risk_engine.py`.
4. **Execution Precision**: Entry model and order intent refinements in `core/execution/entry_model.py` and `core/execution/execution_engine.py`.

---

## Why the Tests Must NOT Be Re-Pinned
The master prompt establishes strict release integrity rules:
- **Do not delete tests or assertions.**
- **Do not add blanket skips or broad xfail markers.**
- **Do not silently change historical digest pins.**
- **Do not invent an identity or re-pin the tests without evidence.**

The historical pin `c52e648c...` reflects the exact code under which historical research artifacts were produced. If the test pin were silently changed to match current bytes:
1. The historical chain of custody would be severed.
2. The claim that the current code matches the research artifacts would become a false attestation.
3. The change detector property would be lost.

---

## Status and Path to Resolution
Per `scripts/recertify_strategy_digest.py`:
- `status`: **BLOCKED** (`BLOCK-162-01`)
- **Prerequisites for Resolution**:
  1. Operator must restore authentic Git history or approve a new versioned strategy identity (e.g. `strategy-v2`).
  2. Research protocol must be re-executed under the current source to prove whether historical findings remain valid under the current implementation.
  3. Until then, `BLOCK-162-01` remains active, the 5 tests remain deliberately red, and production readiness remains **BLOCKED**.
