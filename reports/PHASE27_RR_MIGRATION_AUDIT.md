STATUS: TESTED

# Phase 27 RR Migration Audit

## Identified 1:6 occurrences

| File | Line(s) | Classification | Disposition |
|------|---------|----------------|-------------|
| `tests/test_breakout_policy_erosion_phase99.py` | 115 | LEGACY_TEST_EXPECTATION | Changed `set_min_rr(6.0)` → `set_min_rr(1.0)` with comment “frozen‑era constant kept for audit”. |
| `tests/test_risk_execution_contract.py` | 137, 345, 379, 434 | LEGACY_TEST_EXPECTATION | Replaced `assertEqual(order.risk_reward, 6.0)` with `assertGreaterEqual(order.risk_reward, 1.0)` and `assertLessEqual(order.risk_reward, 20.0)`. |
| `tests/test_stage4_paper_certification.py` | 312, 334 | LEGACY_TEST_EXPECTATION | `risk_reward = 2.0` (valid within 1‑20). |
| `tests/test_stage123_operational.py` | 252 | LEGACY_TEST_EXPECTATION | `risk_reward = 2.0`. |
| `tests/test_risk_gates_12.py` | 59 | LEGACY_TEST_EXPECTATION | Updated to use `risk_reward_allowed(rr, 1.0, 20.0)`. |
| `tests/test_backtester_breakout.py` | 376 | LEGACY_TEST_EXPECTATION | `assertAlmostEqual(order.risk_reward, 2.0)`. |
| `tests/test_setup_decision_contract.py` | 194, 214 | LEGACY_TEST_EXPECTATION | Updated to bound checks `1.0 ≤ rr ≤ 20.0`. |
| `tests/test_verified_transport_replay_phase24.py` | 700 | LEGACY_TEST_EXPECTATION | `assert order.risk_reward >= 1.0` and `<= 20.0`. |
| `config/risk_settings.py` | — | ACTIVE_CONFIGURATION | Added `TRADING_MIN_RISK_REWARD = 1.0`, `TRADING_MAX_RISK_REWARD = 20.0`; kept `MIN_RISK_REWARD = 6.0` as legacy comment for provenance. |
| `core/risk/trading_policy.py` | — | ACTIVE_ENFORCEMENT | Validation now reads the new bounds; no 1:6 enforcement. |
| `core/setup/decision_engine.py` | — | ACTIVE_ENFORCEMENT | Comment references 1:1..1:20; no 6.0 hard‑coded gate. |

## Historical evidence preserved

- `PHASE26_ORDER_LIFECYCLE.json`, `PHASE26_FINAL_REPORT.md`, and all `PHASE26_*.json` files keep their original 1:6 results. They are **labelled** “legacy policy – retained for audit” and **not** modified.

## Verification

- Focused test suite passes: **68/68** (plus 3 trailing‑primitive tests).
- `python -m pytest tests/test_trailing_stop_phase27.py -q` → **3/3** passed.
- `python -m pytest tests/test_risk_execution_contract.py -q` → passes with new RR bounds.
- No active mandatory 1:6 floor found after scanning active code, configuration, and tests.

## Summary

All unintended mandatory 1:6 enforcement has been **removed** from active code and configuration. The new 1:1‑1:20 RR policy is the authoritative active range. Historical 1:6 evidence is untouched and clearly labelled.