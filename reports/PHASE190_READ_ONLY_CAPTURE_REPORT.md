# QuantEngine Phase 190: Continuous Read-Only Level 2 Market-Data Evidence Report

**Report Identifier**: `reports/PHASE190_READ_ONLY_CAPTURE_REPORT.md`  
**Phase**: 190  
**Timestamp**: `2026-10-21T06:47:26Z`  
**Auditor**: Autonomous Senior Quantitative Engineer & Reliability Specialist  
**Operating Posture**: `NOT_PRODUCTION_READY` | `EDGE NOT ESTABLISHED`  
**Release Gate**: **`HOLD`**  
**Exchange Order Writes**: **`0` (Verified strictly read-only)**  
**Continuous Capture Verdict**: **`PARTIAL`** (180.203s continuous bounded capture verified)  
**Historical Artifact Integrity**: **`VERIFIED / PRESERVED UNCHANGED`**  

---

## 1. Executive Summary & Operational Scope

Phase 190 advanced QuantEngine's market-data infrastructure by implementing hardened, continuous Level 2 (L2) capture reliability, deterministic recovery, and cross-platform byte-exact hashing.

### Key Milestones Achieved:
1. **Historical Baseline Integrity Preservation**:
   - The Phase 188 raw capture (`research/captures/phase188_l2/raw_l2_capture_20261021T052549Z.jsonl`) was independently audited and verified on disk:
     - Exact File Size: **256,038 bytes**
     - Raw Binary SHA-256: `4bd1527eb002bbd048a9502c515e055586cd7dac6dd709f54d4842078b574072`
     - LF-Normalized SHA-256: `1382e1002602e3baff505a0e1c199471f78748538b5463f776b72614807cbbf6`
   - Verified that the artifact was preserved completely intact and without modification.

2. **Hardened Binary Streaming Architecture**:
   - Upgraded `scripts/capture_l2_continuous_pipeline.py` and `core/research/l2_book_tracker.py` to enforce explicit binary mode (`open("wb")`), deterministic `b"\n"` newline delimiters, and incremental SHA-256 hashing directly over the exact disk bytes written.
   - Eliminated the Windows text-mode CRLF translation discrepancy discovered in Phase 188.
   - Added microsecond collision disambiguation (`%Y%m%dT%H%M%S_%fZ`) to prevent partial capture truncation during rapid restarts.
   - Implemented bounded disk limits (`max_disk_mb`) preventing unattended disk exhaustion.

3. **Bounded Continuous Public Capture Execution**:
   - Connected strictly to Delta Exchange India Testnet public WebSocket (`wss://socket-ind-pub.testnet.deltaex.org`).
   - Ran an autonomous, bounded session of **180.203 seconds** (target: 180s).
   - Produced a new, independent, immutable capture: `research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl`.
   - **Exact Disk Size**: **237,803 bytes**.
   - **Exact Binary SHA-256**: `fb5835589028693bd6a8bfcf1b72d6515c622e91804d4c41d37acc027279076d`.
   - **In-Memory vs On-Disk Checksum**: 100% bit-for-bit identical (`fb583558...`). Zero `\r` (CR) bytes detected.
   - **Continuity Scope**: 0 sequence gaps across 246 received frames (BTCUSD: 209 frames, ETHUSD: 37 frames).
   - **Zero Order Writes**: Strictly read-only (`exchange_order_writes = 0`).

---

## 2. Capture Session Metadata & Artifact Provenance

| Parameter | Specification | Evidence / Audit Value |
| :--- | :--- | :--- |
| **Session Capture ID** | `phase190-l2-raw_l2_capture_20261021T064426Z` | Defined in JSON telemetry |
| **Target Venue** | Delta Exchange India | Public market data feed |
| **Environment** | Sandbox / Testnet | `wss://socket-ind-pub.testnet.deltaex.org` |
| **Public Channels Subscribed** | `l2_orderbook` | `BTCUSD`, `ETHUSD` |
| **Authentication Status** | Unauthenticated | Zero credentials loaded or transmitted |
| **Capture Protocol** | `binary_streaming_jsonl_v2` | `open("wb")` with exact `b"\n"` delimiters |
| **Start Time (UTC)** | `2026-10-21T06:44:26.511918+00:00` | High-resolution wall-clock timestamp |
| **End Time (UTC)** | `2026-10-21T06:47:26.716530+00:00` | Clean shutdown upon reaching target |
| **Elapsed Duration** | **180.203 seconds** | Finite, bounded capture session |
| **Raw Disk File Path** | `research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl` | Stored in dedicated phase artifact dir |
| **Raw File Size (Bytes)** | **237,803 bytes** | Exact byte count |
| **Raw File SHA-256** | `fb5835589028693bd6a8bfcf1b72d6515c622e91804d4c41d37acc027279076d` | Independent file hash |
| **Telemetry Summary Path** | `research/captures/phase190_l2/l2_quality_summary_20261021T064426Z.json` | Real-time session metrics |
| **Quality Report Path** | `reports/PHASE190_MARKET_DATA_QUALITY.json` | Governed evidence deliverable |
| **CRLF Bytes Detected** | **0 bytes** | Pure LF verified on Windows filesystem |
| **Exchange Order Writes** | **0** | No write methods invoked or available |

---

## 3. Per-Symbol Market Data Quality & Sequence Tracking

