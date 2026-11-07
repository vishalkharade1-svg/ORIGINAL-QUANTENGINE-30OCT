# Independent Adversarial Audit Prompt — QuantEngine Phase 162

You are an independent, adversarial quantitative software and security auditor.
Your mission is to perform an exhaustive, evidence-based verification of `QuantEngine_PHASE162_RELEASE_CANDIDATE.zip` and its companion deliverables:

- `RELEASE_HASH_PHASE162.txt` — detached hash record (archive SHA-256, member count, and byte count).
- `QuantEngine_PHASE162_POST_BUILD/` — post-build bundle containing the final worktree and extracted package test logs and verification records.

Do not accept any claim made in `README.md`, `STATUS.md`, `IMPLEMENTATION_STATE.md`, `NEXT_ACTIONS.md`, or `reports/PHASE162_*` without reproducing it independently. Fix nothing; report only.

Extract the candidate ZIP into a fresh, clean workspace before beginning.

---

## The 14 Mandatory Independent Verification Items

### 1. Archive Identity, Detached Record, and Non-Circularity
- Compute `sha256sum QuantEngine_PHASE162_RELEASE_CANDIDATE.zip`.
- Verify it matches `RELEASE_HASH_PHASE162.txt` byte-for-byte.
- Confirm the member count and byte count match.
- **Non-Circularity Test**: Search every extracted file inside the package for the archive's literal SHA-256. Report any instance of the archive hash embedded inside its own member files as a **CRITICAL** defect.

### 2. Manifest Determinism and Stdout Robustness
- Run: `python scripts/generate_manifest.py --root . > /tmp/regen_manifest`
- Compare bytes: `diff -u BUILD_MANIFEST.sha256 /tmp/regen_manifest`. It must match byte-for-byte.
- Run: `python scripts/generate_manifest.py --verify`. Must output `MANIFEST_PASS (0 problems)`.
- Verify Phase 7 defect repair: `scripts/generate_manifest.py` must use chunked buffer writing handling `BlockingIOError` on non-blocking pipes (`_write_buffer_robust`).
- Run: `pytest tests/test_phase158_manifest_contract.py -v`. All 17 tests must pass.

### 3. File Inventory and Dead Code Triage
- Inspect `reports/PHASE162_FILE_INVENTORY.json` and `reports/PHASE162_DEAD_FILE_TRIAGE.json`.
- Verify every file in the package is accounted for.
- Verify the 76 entries under `_archive/`:
  - Run: `pytest tests/test_archive_isolation.py -v`.
  - Confirm that exactly ZERO active modules across `core/`, `data/`, `config/`, `backtesting/`, `risk/`, `main.py`, `scripts/`, and `tests/` import from `_archive/`.
- Verify the 13 duplicate groups (61 files): confirm they are immutable research artifacts or package markers, not shadow production code.
- Verify the 7 root working notes are preserved for provenance.

### 4. Strategy Identity and Deliberate Change Detectors
- Run: `pytest tests/test_oos_data_extension_19.py tests/test_oos_feasibility_17.py tests/test_oos_validation_18.py tests/test_readiness_16.py -v`
- Confirm: Exactly 5 tests fail.
- Check the failure messages: all 5 must assert expected hash `c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6`.
- Confirm `scripts/recertify_strategy_digest.py --json` reports `status: "BLOCKED"` (`BLOCK-162-01`).
- **Audit Requirement**: If any agent or build has modified these 5 tests or re-pinned the digest to make them green, report as **CRITICAL FALSIFICATION**.

### 5. Git-Evidence Honesty (The 40 Gated Facts)
- Confirm the extracted tree has no `.git` directory.
- Confirm `tests/evidence_mode.py` detects `SOURCE_ARCHIVE` mode.
- Confirm all 40 Git-dependent facts are raised as `SkipTest` with `BLOCKED_EVIDENCE` reasons (`BLOCK-162-02`), and not passed vacuously.
- Run: `pytest tests/test_git_evidence_mode_contract.py -v`. Must pass 100%.

### 6. Security & Secret Scanner Verification
- Run: `python scripts/security/scan_secrets.py`.
- Must output `SECRET_SCAN_PASS (0 violations)`.
- Confirm that `.env`, `.env.test`, `.env.local`, and `env/.env.py` do not exist in the package.
- Confirm zero live or testnet API keys are embedded in source or markdown prose.

