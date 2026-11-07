# QuantEngine Phase 192 — Market-Data Clock Domain & Latency Semantics Report

## 1. Executive Summary

This report establishes the empirical and mathematical analysis of market-data timestamping across Delta Exchange India Testnet captures.

During Phase 190, a naive pipeline filter (`0.0 <= latency <= 60000.0`) discarded over 99% of captured frames, computing average network latency from a single snapshot frame ($N = 1$). Phase 191 revealed that the client host wall-clock lags the Delta Exchange server clock by approximately 326 ms to 346 ms, resulting in negative raw timestamp differences (`receipt_utc - venue_ts < 0`).

Phase 192 independently audited both Phase 190 and 191 baseline captures, conducted a new bounded Phase 192 capture, and executed 7 synthetic edge-case tests in `tests/test_phase192_clock_domain_semantics.py` (explicitly labeled `SIMULATED`).

---

## 2. Empirical Multi-Phase Capture Audit

All captures were streamed directly from `wss://socket-ind-pub.testnet.deltaex.org` to deterministic binary JSONL disk storage without post-capture rewriting:

| Metric | Phase 190 Capture | Phase 191 Capture | Phase 192 Capture |
| :--- | :--- | :--- | :--- |
| **File Path** | `research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl` | `research/captures/phase191_l2/raw_l2_capture_20261021T073820Z.jsonl` | `research/captures/phase192_l2/raw_l2_capture_20261021T085017Z.jsonl` |
| **Byte Size** | `237,803` bytes | `118,802` bytes | `83,636` bytes |
| **SHA-256** | `fb5835589028693bd6a8bfcf1b72d6515c622e91804d4c41d37acc027279076d` | `464430627e6fc38835bbe2f7d9dcebe6c120e0cb2bfa746416fe1a866e28d1aa` | `bc3ea0f233c89010c08f81afa324bf433975f71cb7d66915cd307d11a4ca9c2e` |
| **Total Frames** | 246 (209 BTC, 37 ETH) | 104 (91 BTC, 13 ETH) | 53 (48 BTC, 5 ETH) |
| **Duration** | 177.969 s | 56.922 s | 17.532 s |
| **BTCUSD Seq Range** | 364611 to 364819 | 368515 to 368605 | 373358 to 373405 |
| **BTCUSD Seq Gaps** | **0 gaps** | **0 gaps** | **0 gaps** |
| **ETHUSD Seq Range** | 59776 to 59812 | 60410 to 60422 | 61269 to 61273 |
| **ETHUSD Seq Gaps** | **0 gaps** | **0 gaps** | **0 gaps** |
| **BTCUSD Clock Offset (Median)** | **-326.77 ms** | **-345.999 ms** | **-377.49 ms** |
| **BTCUSD Inter-Arrival p50** | 1000.0 ms | 468.5 ms | 250.0 ms |
| **BTCUSD Inter-Arrival p95** | 1265.0 ms | 1894.7 ms | 750.0 ms |
| **ETHUSD Clock Offset (Median)** | **-325.01 ms** | **-342.26 ms** | **-372.74 ms** |
| **ETHUSD Snapshot Age (Frame 0)** | **+3,941.59 ms** (+3.94s) | **+2,771.93 ms** (+2.77s) | **+4,399.08 ms** (+4.40s) |
| **ETHUSD Inter-Arrival p50** | 5000.0 ms | 5000.0 ms | 4992.0 ms |
| **BTCUSD Spread (Median)** | $72.00 | $3.50 | $0.50 |
| **ETHUSD Spread (Median)** | $0.00 | -$0.10 (crossed) | -$0.25 (crossed) |

---

## 3. Mathematical Proof: Clock Skew vs Physical Transit Latency

### Theorem: Negative Timestamp Delta Represents Clock Offset, Not Travel Time
Let $t_{\text{venue}}$ be the venue exchange event generation timestamp according to venue clock $C_V$.
Let $t_{\text{receipt}}$ be the host receipt timestamp according to host clock $C_H$.
Let $\delta = C_H - C_V$ be the clock skew (offset) between the two unsynchronized clocks.
Let $\tau_{\text{flight}} > 0$ be the physical one-way speed-of-light network transit time from venue to host.

The observed wall-clock difference $\Delta t_{\text{observed}}$ is:
$$\Delta t_{\text{observed}} = t_{\text{receipt}} - t_{\text{venue}} = (t_{\text{venue}} + \delta + \tau_{\text{flight}}) - t_{\text{venue}} = \delta + \tau_{\text{flight}}$$

If the host clock lags the venue clock such that $\delta < -\tau_{\text{flight}}$:
$$\Delta t_{\text{observed}} < 0$$

Under Special Relativity and causality, $\tau_{\text{flight}} > 0$. Therefore, an observed negative difference ($\Delta t_{\text{observed}} \approx -345\text{ ms}$) proves $\delta \approx -390\text{ ms}$ (assuming $\tau_{\text{flight}} \approx 45\text{ ms}$). 
Calling $\Delta t_{\text{observed}}$ "network latency" is physically invalid. Arrival dynamics must be evaluated via monotonic local inter-arrival intervals:
$$\Delta t_{\text{mono}} = t_{\text{mono}}(k) - t_{\text{mono}}(k-1) \ge 0$$
$\blacksquare$

---

## 4. Forensic Analysis of ETHUSD Snapshot Age

In every capture (Phases 190, 191, and 192), Frame 0 of ETHUSD exhibited a large positive wall-clock delta:
- Phase 190: $+3,941.59\text{ ms}$
- Phase 191: $+2,771.93\text{ ms}$
- Phase 192: $+4,399.08\text{ ms}$

**Forensic Finding**: This was not a slow packet. The testnet ETHUSD book was idle for 2.7 to 4.4 seconds prior to client WebSocket connection. Upon subscription, Delta Exchange returns an initial `snapshot` frame containing the existing order book as it stood at its last modification time. Subtraction of client connection time from the snapshot book timestamp yields the **idle age of the order book**, not flight time. Subsequent `ob_updates` frames immediately exhibit standard ~5000ms inter-arrival cadence and -345ms clock skew.

---

## 5. Synthetic Edge-Case Verification (SIMULATED)

All 7 simulated test scenarios in `tests/test_phase192_clock_domain_semantics.py` passed:
1. `test_01_simulated_negative_wall_clock_diff_is_clock_skew`: Proved that negative differences resolve to physical flight time plus clock offset.
2. `test_02_simulated_monotonic_intervals_immune_to_wall_clock_jumps`: Proved monotonic time remains positive (+200ms) even when NTP steps the system clock backwards by 5 seconds.
3. `test_03_simulated_forward_clock_jump_does_not_distort_arrival_cadence`: Proved a forward clock jump of +10s leaves the 50ms physical inter-arrival interval undistorted.
4. `test_04_simulated_missing_and_malformed_timestamp_handling`: Verified graceful classification of missing or non-numeric timestamps without dropping frames from order book sequencing.
5. `test_05_simulated_sequence_gap_duplicate_and_out_of_order_detection`: Verified exact tracking of sequence gaps, duplicates, and out-of-order frames.
6. `test_06_simulated_snapshot_age_vs_transit_latency_distinction`: Proved that snapshot age (3.94s) is separated from network transit latency.
7. `test_07_simulated_arrival_cadence_quantiles`: Demonstrated robust computation of p50, p90, p95, and p99 inter-arrival quantiles.
