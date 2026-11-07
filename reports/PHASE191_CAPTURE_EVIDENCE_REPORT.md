# QuantEngine Phase 191 — Read-Only Market-Data Capture Evidence Report

**Audit Component**: `Phase191CaptureEvidenceReport`  
**Date**: 2026-10-21  
**Auditor**: Senior Market-Data Reliability Engineer & Execution-Safety Auditor  
**System Posture**: `NOT_PRODUCTION_READY`  
**Strategy Status**: `EDGE NOT ESTABLISHED`  
**Release Gate**: `HOLD`  
**Continuity Evidence Verdict**: `PARTIAL` (Target Multi-Day Continuous Capture Unfulfilled)  
**Order Writes to Exchange**: `0` (Strictly Read-Only Capture)

---

## 1. Executive Summary

In compliance with Task 7 of the Phase 191 Master Prompt, a bounded, read-only streaming Level 2 market-data capture was conducted on Delta Exchange India testnet.

Operational safeguards enforced:
1. **Endpoint Safety**: Connected exclusively to the unauthenticated public WebSocket endpoint: `wss://socket-ind-pub.testnet.deltaex.org`. Contains zero order-placement, order-modification, or execution capabilities.
2. **Deterministic Binary Persistence**: Frames were streamed line-by-line in binary mode (`open("wb")`) with LF (`\n`) newlines and an incremental, running SHA-256 digest calculated over the exact bytes written to disk.
3. **Safety Ceilings**: Hard disk quota ceiling (1,024 MB) and strict duration timeout (60 seconds) prevented unbounded process execution.
4. **Honest Continuity Accounting**: Disjoint capture sessions are never concatenated. The multi-day capture target remains unfulfilled; blocker **B-07 remains strictly `PARTIAL`**.

---

## 2. Capture Session Metadata & Provenance

| Parameter | Recorded Value |
| :--- | :--- |
| **Phase** | 191 |
| **Session ID** | `phase191-l2-raw_l2_capture_20261021T073820Z` |
| **Venue** | Delta Exchange (India Testnet) |
| **Environment** | `SANDBOX / TESTNET` |
| **Public WS Endpoint** | `wss://socket-ind-pub.testnet.deltaex.org` |
| **Start Time UTC** | `2026-10-21T07:38:20.472672+00:00` |
| **End Time UTC** | `2026-10-21T07:39:20.665796+00:00` |
| **Elapsed Duration** | **60.187 seconds** |
| **Target Duration** | 60.000 seconds |
| **Total Bytes Written** | **118,802 bytes** |
| **Total Frames Streamed** | **104 frames** |
| **Raw Capture Path** | `research/captures/phase191_l2/raw_l2_capture_20261021T073820Z.jsonl` |
| **Exact Binary SHA-256** | `464430627e6fc38835bbe2f7d9dcebe6c120e0cb2bfa746416fe1a866e28d1aa` |
| **Summary JSON Path** | `research/captures/phase191_l2/l2_quality_summary_20261021T073820Z.json` |
| **Transport Reconnects** | **0** |
| **Malformed Frames** | **0** |
| **Rejected Frames** | **0** |
| **Exchange Order Writes** | **0** |

---

## 3. Per-Symbol Market-Data Quality & Telemetry

### 3.1 BTCUSD (91 Frames)
- **Starting Sequence**: 368515
- **Ending Sequence**: 368605
- **Sequence Gaps / Drops**: **0**
- **Out of Order Count**: 0
- **Crossed Book Events**: 0
- **Valid Coverage Percentage**: **100.0%**
- **Spread Statistics**:
  - Min Spread: $3.50
  - Mean Spread: $4.1571
  - Max Spread: $5.50
- **Depth Statistics**:
  - Average Top Bid Depth: 1,160.98 contracts
  - Average Top Ask Depth: 276.23 contracts
- **Clock Domain Difference ($\Delta_{\text{clock}}$)**:
  - Median Clock Offset: -345.999 ms
  - P95 Clock Offset: -320.020 ms
  - P99 Clock Offset: -224.551 ms
  - Valid Frame-0 Snapshot Latency: 14.48 ms

### 3.2 ETHUSD (13 Frames)
- **Starting Sequence**: 60410
- **Ending Sequence**: 60422
- **Sequence Gaps / Drops**: **0**
- **Out of Order Count**: 0
- **Crossed Book Events**: 0
- **Valid Coverage Percentage**: **100.0%**
- **Spread Statistics**:
  - Min Spread: $0.05
  - Mean Spread: $0.0692
  - Max Spread: $0.30
- **Depth Statistics**:
  - Average Top Bid Depth: 1,923.15 contracts
  - Average Top Ask Depth: 765.08 contracts
- **Clock Domain Difference ($\Delta_{\text{clock}}$)**:
  - Median Clock Offset: -342.258 ms
  - P95 Clock Offset: -335.323 ms
  - P99 Clock Offset: +2,771.931 ms (Snapshot Frame 0 age)

---

## 4. Continuity Evidence & Governance Verdict

While the streaming capture pipeline demonstrated zero sequence gaps, zero transport reconnects, and bitwise reproducibility, the total duration was bounded to 60.187 seconds.

Under the project's evidence standards:
1. Multi-day continuous capture across full weekend maintenance and funding settlement cycles has not yet been achieved.
2. Concatenating disjoint sessions (e.g. Phase 190 and Phase 191) to simulate continuity is strictly prohibited.
3. Therefore, **Blocker B-07 remains `PARTIAL`**.

---

## 5. Summary Verdict

**Phase 191 Capture Evidence Classification**: **PARTIAL**  
Pipeline functionality, disk-limit safety, and exact-byte SHA-256 reproducibility are fully verified. Long-duration continuous capture remains open for future authorized observation.