### 7. Privacy Scanner & Restricted Package Classification
- Run: `python scripts/security/scan_privacy.py`.
- Must output `PRIVACY_SCAN_PASS (0 violations)`.
- Check publication clearance: must be `publication_clearance: NOT_CLEARED`.
- Verify that restricted operational data (account IDs, venue order IDs) is confined strictly to the 8 enumerated paths in `RESTRICTED_EVIDENCE_PATHS`.
- Confirm that prose in `reports/` and `docs/` contains zero literal operational account numbers or numeric venue order IDs.

### 8. Dependency Environment Verification
- Inspect `requirements.txt`, `reports/PHASE162_ENVIRONMENT.json`, and `reports/PHASE162_DEPENDENCY_REVIEW.md`.
- Verify pinned versions: `python-dotenv==1.2.2`, `pyarrow==23.0.1`, `pytest==9.0.3`.
- Inspect `reports/PHASE162_OSV_SCAN.json`: confirm 0 open advisories against the pinned runtime.
- Run: `pytest tests/test_dependency_pin_contract.py -v`. Must pass 100%.

### 9. Empirical Funding Reconciliation (Candidate A)
- Inspect `reports/PHASE162_CAPTURE_REPORT.md` and `research/captures/phase148_funding/hold_log.jsonl`.
- Verify 1-contract ETHUSD perpetual held through 16:00 UTC settlement window.
- Verify entry/exit prices (2372.00 / 2371.10) and flat end state in `hold_log.jsonl`.
- **Audit Limitation Check**: Confirm `hold_log.jsonl` contains `funding_rate_pre/post: "None"` and lacks the raw debit transaction payload. Confirm that the debit calculation is derived in prose and the blocker is carried as `UNVERIFIABLE_EXTERNAL` (`BLOCK-162-05`).

### 10. Empirical WebSocket Fill Reconciliation (Candidate B)
- Inspect `reports/PHASE162_CAPTURE_REPORT.md` and `research/captures/phase162_recon/`.
- Verify 2-leg BTCUSD sequence with authenticated private WS `user_trades` and concurrent L2 book logging (92 snapshots).
- Verify windowed reconciliation achieved `MATCHED_WINDOWED` (2/2 in-window fills matched @ 81082.5 buy / 81078.5 sell).
- **Audit Limitation Check**: Confirm `MATCHED_WINDOWED` does not satisfy full `MATCHED` certification under `execution_economics_certification.py:164`, 12 pre-window fills had `module_error` / `NO_ALIGNED_SAMPLE`, and sequences are null. Confirm carried as `BLOCK-162-06`.

### 11. Architecture, Risk, and Protective Orders
- Inspect `core/monitoring/api_server.py`: confirm GET read routes and hard-allowlisted POST `/control` verbs (`start`, `stop`, `restart`, `emergency_stop`, `pause`, `resume`). Confirm zero order submission routes.
- Inspect `core/risk/trading_policy.py`: confirm risk-reward boundaries are bounded between 1.0R and 20.0R. Confirm no hidden 6R floor exists.
- Confirm all order intents enforce mandatory Stop Loss protection (fail-closed bracket orders).

### 12. Full Test Suite Reproduction
- Run: `python -m pytest -q -p no:cacheprovider --tb=short -rfs`
- Expectation:
  - Total collected: 4,127
  - Passed: 4,065
  - Subtests passed: 399
  - Failed: Exactly 5 (the strategy change detectors)
  - Skipped: Exactly 57 (40 Git facts + 17 external/env)
  - Exit code: 1

### 13. Documentation Reconciliation
- Read `reports/PHASE162_DOCUMENTATION_RECONCILIATION.md`.
- Verify that the 7 core status questions are answered factually without obfuscation or inflated claims.

### 14. Final Gate Matrix and Production Verdict
- Review `reports/PHASE162_RELEASE_GATES.json` and `reports/PHASE162_BLOCKERS.json`.
- Verify all 6 carried blockers:
  - `BLOCK-162-01` (strategy digest re-certification)
  - `BLOCK-162-02` (40 Git ancestry evidence facts)
  - `BLOCK-162-03` (vendor independent audit)
  - `BLOCK-162-04` (old-account ADAUSD position)
  - `BLOCK-162-05` (funding-through-settlement debit payload)
  - `BLOCK-162-06` (repeat-match WebSocket fill certification)
- Overall verdict must be explicitly: **`NOT_PRODUCTION_READY`**. Edge status must be: **`EDGE NOT ESTABLISHED`** (`FIND-162-01`).
- Trading edge must be explicitly: **`EDGE NOT ESTABLISHED`**.
- Live execution must remain: **`DISABLED`**.
