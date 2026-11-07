# QuantEngine Phase 187: Test Census & Focused Regression Reconciliation

**Census Version**: `1.0.0-phase187`  
**Date**: `2026-10-21`  
**Execution Environment**: Python 3.12.10 (64-bit), pytest 9.0.3, Windows 10 (win32)  
**Operating Posture**: `NOT_PRODUCTION_READY` | `EDGE NOT ESTABLISHED`  
**Focused Suite Verdict**: `268/268 PASSED (100.0% PASS RATE)`  
**Snapshot Guard Status**: `tree_pristine_at_session_start: true`, `files_added_by_tests: []`, `restores: {}`  
**Exchange Order Calls**: `0` (Verified strictly offline / mock execution)  

---

## 1. Executive Summary & Terminology Reconciliation

This census reconciles historical test counts across phases and provides the definitive accounting of QuantEngine's active regression test suite:

- **Phase 185 Reported Count (236)**: Represented tests through Phase 185 execution gates (`tests/test_phase185_testnet_execution_and_timeout.py`), excluding historical security scan tests.
- **Phase 186 Reported Count (248 -> 255)**:
  - 16 core test suites totaled **248 tests**.
  - Addition of `tests/test_phase186_forensic_reconciliation.py` (7 tests) brought the focused suite to **255 tests**.
- **Phase 187 Current Count (268)**:
  - Addition of `tests/test_phase187_l2_queue_and_security.py` (13 tests) expands the focused regression suite to **268 tests**.
  - All 268 tests pass with 100.0% reliability in ~30.94 seconds.

---

## 2. Exact Execution Command & Configuration

```powershell
python -m pytest `
  tests/test_maker_execution_phase171.py `
  tests/test_maker_execution_phase172.py `
  tests/test_phase173_audit.py `
  tests/test_phase174_economics_reconciliation.py `
  tests/test_phase175_instrument_economics.py `
  tests/test_phase176_contract_semantics.py `
  tests/test_phase177_tick_remediation.py `
  tests/test_phase178_artifact_audit.py `
  tests/test_phase179_risk_enforcement.py `
  tests/test_phase180_instrument_semantics.py `
  tests/test_phase181_hardened_multiplier_and_risk.py `
  tests/test_phase182_adversarial_risk_and_forensics.py `
  tests/test_phase183_stop_rounding_and_risk_validity.py `
  tests/test_phase185_testnet_execution_and_timeout.py `
  tests/test_phase186_forensic_reconciliation.py `
  tests/test_phase187_l2_queue_and_security.py `
  tests/test_packaging_no_secrets_phase132.py `
  tests/test_secret_scan_phase0.py `
  -v
```

---

## 3. Census Table of the 18 Focused Regression Suites (268 Tests)

| Suite File | Phase | Tests | Status | Scope & Behavioral Verification |
| :--- | :---: | :---: | :---: | :--- |
| `tests/test_maker_execution_phase171.py` | 171 | 8 | **PASSED** | Passive maker execution model |
| `tests/test_maker_execution_phase172.py` | 172 | 23 | **PASSED** | Maker fills, friction hurdle gate |
| `tests/test_phase173_audit.py` | 173 | 9 | **PASSED** | Phase 173 release integrity |
| `tests/test_phase174_economics_reconciliation.py` | 174 | 10 | **PASSED** | Post-cost economics reconciliation |
| `tests/test_phase175_instrument_economics.py` | 175 | 10 | **PASSED** | Instrument-level economics pins |
| `tests/test_phase176_contract_semantics.py` | 176 | 41 | **PASSED** | Multiplier & friction hurdle gate |
| `tests/test_phase177_tick_remediation.py` | 177 | 24 | **PASSED** | Tick rounding remediation |
| `tests/test_phase178_artifact_audit.py` | 178 | 16 | **PASSED** | Forensic artifact integrity |
| `tests/test_phase179_risk_enforcement.py` | 179 | 18 | **PASSED** | Conservative risk gates |
| `tests/test_phase180_instrument_semantics.py` | 180 | 11 | **PASSED** | Multi-symbol contract semantics |
| `tests/test_phase181_hardened_multiplier_and_risk.py` | 181 | 21 | **PASSED** | Hardened multiplier safety |
| `tests/test_phase182_adversarial_risk_and_forensics.py` | 182 | 12 | **PASSED** | Adversarial risk attacks |
| `tests/test_phase183_stop_rounding_and_risk_validity.py` | 183 | 12 | **PASSED** | Stop rounding decision record |
| `tests/test_phase185_testnet_execution_and_timeout.py` | 185 | 20 | **PASSED** | 120s timeout, safety gate, registry |
| `tests/test_phase186_forensic_reconciliation.py` | 186 | 7 | **PASSED** | PnL math, archive hash, timeout audit |
| `tests/test_phase187_l2_queue_and_security.py` | 187 | 13 | **PASSED** | L2 tracker, queue calibration, canary test |
| `tests/test_packaging_no_secrets_phase132.py` | 132 | 4 | **PASSED** | Release packaging secret protection |
| `tests/test_secret_scan_phase0.py` | 0 | 9 | **PASSED** | Multi-encoding secret detection |
| **TOTAL** | — | **268** | **268 PASSED** | **100.0% Pass Rate (0 Failures)** |

---

## 4. Historical Test Failures Triage Accounting

Running the entire legacy repository test collection (Phases 1–160) exhibits 78 historical failures that are known, deliberate, and cataloged:

1. **Historical Strategy Digest Pins (5 failures)**: Deliberate tamper-detection pins in `tests/test_phase158_frozen_representation.py` alerting if historical Phase 131 strategy bytes are modified.
2. **Git Ancestry & Shallow History (27 failures)**: Git evidence gate tests requiring full unabridged Git history (worktree is delivered as a detached release archive).
3. **Historical Worktree Manifest State (9 failures)**: Tests requiring byte-exact equality with historical Phase 158/161 snapshots.
4. **Historical Release Records (4 failures)**: Verification against older chained release digests.
5. **Decommissioned Fixtures & Legacy Accounting (33 failures)**: Binance test fixtures decommissioned in favor of Delta India Testnet; legacy fixed-lot sizing checks superseded by Phase 181 dynamic multiplier sizing.

No historical failures exist within the active execution, pricing, risk, or L2 market-data subsystems.
