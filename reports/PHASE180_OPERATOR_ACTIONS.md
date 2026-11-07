# QUANTENGINE PHASE 180 — OPERATOR ACTION PLAN & GOVERNANCE PROTOCOL

**Document Date**: 2026-10-20  
**Phase**: 180  
**Auditor**: Independent Quant-Engineering Auditor & Release-Integrity Specialist  
**Mandatory Posture**: `NOT_PRODUCTION_READY` | `EDGE NOT ESTABLISHED`  

---

## 1. Overview

This document specifies the mandatory manual operator actions, governance approvals, security incident closures, and external evidence captures required before QuantEngine can progress beyond its current `NOT_PRODUCTION_READY` posture.

Automated auditing and local source verification cannot replace operator authorization, authenticated exchange receipts, or third-party cryptographic recertification.

---

## 2. Operator Action Checklist

| ID | Action Area | Action Item | Required Evidence | Status |
|---|---|---|---|---|
| **OP-180-01** | **API Security** | Historical Key Revocation & Audit | Delta Exchange console access log review; revocation of pre-Phase-158 keys | `MANDATORY_OPEN` |
| **OP-180-02** | **Testnet Keys** | Testnet Key Hygiene & Expiration | Rotate newly provided `.env` testnet keys after audit; restrict permissions to read-only | `RECOMMENDED` |
| **OP-180-03** | **Strategy Baseline** | Strategy Identity Recertification (BLOCK-180-01) | Formal sign-off choosing either branch restoration or authorized baseline re-pinning | `MANDATORY_OPEN` |
| **OP-180-04** | **Repository** | Git Ancestry Reconnection (BLOCK-180-02) | Run tests against central repository clone with complete historical git commit graph | `ENVIRONMENT_OPEN` |
| **OP-180-05** | **Third-Party** | External Quant Audit (BLOCK-180-03) | Formal independent review by detached vendor using detached prompt | `MANDATORY_OPEN` |
| **OP-180-06** | **Trade Evidence** | ADAUSD Closure Receipt (BLOCK-180-04) | Raw authenticated order/fill JSON payload proving legacy account is flat | `EVIDENCE_OPEN` |
| **OP-180-07** | **Funding Evidence**| Raw Funding Transaction (BLOCK-180-05) | Raw authenticated exchange funding debit JSON payload from 8h settlement | `EVIDENCE_OPEN` |
| **OP-180-08** | **WebSocket Recon**| WebSocket Fill Certification (BLOCK-180-06) | Controlled testnet capture yielding 100% matched trade IDs without windowing | `EVIDENCE_OPEN` |
| **OP-180-09** | **Statutory Tax** | GST Invoice & Tax Reconciliation (BLOCK-180-09)| Official Delta Exchange India monthly tax invoice and fee ledger reconciliation | `COMPLIANCE_OPEN` |

---

## 3. Protocol Details

### 3.1 Security Incident Closure Protocol (OP-180-01 & OP-180-02)
- **Background**:
  Historical archives prior to Phase 158 contained un-sanitized credential files. While current release candidates and workspace scanners confirm `SECRET_SCAN_PASS` and exclusion of `.env` files, historical archives remain distributed across archival storage.
- **Operator Execution Steps**:
  1. Log into the Delta Exchange India management console.
  2. Navigate to **API Keys Management**.
  3. Locate any API key pairs generated prior to Phase 158.
  4. Review IP address access logs for any unauthorized API invocations.
  5. Permanently revoke the historical key pairs.
  6. Confirm that the current testnet key pair provided in `.env` has only read and testnet permissions, and has withdrawal permissions strictly disabled.
  7. Provide a signed attestation confirming revocation without pasting secret strings.

### 3.2 Strategy Baseline Approval Protocol (OP-180-03)
- **Background**:
  5 historical change-detector tests assert the Phase 14 Windows CRLF digest (`c52e648ca24f...`) across 9 strategy files. Post-Phase-4 gate-80 fixes altered file bytes. The provenance is understood (`PROVENANCE_EXPLAINED`), but the baseline is not approved (`BASELINE_APPROVED = FALSE`).
- **Options for Operator**:
  - **Option A (Archival Branch Restoration)**: Check out the pristine historical commit branch corresponding to Phase 14 if historical byte regression testing is strictly demanded.
  - **Option B (Authorized Baseline Recertification)**: Issue a formal governance approval recertifying the post-Phase-4 corrected strategy files as the new canonical baseline, and update the 5 tests with versioned baseline metadata.
  *Note: Per Safety Rule #7, the auditor will not update these pins without formal operator approval.*

### 3.3 Exchange Evidence Capture Protocols (OP-180-06 & OP-180-07)
- **ADAUSD Position Closure**:
  Export the raw authenticated REST order and fill history for the historical ADAUSD trade from the exchange portal. Archive the resulting JSON payload into `evidence/exchange_captures/` with a detached SHA-256 checksum.
- **Funding Settlement Debit**:
  During a scheduled 8-hour funding settlement window (00:00, 08:00, or 16:00 UTC), execute a read-only wallet transaction history export. Archive the raw JSON showing the exact funding fee debit amount and associated funding rate.

---

## 4. Current Read-Only Testnet Account Verification

On 2026-10-20, an authenticated read-only probe was executed against Delta Exchange India Testnet (`cdn-ind.testnet.deltaex.org`) using credentials from `.env`:
- **Account Status**:
  - Cash Balance: **$101.04689806 USD**
  - Open Positions: **0** (Account completely flat)
  - Open Orders: **0** (No active resting orders)
- **Product ID 84 Parameters**:
  - Multiplier: **0.001** (Vanilla Linear)
  - Tick Size: **0.10**
- **Safety Compliance**:
  - Zero orders placed, amended, or cancelled.
  - Testnet credentials verified functioning for read-only metadata verification.
  - Release packaging scripts automatically exclude `.env` to prevent credential leakage.

---

## 5. Summary

QuantEngine remains in `NOT_PRODUCTION_READY` posture. No live or testnet trading is permitted until the operator completes the required action items and resolves standing blockers `BLOCK-180-01` through `BLOCK-180-09`.
