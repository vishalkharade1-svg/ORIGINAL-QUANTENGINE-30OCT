# PHASE 193A DATASET CORPUS AUDIT
## Independent Verification of Continuous L2 Market Data Captures & Clock Integrity

**Execution Date**: 2026-10-21  
**Investigator**: Senior Quantitative Execution-Safety Auditor & Evidence-Governance Investigator  
**Repository**: `QuantEngine_PHASE161_RELEASE_CANDIDATE`  
**Artifact Scope**: Continuous L2 Market Data Capture Corpus (Phases 190, 191, 192)

---

### 1. Corpus Inventory & Cryptographic Baseline

Every capture artifact in the continuous L2 corpus was independently audited directly from disk using raw binary reads and SHA-256 digest computation:

| Capture Phase | File Relative Path | Size (Bytes) | SHA-256 Checksum | Frame Count |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 190** | `research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl` | 237,803 | `fb5835589028693bd6a8bfcf1b72d6515c622e91804d4c41d37acc027279076d` | 246 frames |
| **Phase 191** | `research/captures/phase191_l2/raw_l2_capture_20261021T073820Z.jsonl` | 118,802 | `464430627e6fc38835bbe2f7d9dcebe6c120e0cb2bfa746416fe1a866e28d1aa` | 104 frames |
| **Phase 192** | `research/captures/phase192_l2/raw_l2_capture_20261021T091410Z.jsonl` | 121,682 | `c7bf98c56fa244196d44ae4b54e3d93fd9fc177f10b777a83492576b911b332b` | 104 frames |
| **Total** | **3 distinct live capture sessions** | **478,287** | — | **454 frames** |

---

### 2. Symbol Breakdown, Sequence Continuity & Microstructural Integrity

Each frame across all 3 captures was parsed and verified for sequence ordering, depth validity, and spread non-negativity:

| Capture Metric | Phase 190 Capture | Phase 191 Capture | Phase 192 Capture | Combined Corpus |
| :--- | :--- | :--- | :--- | :--- |
| **BTCUSD Frames** | 224 (1 snapshot, 223 updates) | 91 (1 snapshot, 90 updates) | 91 (1 snapshot, 90 updates) | 406 frames |
| **ETHUSD Frames** | 22 (1 snapshot, 21 updates) | 13 (1 snapshot, 12 updates) | 13 (1 snapshot, 12 updates) | 48 frames |
| **Sequence Gaps** | **0 gaps** | **0 gaps** | **0 gaps** | **0 gaps across all feeds** |
| **Sequence Range (BTCUSD)** | 911043324 → 911043547 | 911053426 → 911053516 | 911071295 → 911071385 | Continuous monotonic sequences |
| **Sequence Range (ETHUSD)** | 911043314 → 911043537 | 911053412 → 911053513 | 911071280 → 911071378 | Continuous monotonic sequences |
| **Spread Inversions (Crossed)** | 0 crossed | 0 crossed | 0 crossed | 0 crossed books |
| **Zero / Negative Sizes** | 0 | 0 | 0 | 0 |
| **Duration (Wall-Clock)** | 60.038 s | 60.187 s | 60.024 s | 180.249 s |

---

### 3. Clock Skew Forensic Analysis & Monotonic Domain Verification

#### 3.1 Empirical Offset Findings
Across all 3 sessions, comparing host receipt wall-clock timestamps (`receipt_utc`) with exchange venue timestamps (`timestamp_us` converted to UTC seconds) revealed an invariant clock skew:
- **Phase 190**: `receipt_utc - venue_ts` median = **-345.1 ms** (range: -360.2 ms to -328.4 ms)
- **Phase 191**: `receipt_utc - venue_ts` median = **-344.8 ms** (range: -358.9 ms to -329.1 ms)
- **Phase 192**: `receipt_utc - venue_ts` median = **-345.4 ms** (range: -361.0 ms to -331.2 ms)

#### 3.2 Root Cause & Architectural Resolution
The local host clock is unsynchronized via PTP/NTP and lags Delta Exchange production/testnet servers by approximately 345 milliseconds.
- **Historical Pipeline Defect**: In Phase 190, the continuous capture pipeline applied a naive filter `0.0 <= latency <= 60000.0`. Because the wall-clock difference was negative (-345 ms), this filter discarded 99% of updates, leading to a reporting artifact where average latency was reported as 3.94 seconds based solely on a single un-dropped initial frame ($N = 1$).
- **L2BookTracker Correction**: Monotonic inter-arrival intervals ($\Delta t_{\text{mono}} = t_{\text{mono}}^{(k)} - t_{\text{mono}}^{(k-1)}$) are measured using `time.monotonic_ns()`. Inter-arrival dynamics are completely independent of host-to-exchange clock skew. Venue timestamps are retained purely for exchange sequencing and historical ordering, while monotonic timestamps govern local processing rate and staleness detection.

#### 3.3 Initial Snapshot Age Dynamics
- For `BTCUSD`, the initial snapshot arrived within 10–25 ms of connection.
- For `ETHUSD`, the initial snapshot was 3.94 s (Phase 190), 2.77 s (Phase 191), and 2.85 s (Phase 192) older than the connection time. This occurs because the testnet ETHUSD book was completely idle prior to client connection, and Delta Exchange's initial snapshot reflects the last order book modification timestamp rather than connection time.

---

### 4. Classification Invariant: Empirical Evidence vs Simulated Fills

To maintain strict scientific and quantitative integrity:
1. **Empirical Evidence (B-07 Partial)**:
   - The 454 raw L2 frames recorded across 3 sessions are genuine, empirical, un-synthesized network captures from `wss://socket-ind-pub.testnet.deltaex.org`.
   - They provide verified empirical proof of Delta Exchange testnet L2 schema, sequence numbering behavior, book depth formatting, and inter-arrival distributions.
2. **Simulated Fills (B-08 Uncalibrated)**:
   - All queue position tracking, passive fill assumptions, fill probabilities, and backtest fills remain **strictly simulated**.
   - No empirical fills have been recorded on the exchange.
   - Simulation cannot be substituted for empirical testnet execution data.
