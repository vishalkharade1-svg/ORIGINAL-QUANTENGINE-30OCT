# QUANTENGINE PHASE 181 — AUDIT FINDINGS

**Phase**: 181  
**Status**: NOT_PRODUCTION_READY | EDGE NOT ESTABLISHED  
**Date**: 2026-10-20  

---

## Finding 181-01: Historical Source-Change Discrepancy Forensic Resolution
- **Severity**: MEDIUM (Documentation & Provenance Integrity)
- **Status**: `VERIFIED` & `RESOLVED`
- **Description**: The Phase 180 report section 2.2 correctly enumerated 4 modified files in the Phase 178 → Phase 179 archive diff (`BUILD_MANIFEST.sha256`, `NEXT_ACTIONS.md`, `post_cost_backtester.py`, `queue_aware_paper_engine.py`), but in narrative discussion referred to multiplier precedence changes in `core/execution/maker_execution_model.py`.
- **Forensic Verification**: Direct byte-by-byte SHA-256 analysis of the member files across all three release archives established that `core/execution/maker_execution_model.py` was byte-identical between Phase 178 and Phase 179 (`6fa0ce6...`). It was modified solely during Phase 180 (`9bd9b0f...`).
- **Remediation**: The discrepancy is explicitly resolved and documented in `reports/PHASE181_AUDIT_REPORT.md`.

---

## Finding 181-02: Ambiguous Multiplier Sentinel Vulnerability
- **Severity**: HIGH (Calculation Integrity & Risk Boundary)
- **Status**: `IMPLEMENTED` & `VERIFIED`
- **Description**: Prior to Phase 181, `audit_and_recalculate_stop_risk` used `Decimal("1.0")` as a sentinel indicating that an explicit multiplier was omitted by the caller:
  `if meta is not None and contract_multiplier == Decimal("1.0"): contract_multiplier = meta.contract_multiplier`
  This created ambiguity because a caller could legitimately intend to pass an explicit multiplier of `1.0` for a unit-multiplier derivative or synthetic test fixture. In that case, the caller's explicit multiplier would be silently replaced by metadata. Conversely, if metadata was absent, an accidental default `1.0` was permitted without validation.
- **Remediation**: The API was hardened by introducing `None` as the explicit omission sentinel. When `contract_multiplier is None`, metadata is queried. When an explicit multiplier is supplied, it is validated against metadata; any discrepancy triggers an immediate fail-closed `Metadata conflict` rejection. When both metadata and multiplier are omitted, the function fails closed (`Missing contract multiplier`). Non-positive and non-finite multipliers are strictly rejected.

---

## Finding 181-03: Workspace Secret Hygiene Enforcement
- **Severity**: HIGH (Operational Security & Packaging Hygiene)
- **Status**: `VERIFIED` & `REMEDIATED`
- **Description**: A local `.env` file was present in the development root during early Phase 181 execution, causing `test_packaging_no_secrets_phase132.py` and `test_secret_scan_phase0.py` to fail.
- **Remediation**: The file was purged from the release candidate worktree root. Automated scans confirm 0 credential-bearing paths and 0 secret patterns in the worktree. `.gitignore` and `scripts/generate_manifest.py` exclusions guarantee that local credentials cannot enter release candidates.

---

## Finding 181-04: Rejection State Disambiguation
- **Severity**: LOW (Diagnostic Precision)
- **Status**: `VERIFIED`
- **Description**: In `QueueAwarePaperExecutionEngine`, both friction hurdle rejections and stop-risk budget rejections set `order.state = PaperOrderState.REJECTED_RISK` for contract compatibility.
- **Remediation**: Rejection reasons and underlying audit records were confirmed distinct. Hurdle failures populate `order.hurdle_verdict` with `allowed=False` and a `"Friction hurdle failed"` explanation, while stop-risk budget failures halt before hurdle evaluation and record `"Normalized stop risk ... exceeds risk budget"`.
