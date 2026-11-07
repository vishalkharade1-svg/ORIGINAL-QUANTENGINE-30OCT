# Phase 162 Empirical Capture Report

**Phase:** 162  
**Date:** 2026-10-18  
**Venue:** Delta Exchange India Testnet (`cdn-ind.testnet.deltaex.org` / `socket-ind.testnet.deltaex.org`)  
**Overall Release Verdict:** `NOT_PRODUCTION_READY` (Empirical evidence advancement only; live trading readiness not established)

---

## Executive Summary

Phase 162 audited and recorded empirical captures on Delta Exchange India Testnet. In accordance with the forensic audit findings:
1. **`BLOCK-161-02` (Funding-Through-Settlement Evidence):** Evaluated via **Candidate A**. Held a 1-contract ETHUSD position across the 16:00 UTC funding settlement boundary (+5-minute margin buffer) and flattened the position cleanly. However, because the raw capture artifact (`research/captures/phase148_funding/hold_log.jsonl`) contains `funding_rate_pre/post: "None"` and does not contain the raw exchange debit transaction payload, the reported `-0.00237942 USD` debit is a theoretical calculation in report prose. The gate is therefore carried as **`BLOCK-162-05` (`UNVERIFIABLE_EXTERNAL`)**.
2. **`BLOCK-161-03` (Repeat-Match Private WebSocket Fill Reconciliation):** Evaluated via **Candidate B**. Executed a two-leg BTCUSD sequence under concurrent private WebSocket streaming and public Level 2 orderbook delta logging. Achieved windowed match (`MATCHED_WINDOWED`, 2/2 in-window fills matched). However, 12 pre-window fills had `module_error: "ValueError: no aligned market-friction observation..."` / `NO_ALIGNED_SAMPLE`, and WebSocket sequences are null. Under `execution_economics_certification.py:164`, `MATCHED_WINDOWED` does not satisfy full `MATCHED` certification. The gate is carried as **`BLOCK-162-06` (`PARTIAL_MATCHED_WINDOWED`)**.
3. **`BLOCK-161-06` (Old-Account ADAUSD Position):** Carried as **`BLOCK-162-04` (`BLOCKED_EXTERNAL`)**. Verbal operator assertion is insufficient; authentic venue capture of the closure transaction is required.

---

## 1. Candidate A: Funding-Through-Settlement Hold (ETHUSD)

### 1.1 Objective & Parameters
- **Target Contract:** `ETHUSD` (Delta Testnet Perpetual)
- **Position Size:** 1 contract ($0.01\text{ ETH}$)
- **Entry Type:** Limit buy on the best ask (taker touch)
- **Settlement Target:** 16:00:00 UTC (2026-10-18)
- **Buffer:** +5 minutes post-settlement margin verification (hold release at 16:05:00 UTC)
- **Exit Type:** Limit sell on the best bid (clean flat verification)
- **Artifact:** `research/captures/phase148_funding/hold_log.jsonl`

### 1.2 Execution Chronology
1. **Pre-flight Flat Verification:**
   - Account verified flat ($0\text{ ETH}$, $0\text{ open orders}$) at `2026-10-18T15:42:54.079024Z`.
   - Quote touch: Bid `2371.95`, Ask `2372.00`.
2. **Entry Leg:**
   - Order Role: Entry Limit Buy (documented in `hold_log.jsonl`)
   - Placed: `2026-10-18T15:42:55.124925Z`
   - Fill ID: `4d3963f599b4499d940571d6858e71e3` (recorded in hold metadata)
   - Price: `2372.00 USD` (corroborated in `hold_log.jsonl`)
   - Size: `1` contract ($0.01\text{ ETH}$)
3. **Settlement Passage:**
   - 16:00:00 UTC settlement window passed.
   - Buffer held until `2026-10-18T16:05:25.795656Z`.
4. **Exit Leg:**
   - Order Role: Exit Limit Sell (documented in `hold_log.jsonl`)
   - Placed: `2026-10-18T16:05:26.708800Z`
   - Fill ID: `b9484a83b1d248b6a05509fcd694787d` (recorded in hold metadata)
   - Price: `2371.10 USD` (corroborated in `hold_log.jsonl`)
   - Size: `1` contract
   - Exit filled: `2026-10-18T16:05:32.533496Z`.
5. **Post-flight Flat Verification:**
   - Position size: `0` (corroborated flat in `hold_log.jsonl`)
   - Open orders: `0`

### 1.3 Settlement Cashflow Audit Limitation (Finding H3)
- **Reported Figures (Prose / Theoretical):**
  - Transaction UUID: `b7ff2f7c73b149dcb46928b1c388634e`
  - Timestamp: `2026-10-18T16:05:27Z`
  - Settlement Mark Price: `2379.42 USD/ETH`
  - Funding Rate: `0.00010000` (+0.0100%)
  - Debit: `-0.00237942 USD`
- **Audit Limitation:** The raw repository capture `research/captures/phase148_funding/hold_log.jsonl` contains `funding_rate_pre: "None"`, `funding_rate_post: "None"`, and only `funding_rows: 1`. It does not contain the raw JSON wallet transaction payload, debit amount, or individual fill objects.
- **Verdict:** While entry/exit prices and the flat end state are corroborated by the raw capture, the debit reconciliation compares an observed figure against a formula from the same inputs without an independent raw payload. Classified as **`UNVERIFIABLE_EXTERNAL` (carried as `BLOCK-162-05`)**.

---

## 2. Candidate B: Repeat-Match Private WebSocket Fill Reconciliation (BTCUSD)

