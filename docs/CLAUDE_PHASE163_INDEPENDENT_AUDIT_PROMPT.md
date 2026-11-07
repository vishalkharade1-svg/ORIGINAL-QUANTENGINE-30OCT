# Independent Adversarial Audit Prompt — QuantEngine Phase 163

You are an independent, adversarial quantitative software and security auditor.
Your mission is to perform an exhaustive, evidence-based verification of `QuantEngine_PHASE163_RELEASE_CANDIDATE.zip` and its companion deliverables:

- `RELEASE_HASH_PHASE163.txt` — detached hash record (archive SHA-256, member count, and byte count).
- `QuantEngine_PHASE163_POST_BUILD/` — post-build bundle containing the final worktree and extracted package test logs and verification records.

Do not accept any claim made in `README.md`, `STATUS.md`, `IMPLEMENTATION_STATE.md`, `NEXT_ACTIONS.md`, or `reports/PHASE163_*` without reproducing it independently. Fix nothing; report only.

Extract the candidate ZIP into a fresh, clean workspace before beginning.

---

## The 16 Mandatory Independent Verification Items

### 1. Archive Identity, Detached Record, and Non-Circularity
- Compute `sha256sum QuantEngine_PHASE163_RELEASE_CANDIDATE.zip`.
- Verify it matches `RELEASE_HASH_PHASE163.txt` byte-for-byte.
- Confirm the member count and byte count match.
- **Non-Circularity Test**: Search every extracted file inside the package for the archive's literal SHA-256. Report any instance of the archive hash embedded inside its own member files as a **CRITICAL** defect.

### 2. Manifest Determinism and Stdout Robustness
- Run: `python scripts/generate_manifest.py --root . > /tmp/regen_manifest`
- Compare bytes: `diff -u BUILD_MANIFEST.sha256 /tmp/regen_manifest`. It must match byte-for-byte.
- Run: `python scripts/generate_manifest.py --verify`. Must output `MANIFEST_PASS (0 problems)`.
- Run: `pytest tests/test_phase158_manifest_contract.py -v`. All tests must pass.

### 3. File Inventory and Archive Isolation
- Run: `pytest tests/test_archive_isolation.py -v`.
- Confirm that exactly ZERO active modules across `core/`, `data/`, `config/`, `backtesting/`, `risk/`, `main.py`, `scripts/`, and `tests/` import from `_archive/`.

### 4. Strategy Identity and Deliberate Change Detectors
- Run: `pytest tests/test_oos_data_extension_19.py tests/test_oos_feasibility_17.py tests/test_oos_validation_18.py tests/test_readiness_16.py -v`
- Confirm: Exactly 5 tests fail.
- Check the failure messages: all 5 must assert expected hash `c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6`.
- Confirm `scripts/recertify_strategy_digest.py --json` reports `status: "BLOCKED"` (`BLOCK-163-01`).
- **Audit Requirement**: If any agent or build has modified these 5 tests or re-pinned the digest to make them green, report as **CRITICAL FALSIFICATION**.

### 5. Git-Evidence Honesty (The 40 Gated Facts)
- Confirm the extracted tree has no `.git` directory.
- Confirm `tests/evidence_mode.py` detects `SOURCE_ARCHIVE` mode.
- Confirm all 40 Git-dependent facts are raised as `SkipTest` with `BLOCKED_EVIDENCE` reasons (`BLOCK-163-02`), and not passed vacuously.
- Run: `pytest tests/test_git_evidence_mode_contract.py -v`. Must pass 100%.

### 6. Security & Secret Scanner Verification
- Run: `python scripts/security/scan_secrets.py`.
- Must output `SECRET_SCAN_PASS (0 violations)`.
- Confirm that `.env`, `.env.test`, `.env.local`, and `env/.env.py` do not exist in the package.
- Confirm zero live or testnet API keys are embedded in source or markdown prose.

### 7. Privacy Scanner & Restricted Package Classification
- Run: `python scripts/security/scan_privacy.py`.
- Must output `PRIVACY_SCAN_PASS (0 violations)`.
- Confirm `publication_clearance: "NOT_CLEARED"`. Verify that only the 8 enumerated raw restricted captures contain account IDs.

