# QuantEngine Release-Candidate Repair Audit — Phase 193B Continuation

**Audit basis:** uploaded `QuantEngine_PHASE161_RELEASE_CANDIDATE 2.zip`  
**Repository HEAD at extraction:** `ffefa14a8729f6d2160db3735a06257cbb6ab48b`  
**Operating posture:** `NOT_PRODUCTION_READY`  
**Strategy status:** `EDGE NOT ESTABLISHED`  
**Release gate:** `HOLD`  
**Exchange order writes performed by this audit:** `0`

## Executive result

The ZIP is not the Phase 31 snapshot described in the accompanying conversation. It contains later Phase 192–193B execution-safety and forensic work. The audit reproduced several concrete archive and test issues, repaired the local working copy, and verified a targeted regression set. This is not a production-readiness certification.

## 1. Security and archive boundary

- The uploaded ZIP contains a root `.env` member. It was deliberately **not extracted or read** during this audit.
- The Git history contains four commits that the repository's secret scanner identifies as containing non-empty `.env` credential assignments. The history check failed closed and printed only file paths, commit IDs, and rule names—not credential values.
- The extracted audit working copy excludes `.env`. Therefore `SECRET_SCAN_PASS` on that working copy is **not evidence that the original ZIP is secret-free**.
- A CI workflow was restored and strengthened to run worktree, staged-blob, and history scans. The history scan is expected to fail until the credential-bearing history is remediated through a coordinated owner-controlled procedure.
- The final distribution archive is sanitized: it excludes `.env`, `.git`, virtual environments, and cache directories. No exchange API credentials are included.
- No credentials were used, copied into reports, or sent to an exchange. No exchange reads or writes were performed.

## 2. Archive / Git state

At extraction, Git reported `main...origin/main [ahead 18]`, HEAD `ffefa14a8729f6d2160db3735a06257cbb6ab48b`, and a heavily modified working tree (1,567 porcelain status entries: 1,251 modified tracked files, one deleted tracked file, and 315 untracked entries). This is not a clean checkout. The audit did not reset, clean, rebase, or discard that work.

The archive omitted two files covered by `BUILD_MANIFEST.sha256`:
- `.github/workflows/secret-scan.yml`
- `.vscode/mcp.json`

The workflow was restored with fail-closed secret scanning. The MCP configuration was reconstructed from the preserved Phase 155 operator-provided configuration record; because the original bytes were absent from the ZIP and the reconstructed bytes did not match the prior recorded digest, this is a **semantic reconstruction, not a byte-exact recovery**. The manifest was regenerated for the repaired working copy and independently verified.

## 3. Full-suite collection defect repaired

`tests/test_stage123_operational.py` contained a module-level assertion using `self`, causing `NameError: name 'self' is not defined` during full-suite collection. The test also omitted the active RR bound fields from its configuration fingerprint.

Repair:
- moved the maximum-RR assertion into `TestDeterminism.test_config_fingerprint_stable`;
- added `TRADING_MIN_RISK_REWARD` and `TRADING_MAX_RISK_REWARD` to the fingerprint inputs;
- retained the active bounds assertions (`1.0` and `20.0`);
- kept the legacy `MIN_RISK_REWARD=6.0` explicitly identified as provenance-only.

The focused module now passes. No risk policy or runtime trading behavior was changed by this repair.

## 4. Independent capture reconciliation

The actual capture files were rehashed and parsed from disk:

| Capture | Bytes | SHA-256 | Frames | Symbols | Per-symbol sequence gaps |
|---|---:|---|---:|---|---:|
| Phase 190 `raw_l2_capture_20261021T064426Z.jsonl` | 237,803 | `fb5835589028693bd6a8bfcf1b72d6515c622e91804d4c41d37acc027279076d` | 246 | BTCUSD 209; ETHUSD 37 | 0 |
| Phase 191 `raw_l2_capture_20261021T073820Z.jsonl` | 118,802 | `464430627e6fc38835bbe2f7d9dcebe6c120e0cb2bfa746416fe1a866e28d1aa` | 104 | BTCUSD 91; ETHUSD 13 | 0 |
| Actual Phase 192 `raw_l2_capture_20261021T085017Z.jsonl` | 83,636 | `bc3ea0f233c89010c08f81afa324bf433975f71cb7d66915cd307d11a4ca9c2e` | 53 | BTCUSD 48; ETHUSD 5 | 0 |
| **Actual total** | **440,241** | — | **403** | — | **0 within each symbol/session** |

