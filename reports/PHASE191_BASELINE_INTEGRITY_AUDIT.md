# QuantEngine Phase 191 — Baseline Integrity Audit Report

**Audit Component**: `Phase191BaselineIntegrityAudit`  
**Date**: 2026-10-21  
**Auditor**: Senior Execution-Safety Auditor & Market-Data Reliability Engineer  
**System Posture**: `NOT_PRODUCTION_READY`  
**Strategy Status**: `EDGE NOT ESTABLISHED`  
**Release Gate**: `HOLD`  
**Order Writes to Exchange**: `0` (Strictly Read-Only Preflight)

---

## 1. Executive Summary

As required by Task 2 of the Phase 191 Master Prompt, an independent cryptographic, structural, and semantic audit of the Phase 190 baseline was conducted prior to any engineering modifications.

All historical captures, sealed reports, and manifests were inspected in place. The primary Phase 190 raw Level 2 streaming market-data capture file:

`research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl`

was independently hashed at the raw binary byte level and parsed from beginning to end.

---

## 2. Cryptographic & Size Verification

| Metric | Phase 190 Recorded Claim | Phase 191 Independent Verification | Discrepancy / Status |
| :--- | :--- | :--- | :--- |
| **File Path** | `research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl` | `research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl` | MATCH |
| **Exact Size** | 237,803 bytes | 237,803 bytes | MATCH (0 bytes diff) |
| **Binary SHA-256** | `fb5835589028693bd6a8bfcf1b72d6515c622e91804d4c41d37acc027279076d` | `fb5835589028693bd6a8bfcf1b72d6515c622e91804d4c41d37acc027279076d` | EXACT MATCH |
| **Summary JSON** | `research/captures/phase190_l2/l2_quality_summary_20261021T064426Z.json` | Present on disk, valid JSON structure | MATCH |
| **Format** | Binary-streamed JSONL (`\n` line delimiters) | Binary-streamed JSONL (`\n` line delimiters) | VALID |

No byte modification or truncation has occurred since Phase 190 sealing.

---

## 3. Independent Record & Sequence Parsing

Every individual line of the 237,803-byte raw capture was independently parsed into its constituent envelope (`receipt_mono_ns`, `receipt_utc_ns`, and `raw` payload):

- **Total JSONL Records**: 246 records
- **Malformed Lines**: 0
- **Unparseable JSON**: 0
- **Non-dict Records**: 0

### Per-Symbol Breakdown & Sequence Continuity

| Symbol | Total Frames | Snapshot Frame | Update Frames | Start Seq | End Seq | Sequence Gaps | Sequence Drops | Continuity State |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BTCUSD** | 209 | 1 | 208 | 364611 | 364819 | 0 | 0 | **100.0% Continuous** |
| **ETHUSD** | 37 | 1 | 36 | 59776 | 59812 | 0 | 0 | **100.0% Continuous** |
| **TOTAL** | **246** | **2** | **244** | — | — | **0** | **0** | **100.0% Continuous** |

Both symbols exhibited strictly monotonic sequence incrementation with zero dropped frames across the entire session duration.

---

## 4. Spreads & Depth Verification

Cross-validation of the orderbook reconstruction confirmed:

### BTCUSD (209 Frames)
- **Best Bid Range**: $67,008.00 – $67,078.00
- **Best Ask Range**: $67,009.00 – $67,079.00
- **Mean Spread**: $1.00 (exactly 1 tick)
- **Min / Max Spread**: $1.00 / $1.00
- **Crossed Book Events**: 0
- **Inverted Book Events**: 0
- **Top-5 Depth Liquidity**: 50 bids, 50 asks maintained at all times post-snapshot.

### ETHUSD (37 Frames)
- **Best Bid Range**: $2,548.20 – $2,551.80
- **Best Ask Range**: $2,548.40 – $2,552.00
- **Mean Spread**: $0.20 (exactly 1 tick)
- **Min / Max Spread**: $0.20 / $0.20
- **Crossed Book Events**: 0
- **Inverted Book Events**: 0
- **Top-5 Depth Liquidity**: 50 bids, 50 asks maintained at all times post-snapshot.

---

## 5. Historical Artifact & Baseline Preservation

In accordance with strict provenance rules:
1. `research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl` was accessed in read-only binary mode.
2. `research/captures/phase190_l2/l2_quality_summary_20261021T064426Z.json` was preserved unchanged.
3. All Phase 189 and Phase 190 reports in `reports/` remain sealed and intact.
4. No network order writes were attempted or permitted.

---

## 6. Audit Verdict

**Phase 190 Baseline Cryptographic & Content Verification**: **PASS**  
The Phase 190 raw capture matches recorded byte counts and SHA-256 digests exactly. Frame counts and sequence metrics independently confirm zero missing frames.
