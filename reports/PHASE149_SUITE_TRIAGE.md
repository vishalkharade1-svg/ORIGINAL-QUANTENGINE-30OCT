# Phase149 full-suite re-run triage (EXECUTED, post-fix)

CMD: `python -m pytest -q -p no:cacheprovider --tb=short` → `reports/PHASE149_FULL_SUITE_RUN.txt`
RESULT: **43 failed, 3909 passed, 10 skipped, 5 errors** in 2326.94s (EXIT 1).
BASELINE (Phase132): 41 failed, 3905 passed, 10 skipped, 5 errors.

## Set diff (load-bearing)

NEW failures (2, both expected operator-secret detections, tests working as designed):
- `test_packaging_no_secrets_phase132::test_no_secret_bearing_paths` — `.env` with live Testnet secrets now present (absent at baseline).
- `test_secret_scan_phase0::test_current_worktree_has_no_detected_secret_material` — scanner correctly reports 2 findings.

FIXED: none. All 12 Phase132–134 tests green (none in failure list). Zero new execution-path failures.

## Verdict

Gate A still FAIL (pre-existing pins + 2 correct secret detections). NOT_PRODUCTION_READY stands. The 2 deltas prove the scanner/packaging guards work against the live `.env`; they must NOT be "fixed" by deleting operator credentials or weakening the tests.
