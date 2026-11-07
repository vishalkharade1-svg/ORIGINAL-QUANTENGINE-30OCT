# QuantEngine Phase 180 — Historical Credential Incident Status Report

## Executive Summary

Phase 180 audited repository artifacts, release history, and local environment files regarding historical credential exposure, executed an authenticated read-only probe using testnet credentials provided in `.env`, and documented mandatory operator remediation steps.

> [!CAUTION]
> **CRITICAL SECURITY NOTICE:**  
> A passing current secret scan (`SECRET_SCAN_PASS`) demonstrates workspace hygiene but **DOES NOT** close the historical credential exposure incident.  
> Credentials present in earlier un-sanitized archives must be revoked and rotated in the exchange console by the account owner.

---

## 1. Incident Background & Scope

1. **Origin of Exposure:**
   - In historical revisions prior to Phase 132, non-empty Delta Exchange API credentials were present in `.env` and `env/.env.py`.
2. **Potentially Affected Artifacts:**
   - Pre-Phase-132 source archives and historical working trees containing active environment files.
3. **Workspace Sanitization Implemented:**
   - Active `.env` and `env/.env.py` files are strictly excluded from all release archives, git tracking, and packaging manifests.
   - Only `.env.example` (containing empty/blank templates with zero sensitive values) is packaged.
   - `scripts/security/scan_secrets.py` actively checks for any assignment patterns matching `DELTA_API_*`, `DELTA_INDIA_TESTNET_*`, private keys, and authorization tokens, failing closed if any credential is detected in tracked files.
   - Release archive packing (`scripts/build_release.py`) asserts zero `.env` or `env/` members.

---

## 2. Current Workspace Verification & Read-Only Probe

- **Automated Scanner:** `python scripts/security/scan_secrets.py --root .` $\implies$ **`SECRET_SCAN_PASS`**.
- **Packaging Integrity Test:** `tests/test_packaging_no_secrets_phase132.py` $\implies$ **`PASSED`**.
- **Manifest Audit:** Zero credentials, keys, or non-template environment files in `BUILD_MANIFEST.sha256`.
- **Archive Audit:** Zero `.env` files in `QuantEngine_PHASE178_RELEASE_CANDIDATE.zip` and candidate package.
- **Read-Only Testnet Probe Execution:**
  On 2026-10-20, an authenticated read-only probe was executed using the new testnet credentials in `.env` against `cdn-ind.testnet.deltaex.org`:
  - Verified account state: **0 open positions**, **0 open orders**, balance **$101.05 USD**.
  - Verified Product ID 84 multiplier: **0.001** (Vanilla Linear).
  - Confirmed zero orders were submitted, amended, or cancelled.

---

## 3. Mandatory Operator Remediation Protocol

Because local tooling cannot revoke keys or verify account safety on Delta Exchange, the account owner must execute the following protocol:

### Step 1: Revocation in Provider Console
1. Log into the Delta Exchange console (delta.exchange).
2. Navigate to **API Management**.
3. Identify all API keys created prior to Phase 158 or corresponding to the historical development period.
4. Immediately **REVOKE / DELETE** those API keys. Do not merely disable them.

### Step 2: Audit Exchange Access Logs
1. Inspect the API access history and IP audit logs for each revoked key in the console.
2. Review account order history, open positions, and balance settlements to confirm no unauthorized trading or withdrawal activity occurred.

### Step 3: Testnet Key Hygiene
1. For any testnet keys used in local development (such as those in `.env`):
   - Ensure withdrawal permissions are strictly disabled in the console.
   - Restrict permissions to read-only where possible.
   - Never commit `.env` or credential files to any shared repository or artifact package.
