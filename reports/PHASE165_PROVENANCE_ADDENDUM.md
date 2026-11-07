# Phase 165 Provenance Addendum — Phase 162 Release Gate & Blocker Reconciliation

**Date**: 2026-10-19  
**Target Release**: QuantEngine Phase 165 Engineering Candidate  
**Purpose**: Document and reconcile the cryptographic and semantic provenance discrepancy between the sealed `QuantEngine_PHASE162_RELEASE_CANDIDATE.zip` archive and subsequent working-tree copies of Phase 162 gate/blocker reports.

---

## 1. Summary of Provenance Discrepancy

During the Phase 164 detached forensic audit, an independent cryptographic inspection compared the files inside `QuantEngine_PHASE162_RELEASE_CANDIDATE.zip` against the disk records in the working repository. A hash mismatch was detected on two historical reports:

1. `reports/PHASE162_RELEASE_GATES.json`
2. `reports/PHASE162_BLOCKERS.json`

Both files had been pinned in `tests/test_release_records_phase163.py` under `HISTORICAL_PINS` with the claim: `"preserved unchanged"`. However, the pinned hashes corresponded to post-seal edited versions on disk, not the sealed archive bytes.

---

## 2. Cryptographic Hashes of Both Versions

| Record Path | Sealed Archive Version (`QuantEngine_PHASE162_RELEASE_CANDIDATE.zip`) | Working Tree / Pinned Version (`reports/`) | Preserved Sealed Copy (`reports/historical_sealed_phase162/`) |
| :--- | :--- | :--- | :--- |
| `reports/PHASE162_RELEASE_GATES.json` | `6ec688e80cf4f85b9ad2209ed3d2f858d4c704c6895e4aeffbf9afaabbaf9f64` | `f94aff1f1723c37527975850b733257d0ca26443dbcf81672f7429bd65a668b2` | `PHASE162_RELEASE_GATES_SEALED.json` |
| `reports/PHASE162_BLOCKERS.json` | `7c4c65783ae7041ec7a45a1a412777854d2f38c6938ef18e5537add342d24732` | `5d053de948f7e0a07eae1b24022d2f4cd7d03f7ca92d819b79bd2aceff0fc626` | `PHASE162_BLOCKERS_SEALED.json` |

---

## 3. Root Cause & Rationale for Downgrade

The differences between the sealed and disk versions are semantic downgrades made to prevent false claims of verification:

### 3.1 Funding Through Settlement Claim Downgrade
* **Sealed Version Claim**:
  ```json
  "funding_through_settlement_evidence": "PASS-reconciled-funding-hold-ethusd-exact-debit-match"
  ```
* **Post-Seal Corrected Version**:
  ```json
  "funding_through_settlement_evidence": "UNVERIFIABLE_EXTERNAL-hold-executed-but-raw-capture-lacks-settlement-debit-payload-see-BLOCK-162-05"
  ```
* **Rationale**: The capture file `research/captures/phase148_funding/hold_log.jsonl` recorded `funding_rate: 'None'` and lacked the raw JSON exchange transaction debit payload. Claiming `PASS` was empirically unproven from archive bytes alone. The downgrade to `UNVERIFIABLE_EXTERNAL` was scientifically necessary.

### 3.2 WebSocket Match Claim Downgrade
* **Sealed Version Claim**:
  ```json
  "repeat_match_evidence": "PASS-windowed-ws-rest-reconciliation-2-fills-matched-concurrent-l2-friction-zero-slippage"
  ```
* **Post-Seal Corrected Version**:
  ```json
  "repeat_match_evidence": "PARTIAL_MATCHED_WINDOWED-window-matched-2-of-2-but-pre-window-unaligned-and-seqs-null-see-BLOCK-162-06"
  ```
* **Rationale**: 12 pre-window fills in Candidate B had unaligned market-friction observations and websocket sequence numbers were `null`. Downgrading to `PARTIAL_MATCHED_WINDOWED` accurately reflected the empirical limits of the capture.

---

## 4. Timeline of Incorporation

1. **2026-10-19 01:08 UTC**: `QuantEngine_PHASE162_RELEASE_CANDIDATE.zip` was sealed with the optimistic claims (`6ec688e8...` and `7c4c6578...`).
2. **2026-10-19 01:40 UTC**: Working-tree forensic audit detected that the raw capture lacked funding debit payloads and carried null WebSocket sequence numbers.
3. **2026-10-19 02:00 UTC**: The working-tree copies were amended to honestly state `UNVERIFIABLE_EXTERNAL` and `PARTIAL_MATCHED_WINDOWED`, producing hashes `f94aff1f...` and `5d053de9...`.
4. **2026-10-19 02:15 UTC**: `tests/test_release_records_phase163.py` pinned the corrected hashes, labeling them as Phase 162 records.
5. **2026-10-19 15:30 UTC**: Phase 164 detached vendor audit flagged the mismatch against the sealed archive bytes.
6. **2026-10-19 16:03 UTC (Phase 165)**: Both versions are formally preserved: sealed originals in `reports/historical_sealed_phase162/` and amended working copies in `reports/`, fully reconciled and cross-referenced.

---

## 5. Downstream Records & Test References

* **`tests/test_release_records_phase163.py`**: Pins `f94aff1f...` and `5d053de9...` in `HISTORICAL_PINS`.
* **`reports/PHASE163_RELEASE_GATES.json`**: Cites supersession of `reports/PHASE162_RELEASE_GATES.json`.
* **`reports/historical_sealed_phase162/`**: Preserves byte-identical copies of the original sealed files.