### 8. Multi-Stream Multiplexer Verification (Phase 163 Core)
- Inspect `core/runtime/multi_stream_multiplexer.py`.
- Run: `pytest tests/test_multi_stream_multiplexer_phase163.py -v`.
- Verify:
  - Strict fail-closed rejection of `is_final=False` candles (`UnfinalizedCandleError`).
  - Monotonic timestamp gap detection (`CandleGapError`).
  - Strict cross-symbol state isolation (independent ring buffers).
  - Thread safety under concurrent multi-producer execution.

### 9. Protective Bracket Orders & Trailing Latency Simulation (Phase 163 Core)
- Inspect `core/execution/protective_bracket.py`.
- Run: `pytest tests/test_protective_bracket_phase163.py -v`.
- Verify:
  - Mandatory Stop Loss requirement (`MissingStopLossError`).
  - Inverted bracket geometry rejection (`InvalidBracketGeometryError`).
  - R:R bounds enforcement ($1.0R \le \text{R:R} \le 20.0R$).
  - Realistic trailing stop execution slippage simulation under latency delay.

### 10. Mobile Push Telemetry Gateway Verification (Phase 163 Core)
- Inspect `core/monitoring/mobile_push_gateway.py`.
- Run: `pytest tests/test_mobile_push_gateway_phase163.py -v`.
- Verify:
  - Bearer-token authentication on subscription and dispatch (`AuthenticationError`).
  - Automated regex scrubbing of credentials and secrets from event payloads.
  - Bounded non-blocking queues with `drop_oldest` policy on subscriber backpressure.
  - Explicit provenance tagging (`OBSERVED`, `PAPER_MODELLED`).

### 11. Historical Record Immutability
- Verify that historical records from Phase 161 and Phase 162 are preserved byte-for-byte:
  - `reports/PHASE161_RELEASE_GATES.json` (SHA-256: `d1e0663b35455c3b5fae9b1bd13fbc37e5ba27b2e4d5e3f5a6fb888bc6abd898`)
  - `reports/PHASE161_ENVIRONMENT.json` (SHA-256: `ae9671c03ac166596df9da0c9be6e89e56e5d4e269e68c3eeb489fc1f2fa0251`)
  - `reports/PHASE162_RELEASE_GATES.json` (SHA-256: `f94aff1f1723c37527975850b733257d0ca26443dbcf81672f7429bd65a668b2`)
  - `reports/PHASE162_BLOCKERS.json` (SHA-256: `5d053de948f7e0a07eae1b24022d2f4cd7d03f7ca92d819b79bd2aceff0fc626`)
- Run: `pytest tests/test_release_records_phase163.py -v`. Must pass 100%.

### 12. Carried External Blockers Ledger
- Inspect `reports/PHASE163_BLOCKERS.json`.
- Confirm all 6 blockers are explicitly listed as open/unverifiable:
  - `BLOCK-163-01`: Strategy digest re-certification.
  - `BLOCK-163-02`: Git ancestry facts.
  - `BLOCK-163-03`: Independent audit requirement.
  - `BLOCK-163-04`: Old-account ADAUSD position closure.
  - `BLOCK-163-05`: Funding settlement cashflow debit payload.
  - `BLOCK-163-06`: Repeat-match WebSocket fill certification.
- Confirm zero blockers have been fraudulently marked closed.

### 13. Production Readiness and Edge Claims
- Check `reports/PHASE163_RELEASE_GATES.json`:
  - `overall`: Must be `NOT_PRODUCTION_READY`.
  - `edge_status`: Must be `EDGE NOT ESTABLISHED`.
- Any claim of "Production Ready" or "Profitable Edge Established" is an immediate critical audit failure.

### 14. Full Suite Authoritative Reproduction
- Run `pytest`.
- Confirm exactly 4,083 passed, 5 failed, 57 skipped.
- Confirm failure count equals 5 and consists solely of the strategy change detectors.

---

## Auditor Report Format
Your final report must state:
1. Exact SHA-256 of the audited zip archive.
2. Status of all 16 items above (PASS / FAIL / BLOCKED).
3. Final Verdict: Must agree with `NOT_PRODUCTION_READY` and `EDGE NOT ESTABLISHED`.
