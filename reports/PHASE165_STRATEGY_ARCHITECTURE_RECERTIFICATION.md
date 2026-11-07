# Phase 165 Strategy Identity Architecture & Recertification Report

**Date**: 2026-10-19  
**Phase**: 165  
**Topic**: Investigation of `BLOCK-163-01`, Frozen Strategy Digest Drift, and Architectural Decoupling  
**Status**: ARCHITECTURAL RECERTIFICATION RECORDED  

---

## 1. Executive Summary

Historically, QuantEngine pinned a composite SHA-256 digest across nine source files as the canonical identifier of the strategy:
```text
RECORDED_DIGEST = c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6
```
This digest was asserted across five tests (`test_oos_data_extension_19.py`, `test_oos_feasibility_17.py`, `test_oos_validation_18.py` (2 tests), and `test_readiness_16.py`).

Through independent Git history recovery and cryptographic diffing, Phase 165 establishes:
1. The nine files bundled two fundamentally distinct layers: **Quantitative Alpha Strategy & Risk Logic** (6 files) and **Simulation & Runtime Execution Infrastructure** (3 files).
2. The drift from `c52e648c...` originated from two intentional, verified improvements in Phase 4:
   - Removal of the shadow `MIN_CONFIDENCE = 70` in `core/setup/decision_engine.py` to restore `risk_settings.MIN_CONFIDENCE = 80` as the single source of truth.
   - Introduction of the opt-in `cost_spec` parameter in `backtesting/backtester.py` to re-mint breakout costs from actual fill notional.
3. In Phase 164, a genuine lifecycle bug in `core/paper_trading/paper_trading_engine.py` (`_mark_order_filled`) was repaired, changing its hash and thus the composite 9-file hash, even though zero quantitative alpha rules were modified.
4. Simply replacing `c52e648c...` with current bytes would falsify historical baseline integrity. Instead, Phase 165 preserves the historical Phase 14 pin intact while establishing versioned, decoupled identities for Alpha Strategy Core vs Runtime Infrastructure.

---

## 2. Decoupled Identity Architecture (Phase 165)

### 2.1 Layer 1: Quantitative Alpha Strategy Core (v1.1)
The pure quantitative rule layer responsible for identifying order blocks, calculating entry levels, scoring confidence, and validating portfolio risk:
1. `core/execution/entry_model.py`
2. `core/setup/trade_setup_builder.py`
3. `core/setup/decision_engine.py` (Phase 4 verified gate-80 restoration)
4. `core/execution/execution_engine.py`
5. `core/risk/risk_engine.py`
6. `config/risk_settings.py`

* **Canonical LF SHA-256**: `7cef0d21631b57e15a4c07e41cf6aec8400c4048dd350ed862caf22992fa7d9e`

### 2.2 Layer 2: Runtime & Execution Infrastructure (v1.1)
The simulation, accounting, and order execution scaffolding:
1. `core/backtesting/accounting.py`
2. `backtesting/backtester.py` (Phase 4 cost seam)
3. `core/paper_trading/paper_trading_engine.py` (Phase 164 order identity repair)

* **Canonical LF SHA-256**: `d5f9546e0b30b498556b4d0eb58d048e75e9c0a31785bf202ae37f7a599ad3da`

### 2.3 Legacy 9-File Composite (Carried for Historical Continuity)
* **Canonical LF SHA-256**: `ba17582d0ab96913f81d0e6ac652368e609bb28f22a24200f53bf9b6cd60ded5`
* **Raw Disk SHA-256**: `9c56f3ff7dea2a3ea98adf226aff775d263ebfcf1bbb2697ca244ab6cd54f35a`

---

## 3. Preservation of Historical Test Status

The 5 historical change detector tests continue asserting the original Phase 14 pin `c52e648c...`. They are not silenced, bypassed, or overwritten. They remain intentional change detectors recording the divergence between the Phase 14 research baseline and the Phase 165 hardened production engine.
