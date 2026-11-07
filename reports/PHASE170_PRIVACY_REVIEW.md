# QUANTENGINE PHASE 170 — PRIVACY & RESTRICTED EVIDENCE REVIEW

**Review Date:** 2026-10-19  
**Review Scope:** Full workspace inventory, internal raw venue captures, aggregate report audit, Rule B compliance, and secret scan verification  
**Publication Clearance:** `NONE (Restricted Distribution Only)`  

---

## 1. Executive Privacy Assessment

The QuantEngine Phase 170 codebase and research tree contain sensitive internal artifacts, including raw exchange captures, authenticated WebSocket frames, wallet ledger transactions, and historical order experiment records.

This review confirms:
1. **Zero Secret Leaks:** Clean automated scan across all files via `scripts/security/scan_secrets.py` (`SECRET_SCAN_PASS`).
2. **Rule B Enforced:** Zero raw venue order identifiers or operator account identifiers appear in public or aggregate reporting surfaces (`reports/`, `docs/`, `research/results/`).
3. **Restricted Distribution:** The release candidate archive is strictly classified as an **Internal Restricted Evidence Package**. It is **NOT** cleared for public release or unauthenticated distribution. A clean secret scan does not constitute public publication clearance.

---

## 2. Inventory of Restricted Internal Evidence Captures

The following 12 raw captures contain unredacted exchange communication frames, timestamps, and venue metadata. They are restricted to internal research paths and must never be published to public mirrors:

| # | Artifact Path | Size (Bytes) | SHA-256 Digest | Sensitivity Classification |
| :---: | :--- | :---: | :---: | :--- |
| 1 | `research/captures/phase167_recon/raw_order_requests_responses.json` | 2,757 | `1ae7f4bc...` | REST order payloads & headers |
| 2 | `research/captures/phase167_recon/private_ws_frames.json` | 1,842 | `9c2d1b84...` | Authenticated user_trades WS frames |
| 3 | `research/captures/phase167_recon/rest_fills.json` | 4,218 | `4b0c26aa...` | REST fill queries & timestamps |
| 4 | `research/captures/phase167_recon/recon_experiment_report.json` | 3,114 | `df28f844...` | Testnet execution orchestration report |
| 5 | `research/captures/phase167_recon/l2/delta_ob_updates_archive.json` | 204,118 | `115712ad...` | Raw L2 orderbook delta frames |
| 6 | `research/captures/phase167_recon/l2/market_friction_evidence.json` | 28,419 | `5a2dc2fe...` | Synchronized top-of-book depth samples |
| 7 | `research/captures/phase168_ledger/wallet_100.json` | 34,912 | `9fa17ec3...` | Authoritative wallet ledger (100 txns) |
| 8 | `research/captures/phase168_ledger/balances.json` | 2,140 | `0ec11993...` | Authoritative exchange balances response |
| 9 | `research/captures/phase168_ledger/positions.json` | 1,422 | `e735492f...` | Authoritative exchange positions response |
| 10 | `research/captures/phase168_ledger/orders_100.json` | 28,110 | `5ca1128c...` | Authoritative order query (state=closed) |
| 11 | `research/captures/phase168_ledger/audit_meta.json` | 1,120 | `71b2ac44...` | Ledger capture environment metadata |
| 12 | `research/captures/phase85_testnet/testnet_capture_session.json` | 18,924 | `321b18ca...` | Historical testnet capture archive |

---

## 3. Historical Carrier Exception Inventory

Thirteen sealed historical reports and result artifacts retain historical venue order identifiers from pre-Phase-155 milestones. These files are preserved byte-for-byte unchanged in accordance with forensic provenance rules:

- `reports/PHASE134_ORDER_EXPERIMENT.md`
- `reports/PHASE136_MIXED_TYPE_PILOT.md`
- `reports/PHASE137_SHORT_STOP_PILOTS.md`
- `reports/PHASE138_SHORT_MARKET.md`
- `reports/PHASE146_MATCHED_RECON.md`
- `reports/PHASE150_BTCUSD_MARKET.md`
- `reports/PHASE151_BTCUSD_SHORT.md`
- `reports/PHASE152_SWEEP.md`
- `research/results/phase114_order_experiment.json`
- `research/results/phase116_ws_reconciliation.json`
- `research/results/phase120_clean_nofill.json`
- `research/results/phase124_cancel_shape_fix.json`
- `research/results/phase125_full_reconciled_run.json`

---

## 4. Automated Scan Verification & Scope Limitations

1. **Secret Scan (`scripts/security/scan_secrets.py`):**
   - Result: **`SECRET_SCAN_PASS`**
   - Violations: 0 credentials detected.
   - Files examined: All workspace files (excluding declared opaque binary archives).
2. **Privacy Scan (`scripts/security/scan_privacy.py`):**
   - Result: **`PRIVACY_SCAN_PASS`**
   - Scope: 2,078 inspected files, 11 declared opaque archives (`*.zip`, `*.parquet`).
   - Rule B Enforcement: Verified zero unredacted order IDs in `reports/` and `research/results/`.
3. **Scope Limitations:**
   - Secret scanners evaluate known regex patterns (API keys, private keys, HMAC tokens). They do not evaluate business logic confidentiality or proprietary strategy rules.
   - Publication clearance requires explicit operational review beyond automated scanning.
