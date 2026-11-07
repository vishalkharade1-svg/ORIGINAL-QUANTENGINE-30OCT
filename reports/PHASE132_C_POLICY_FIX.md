# Phase132-C — Risk-policy symbol threading fix (EXECUTED)

Date: 2026-10-15
Status: TESTED (focused shards green) | Full suite: RUNNING (background) | Production: NOT_PRODUCTION_READY

## Defect (why it matters)

Per-instrument `trading_policy(symbol)` overrides were bypassed at fill choke points. A symbol with `min_rr=6` would still allow a 3R fill through the global fallback, violating the authoritative 1R default / 20R max with per-symbol override contract. No hidden 6R floor exists, but the override path was silently downgraded to global.

Sources of truth: `core/risk/trading_policy.py` (1.0..20.0 + canonical keys), `core/risk/costs.py` (`post_cost_rr/trailing` with `symbol`), `core/backtesting/accounting.py` (`risk_reward_allowed`).

## Findings (subagent audit, verified by inspection)

- `core/backtesting/trade_simulator.py:168` FIXED branch dropped `symbol` (trailing branch passed it) — DEFECT, fixed.
- `core/live/broker_engine.py:730` post-cost dropped `symbol` + `exit_mode`, flattening trailing to FIXED — DEFECT, fixed with trailing dispatch.
- `core/execution/economics.py:255` `recheck_rr` dropped `symbol` (dormant, zero callers) — DEFECT, fixed with optional `symbol=None`.
- `core/paper_trading/paper_trading_engine.py:351` + `broker_engine.py:707` duplicated `policy.min<=rr<=max` instead of single authority — drift risk, unified to `risk_reward_allowed(..., FIXED_TARGET, symbol)`.
- `core/backtesting/accounting.py:127` stale `1:6` comment — fixed to active policy bounds (comment only).

No executable `6.0` / `MIN_RISK_REWARD` floor found in `core/*,backtesting/*` (only frozen-research definition + dead mirrors). Min+max enforced everywhere after fix.

## Fix (smallest complete)

1. `trade_simulator.py`: FIXED `post_cost_rr(..., symbol=getattr(setup,"symbol",None))`.
2. `broker_engine.py`: import `risk_reward_allowed` + `post_cost_trailing`; gross via `risk_reward_allowed(FIXED_TARGET,symbol)`; post-cost dispatches TRAILING vs FIXED with `symbol` + `exit_mode`.
3. `paper_trading_engine.py`: gross via `risk_reward_allowed(FIXED_TARGET,symbol)`.
4. `economics.py`: `recheck_rr(..., symbol=None)` threaded to `post_cost_rr`.
5. `accounting.py`: comment `1:6` → active policy bounds.

No strategy/digest pins rewritten. No credentials, no network, no orders.

## Regression test

New `tests/test_policy_symbol_threading_phase132.py` (6 tests):
- simulator FIXED respects override (FAILED before: Trade booked, now refused)
- simulator allows when override satisfied
- post-cost authority override vs global
- max bound 20 passes / 20.1 fails
- target-less trailing refuses
- `recheck_rr` threads symbol (FAILED before: TypeError, now passes)

Before: 2 failed, 4 passed. After: 6 passed.

## Verification (EXECUTED)

- New shard: 6 passed.
- Policy + broker + paper + live shard: 159 passed (`trading_policy, level4, breakout_erosion, authority_guard, simulator_gate, post_cost_rr, broker_engine, paper_trading, execution_ack, live_block, live_boundary`).
- Phase131 shard + new: 77 passed, 1 skipped (Git ancestry absent).
- Risk/execution/paper/reconciliation shard: 125 passed.
- `compileall`: PASS. `SECRET_SCAN_PASS`. Policy file clean (`instruments:{}`).
- Digest: old `99a47bdd…` (Phase131) → new `1d30793e4e1ec7d6f8c5f14385d6308f869f74b8d8b4d86b348136af17d0b1f5` (accounting comment + paper authority change; both in nine-file set). Historical `9eff61b7…` / recorded `c52e64…` preserved unchanged. Status remains BLOCKED, not re-pinned.
- Full suite: background run started (`reports/PHASE132_FULL_SUITE_RUN.txt`), result pending — NOT claimed.

## Remaining

B01 git history, B02 digest BLOCKED, B03 full-suite green, B04 credential rotation (operator), B05 economics, B06 WS/recovery/private-fills. LIVE disabled. EDGE NOT ESTABLISHED.

Files changed: 5 source + 1 new test + baseline reports (see JSON).