The Phase 193A corpus report's claimed Phase 192 artifact `raw_l2_capture_20261021T091410Z.jsonl` (121,682 bytes, digest prefix `c7bf98c5…`, 104 frames) is absent from the repository. The reported 478,287-byte / 454-frame aggregate therefore does not describe the files at rest. The actual third capture is the 83,636-byte file listed above. Existing forensic artifact `EVIDENCE/PHASE19X_FORENSIC/PHASE4_CAPTURE_RECONCILIATION.md` documents the same discrepancy; this audit independently reproduced the hashes and counts.

Receipt monotonic timestamps are non-decreasing but not strictly increasing in every adjacent line: equal values occur across different symbols at the available clock resolution. No decreasing timestamp was found. This does not change the per-symbol sequence-gap result, but the phrase “strictly increasing receipt timestamps” is too strong for these files.

## 5. Verification executed

Environment: Python 3.13.5, pytest 9.0.2 in the provided runtime; the repository's documented release environment is Python 3.12 with pinned dependencies.

| Command / scope | Result |
|---|---|
| `pytest` Phase 189–193B tests plus MCP safety tests | **171 passed**, 9 subtests passed |
| Secret-scanner, packaging, dependency-pin tests | **29 passed**, 18 subtests passed |
| `pytest tests/test_stage123_operational.py` | **52 passed** |
| RR / trailing-stop policy regression tests (6 modules) | **48 passed** |
| `pytest tests/ --collect-only -q` | **4,864 tests collected** |
| `scripts/security/scan_secrets.py` on extracted sanitized working copy | `SECRET_SCAN_PASS` (does not cover the omitted original `.env`) |
| `scripts/security/scan_secrets.py --check-history` | **FAIL** — four credential-bearing `.env` commits detected, values redacted |
| `scripts/generate_manifest.py --root . --verify` after repairs | **`MANIFEST_PASS (0 problems)`**, 2,479 entries |
| Full `pytest tests/` | **NOT COMPLETED** — after fixing the collection error, the run exceeded the execution environment's 60-second foreground limit and was interrupted early. It is not reported as passing. |

Python startup emitted a spreadsheet-runtime warmup warning in this environment; pytest itself ran. This environment does not match the repository's pinned Python 3.12 release environment.

## 6. Changes made in the working copy

- Restored `.github/workflows/secret-scan.yml` with working-tree, staged, and full-history scan steps.
- Reconstructed `.vscode/mcp.json` from the preserved Phase 155 configuration record, selecting only `india_testnet` and containing no credentials.
- Fixed the malformed configuration-fingerprint test in `tests/test_stage123_operational.py`.
- Regenerated `BUILD_MANIFEST.sha256`; verification passes.
- Added this audit report.

No strategy parameters, RR limits, exchange execution behavior, authorization template, historical capture bytes, or old phase reports were changed.

## 7. Remaining blockers and required owner action

1. **Credential exposure:** revoke/rotate any credentials previously included in the uploaded archive and review provider account activity. The agent cannot certify revocation.
2. **Git history:** coordinate a secret-removal history rewrite after rotation; the scanner correctly remains red until the credential-bearing history is addressed. Preserve a secure forensic record without redistributing secret blobs.
3. **Testnet authorization:** authorization remains `PENDING_OPERATOR_APPROVAL`. No order experiment was run. A user message alone does not complete the repository's cryptographic authorization procedure.
4. **Market-data evidence:** the Phase 192 phantom-row discrepancy remains an evidence-integrity defect in the historical Phase 193A reports; preserve those reports and use the reconciliation report as the correction record.
5. **Execution calibration and strategy edge:** zero empirical fills means queue-position/fill assumptions remain uncalibrated. `EDGE NOT ESTABLISHED`; no live readiness claim is justified.
6. **Full suite:** run under Python 3.12 with pinned dependencies, preferably in a dedicated environment, and triage all failures without blanket skips or changing frozen research pins.

## Final verdict

**Research / paper build: repair progress verified. Production / live trading: NO-GO.**

Targeted safety and regression tests pass and the repaired tree's manifest verifies. The full suite has not completed, history scanning fails for known credential-bearing commits, and empirical execution calibration / independent strategy evidence remain blocked. Live/testnet gates remain disabled; exchange order writes remain zero.