### 2.1 Objective & Parameters
- **Target Contract:** `BTCUSD` (Product ID 84, Contract Value $0.001\text{ BTC}$)
- **Execution Script:** `scripts/bounded_testnet_reconciled_experiment.py`
- **Socket Stream:** Authenticated private WebSocket `v2/user_trades` + concurrent public Level 2 orderbook updates (`l2orderbook`)
- **Isolation Scope:** Windowed socket capture interval ($t_{\text{start}} = 1792341667321\text{ ms}$, $t_{\text{end}} = 1792341669846\text{ ms}$)
- **Artifacts Directory:** `research/captures/phase162_recon/`

### 2.2 Execution Chronology
1. **Pre-flight State:**
   - Account verified flat ($0\text{ BTC}$, $0\text{ open orders}$).
   - WebSocket authenticated and subscribed to `v2/user_trades`.
   - Level 2 orderbook stream actively recording delta frames.
2. **Leg 1 (Buy):**
   - Order Role: Bounded Limit Buy (documented in `recon_experiment_report.json`)
   - Order Price: `81092.0 USD`
   - Fill ID: `d1c5c852d2904b9a8bd1ddf8131852fa`
   - Executed Price: `81082.5 USD`
   - Executed Size: `1` contract
   - Private WS Frame: Received and captured (`private_ws_frames.json`).
3. **Leg 2 (Sell):**
   - Order Role: Bounded Limit Sell (documented in `recon_experiment_report.json`)
   - Order Price: `81078.5 USD`
   - Fill ID: `bceea400d432436086278effc0148c64`
   - Executed Price: `81078.5 USD`
   - Executed Size: `1` contract
   - Private WS Frame: Received and captured (`private_ws_frames.json`).
4. **Post-flight State:**
   - Account verified flat ($0\text{ BTC}$, $0\text{ open orders}$).

### 2.3 Windowed Reconciliation Analysis & Audit Limitations (Findings M1, M2, M3)
- **Prices Verified (Finding M1):** Fills in raw captures (`rest_fills.json`, `private_ws_frames.json`) are verified at `81082.5 USD` (buy) and `81078.5 USD` (sell).
- **In-Window Fills:** 2 fills (`d1c5c852...`, `bceea400...`), matched 2 / 2 between private WebSocket frame stream and REST execution record.
- **Audit Limitation (Finding M2):**
  - `MATCHED_WINDOWED` is not full `MATCHED` certification under `execution_economics_certification.py:164`.
  - The report's `fill_friction_binding` recorded `module_error: "ValueError: no aligned market-friction observation..."` for 12 pre-window fills (`NO_ALIGNED_SAMPLE`).
  - `websocket_first_seq` and `websocket_last_seq` are `null`.
- **Reconciliation Fallback (Finding M3):** `scripts/bounded_testnet_reconciled_experiment.py` has been updated to preserve the strict reconciliation failure (`strict_reconciliation_attempt`) in the evidence dictionary rather than silently falling back to windowed matching.
- **Verdict:** Repeat-match WebSocket evidence is classified as **`PARTIAL_MATCHED_WINDOWED` (carried as `BLOCK-162-06`)**.

### 2.4 Level 2 Friction & Slippage Binding
- **Total L2 Observations Captured:** 92 snapshots spanning 74,575 ms (`research/captures/phase162_recon/l2/`).
- **Leg 1 Binding (`d1c5c852...`):** Aligned within 165 ms of top-of-book state. Fill price `81082.5`, Reference price `81082.5`, Slippage `0.0 USD` (0 bps).
- **Leg 2 Binding (`bceea400...`):** Aligned within 150 ms of top-of-book state. Fill price `81078.5`, Reference price `81078.5`, Slippage `0.0 USD` (0 bps).

---

## 3. Privacy & Restricted Evidence Classification

The captured raw private frames contain the operator's Testnet account identifier (parameterised in `scripts/security/scan_privacy.py`):
- `research/captures/phase162_recon/private_ws_archive.json`
- `research/captures/phase162_recon/private_ws_frames.json`

Both files have been declared in `RESTRICTED_EVIDENCE_PATHS` in `scripts/security/scan_privacy.py` (total allowlist: 8 files) and are covered under the release manifest `BUILD_MANIFEST.sha256`. The package is classified as a **restricted evidence package** and is **NOT cleared for public redistribution**.

---

## 4. Disposition of Carried Blockers

| Blocker ID | Description | Phase 162 Disposition | Justification |
|---|---|---|---|
| `BLOCK-161-01` | Strategy digest re-certification | **CARRIED (`BLOCK-162-01`)** | 5 tests stay red by contract pinning `c52e648ca24f...`; change detectors remain intact. |
| `BLOCK-161-04` | Git ancestry evidence facts | **CARRIED (`BLOCK-162-02`)** | 40 facts remain gated `BLOCKED_EVIDENCE` in source archive mode. |
| `BLOCK-161-05` | Vendor-independent audit | **CARRIED (`BLOCK-162-03`)** | Third-party vendor independence not yet performed. |
| `BLOCK-161-06` | Old-account ADAUSD position | **CARRIED (`BLOCK-162-04`)** | ADAUSD position on old account awaits authenticated exchange capture. |
| `BLOCK-161-02` | Funding-through-settlement evidence | **CARRIED (`BLOCK-162-05`)** | Hold executed; raw hold_log lacks funding rate/debit payload. Classified UNVERIFIABLE_EXTERNAL. |
| `BLOCK-161-03` | Repeat-match private WS reconciliation | **CARRIED (`BLOCK-162-06`)** | Partial only: windowed match (`MATCHED_WINDOWED`); 12 pre-window unaligned, sequences null. |
