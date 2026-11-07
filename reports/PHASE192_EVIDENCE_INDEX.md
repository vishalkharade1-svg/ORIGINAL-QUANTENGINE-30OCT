# QuantEngine Phase 192 — Cryptographic Evidence Index

## 1. Master Evidence Manifest

This document records the exact, byte-level cryptographic inventory of all source code changes, test suites, market-data capture files, summaries, and audit reports generated or validated under Phase 192.

| Category | File Path | Exact Bytes | SHA-256 Digest |
| :--- | :--- | :--- | :--- |
| **Core Hardening** | `core/execution/testnet_authorization_gate.py` | 40,567 | `d097b5bf355d02794b5f130e3e87886c4dbd1d8f9b5ac5728adbe0b9ddc37d36` |
| **Core Hardening** | `core/execution/testnet_state_reconciler.py` | 23,145 | `99084067d3f33ccd98f91ca9cb5b9aaaa3670dd2761aae1e624c45ecb8068c30` |
| **Script Guard** | `scripts/funding_settlement_hold.py` | 9,222 | `baa41f5c52b79fb4b74c51095b808a6a5b7d597068c2b6c180838a64c0aa052e` |
| **Script Guard** | `scripts/bounded_testnet_order_experiment.py` | 15,508 | `89b0fab6daad34c049741902b20bbef95e03a54f37893064c7f4f68e57861a20` |
| **Script Guard** | `scripts/bounded_testnet_reconciled_experiment.py` | 19,219 | `246cea8ddbbca8f3f58a0dda6ebc9c9720b6b75f950fae449c966881060cd256` |
| **Test Suite** | `tests/test_phase192_multiprocess_ledger.py` | 16,683 | `327fbd5bc275aaa7a535d0a87a29deb69dc82e93dd3ef18442d58ff9c6c60424` |
| **Test Suite** | `tests/test_phase192_lifecycle_transitions.py` | 15,081 | `251cecd8049111486c2c8569231c0f833270be497a8c1b7e3ed2fffb7e6f7842` |
| **Test Suite** | `tests/test_phase192_reconciliation_adversarial.py` | 15,904 | `8a6a46eb5079ae323a0a95b06a539eff1a17488c5926b7b008da1ca01d8113d6` |
| **Test Suite** | `tests/test_phase192_clock_domain_semantics.py` | 7,310 | `688d80158f1cfc842ffc59a8cb071039ddf6727c864789273657d9032606e68a` |
| **Market Data** | `research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl` | 237,803 | `fb5835589028693bd6a8bfcf1b72d6515c622e91804d4c41d37acc027279076d` |
| **Market Data** | `research/captures/phase191_l2/raw_l2_capture_20261021T073820Z.jsonl` | 118,802 | `464430627e6fc38835bbe2f7d9dcebe6c120e0cb2bfa746416fe1a866e28d1aa` |
| **Market Data** | `research/captures/phase192_l2/raw_l2_capture_20261021T085017Z.jsonl` | 83,636 | `bc3ea0f233c89010c08f81afa324bf433975f71cb7d66915cd307d11a4ca9c2e` |
| **Capture Summary** | `research/captures/phase192_l2/l2_quality_summary_20261021T085017Z.json` | 4,922 | `cd65afa9c82c92d189813d11ea9a3ad6b7918b4602b53c43e4c4c05ba9d663dc` |
| **Report** | `reports/PHASE192_INDEPENDENT_AUDIT_REPORT.md` | 7,533 | `b87dca6277e1450b28572ae351abf8f52f7de6da1b0b0c67c1dfca5ad799de64` |
| **Report** | `reports/PHASE192_WRITE_PATH_SAFETY_INVENTORY.md` | 5,648 | `8e3beb2f457694c60e921caa24c994f149d1be92548f65e6e9cb52777e2328be` |
| **Report** | `reports/PHASE192_LEDGER_FAULT_INJECTION_REPORT.md` | 7,148 | `679273d72d6d3a118f43a2fde8a6d70495e38f40a8c55385e80d9782705242f8` |
| **Report** | `reports/PHASE192_CRASH_CONSISTENCY_LIFECYCLE_REPORT.md` | 7,680 | `d670a1462ea0c74eb9b5592601fb9c4b8ec57e0c764501a761224e91f5892aa1` |
| **Report** | `reports/PHASE192_RECONCILIATION_STRESS_REPORT.md` | 6,531 | `338185795256054f4028a40c0579ac6be1613408461e18633a8b73d90b937936` |
| **Report** | `reports/PHASE192_CLOCK_DOMAIN_LATENCY_REPORT.md` | 6,262 | `5c14c7f468a9b465dfc2f9561f7a3ecc28b8f40d2e68dfc9376b98dfd5d11a7c` |
| **Report** | `reports/PHASE192_BLOCKER_STATUS_AND_BURNDOWN.md` | 6,023 | `fe8997e8bcec767173990f3d511059650a2197fad204ba487077090f4255d1a4` |

---

## 2. Integrity Verification Procedure

To verify all artifacts against this index:

```bash
python scripts/generate_manifest.py --verify
```

A passing exit code (0) confirms that every single regular file in the release package matches its recorded cryptographic fingerprint with zero byte drift.
