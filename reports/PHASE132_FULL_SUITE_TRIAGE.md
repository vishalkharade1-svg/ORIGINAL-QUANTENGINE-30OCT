# Phase132 full-suite triage (EXECUTED 2026-10-15)

CMD: `python -m pytest -q -p no:cacheprovider --tb=short` (background, 3470.50s)
RESULT: **3905 passed, 41 failed, 10 skipped, 5 errors** — EXIT 1. NOT GREEN.
Raw (UTF-16): `reports/PHASE132_FULL_SUITE_RUN.txt`

## Categories (46 fail/error, zero in touched execution paths)

1. **No-git ancestry (15):** `test_researcher_11g_n/u` (14: branch_main + head_ancestor/descends) + `test_stage4_paper_certification::test_head_is_stage123_closure_descendant` (1). Cause: archive has no `.git`; `git grep/ls-files/rev-list` return empty. Pre-existing, UNVERIFIABLE, not caused here.
2. **Strategy/dataset hash pins (23):** `test_oos_data_extension_19` (11), `test_oos_feasibility_17` (2: nine_file_hash + artifact_bytes), `test_oos_topup` (1), `test_oos_validation_18` (3), `test_phase11f_data_lineage` (1), `test_phase11f_determinism` (1), `test_readiness_16` (2: artifact_bytes + strategy_hash_pinned), `test_researcher_15` (2: no_new_family + artifact_bytes). Cause: intentional Phase132-C source deltas (`accounting.py` comment + `paper_trading_engine.py` authority) move canonical digest `99a47bdd→1d30793e`; plus missing Git bytes + CRLF + research-dirt pins. Historical pins preserved, never re-pinned. Expected BLOCKED.
3. **Missing optional config (5 errors):** `test_delta_mcp_config_safety` (5) — `FileNotFoundError: .vscode/mcp.json`. Pre-existing fixture absent, not caused here.
4. **Git-dependent audit (1):** `test_upstream_hypothesis_audit::test_only_coercion_constructs_records_in_core` — uses `git grep`, returns [] without repo. Pre-existing no-git class.
5. **Research multiple-testing (1):** `test_researcher_15::test_no_new_hypothesis_family` — hash/pin class, pre-existing.
6. **Upstream edge (1):** counted in (4); total failed = 41.

No failures in: `trading_policy, level4, breakout_erosion, authority_guard, simulator_gate, post_cost_rr, broker_engine, paper_trading, execution_ack, live_block/boundary, candle continuity/finality/gates, reconciliation, safety_gates, history, monitoring, packaging, secret_scan, policy_symbol_threading_phase132`.

## Comparison

- Historical (Phase127/130, different env): 3869 passed / 67 failed. Current: 3905 passed / 41 failed +5 errors. Delta reflects pinned Python 3.12 env + 10 new Phase132 tests (all green) + intentional digest move. No new execution-policy regressions.
- Skips (10): documented (Git ancestry + pre-existing).

## Verdict

`Gate A: FAIL` (not green). `NOT_PRODUCTION_READY` stands. Failures are triaged pre-existing pin/env classes; none hide a fixable execution defect in scope. Do not blanket-skip or re-pin.