### 3.1 BTCUSD (Delta Product ID 84)

- **Book Integrity State**: `VALID`
- **First Observed UTC**: `2026-10-21T06:44:27.868522+00:00`
- **Last Observed UTC**: `2026-10-21T06:47:25.839536+00:00`
- **Sequence Trajectory**: 364611 $\rightarrow$ 364819
- **Total Frames Received**: **209**
- **Valid Updates**: **209** (100.0% coverage over observed connection)
- **Sequence Gaps**: **0**
- **Duplicate Frames**: **0**
- **Out-of-Order Frames**: **0**
- **Snapshot Resynchronizations**: **1** (Initial snapshot frame 364611 at connect)
- **Stale Updates Detected**: **0** (Max observed interval: 2.1s; threshold: 5.0s)
- **Crossed-Book Incidents**: **0**
- **Spread Distribution**:
  - Closing Spread: $4.00 ($82,830.00 bid / $82,834.00 ask)
  - Average Spread: **$3.9498**
  - Min / Max Spread: **$0.50 / $4.50**
- **Top-of-Book Depth Distribution**:
  - Average Best Bid Depth: **1,304.9952 contracts** (~1.305 BTC)
  - Average Best Ask Depth: **267.1818 contracts** (~0.267 BTC)
- **Receive-to-Event Latency**:
  - Venue matching engine timestamp vs local receive timestamp averaged **204.96 ms**
  - Median: 204.96 ms | p95: 204.96 ms | p99: 204.96 ms

### 3.2 ETHUSD (Delta Product ID 1699)

- **Book Integrity State**: `VALID`
- **First Observed UTC**: `2026-10-21T06:44:27.878950+00:00`
- **Last Observed UTC**: `2026-10-21T06:47:23.664014+00:00`
- **Sequence Trajectory**: 59776 $\rightarrow$ 59812
- **Total Frames Received**: **37**
- **Valid Updates**: **37** (100.0% coverage over observed connection)
- **Sequence Gaps**: **0**
- **Duplicate Frames**: **0**
- **Out-of-Order Frames**: **0**
- **Snapshot Resynchronizations**: **1** (Initial snapshot frame 59776 at connect)
- **Stale Updates Detected**: **0**
- **Crossed-Book Incidents**: **0**
- **Spread Distribution**:
  - Closing Spread: $0.05 ($2,442.45 bid / $2,442.50 ask)
  - Average Spread: **$0.0500** (Strictly 1 tick throughout entire session)
  - Min / Max Spread: **$0.05 / $0.05**
- **Top-of-Book Depth Distribution**:
  - Average Best Bid Depth: **2,239.0541 contracts** (~22.39 ETH)
  - Average Best Ask Depth: **663.8378 contracts** (~6.64 ETH)
- **Receive-to-Event Latency**:
  - Venue matching engine timestamp vs local receive timestamp averaged **3,941.59 ms** (reflects testnet batching characteristics on lower-volume instruments)
  - Median: 3,941.59 ms | p95: 3,941.59 ms | p99: 3,941.59 ms

---

## 4. Explicit Metric Denominator Governance

To prevent misleading claims of continuity, all metrics are governed by explicit denominator definitions:

1. **`valid_coverage_pct`**:
   $$\text{Coverage} = \frac{\text{valid\_updates}}{\text{total\_messages}} \times 100\%$$
   *Definition*: Evaluated strictly over the frames received while the WebSocket socket was open and actively reading frames.

2. **Continuity Claim Boundary**:
   - A sequence gap counter of 0 establishes continuity **only** for the subset of frames observed during the live connection.
   - An empty gap counter over a 180-second session **does not** infer continuous exchange-side coverage across unobserved periods, disconnects, or upstream network outages.
   - Concatenating two disjoint capture sessions into a single file and labeling the aggregate as "continuous" is mathematically invalid and strictly prohibited by QuantEngine evidence standards.

3. **Classification of Duration**:
   - The session achieved **180.203 seconds**.
   - It is honestly classified as **`PARTIAL`**.
   - Neither 24-hour nor multi-day continuity is claimed. Blocker **B-07** remains **`PARTIAL`**.

---

## 5. Security and Credential Isolation Verification

- **Credential Scan**: Verified that no API keys, secrets, passphrase hashes, or private tokens were loaded into the capture environment or written to `.jsonl` files.
- **Endpoint Safety**: Connected exclusively to public domain `socket-ind-pub.testnet.deltaex.org`. Production exchange hostnames (`india.delta.exchange`, `api.delta.exchange`) were blocked by configuration and network guardrails.
- **Write Path Inspection**: Audited `scripts/capture_l2_continuous_pipeline.py`. The script imports zero order execution libraries (`order_executor`, `broker_engine`, `delta_rest`) and exposes no method capable of sending `order_create`, `order_cancel`, or `order_amend` messages.

---

## 6. Phase 190 Evidence Verdict

1. **Capture Reliability**: **`VERIFIED`** (Deterministic binary streaming, running SHA-256, microsecond restart collision safety, and disk limits operate cleanly).
2. **Session Execution**: **`EXECUTED`** (180.203-second capture completed without error or data loss).
3. **Continuity Evidence**: **`PARTIAL`** (180s capture verified; multi-day continuity remains unachieved and tracked under B-07).
4. **Exchange Order Writes**: **`0` (Zero)**.
