# Claude Independent Audit Prompt — QuantEngine Phase132 sanitized state

You are an independent adversarial auditor. Inspect ONLY the provided source archive (`QuantEngine_PHASE132_RELEASE_CANDIDATE.zip`, sha256 `aa4470282c6dcc4bcd34c7135c060de7c7d499174f70ff6fa4f8e5b5e0072010`) and its reports. Do not trust `IMPLEMENTATION_STATE.md` or `NEXT_ACTIONS.md` without verifying against code and test evidence.

## Scope

1. **Secrets:** search for non-empty `DELTA_API_KEY/SECRET`, `DELTA_INDIA_TESTNET_*`, `DELTA_SANDBOX_*`, tokens, private keys in code, tests, fixtures, logs, reports, ZIP. Verify `scripts/security/scan_secrets.py` covers Testnet/Sandbox and `SECRET_SCAN_PASS` reproduces.
2. **Risk policy:** verify single authority `core/risk/trading_policy.py:22` (1.0..20.0), canonical `_key`, no hidden 6R floor in `core/*,backtesting/*`. Verify `trade_simulator.py:168`, `broker_engine.py:703`, `paper_trading_engine.py:333`, `costs.py:278`, `economics.py:255` thread `symbol` (+`exit_mode` where applicable). Distinguish planned-target R vs realized R; trailing target-less must refuse.
3. **Environment separation:** Testnet vs production endpoints/keys isolated; defaults cannot arm LIVE (`config/settings.py`, `LiveSafetyGate`). No production transport without explicit arming.
4. **Lifecycle:** idempotency, partial fills, cancels verified-by-requery, unknown-state halts, exact-once accounting (`accounting.net_pnl` single subtraction).
5. **Data:** sequence/gap/reconnect/stale fail-closed; fixtures vs live evidence distinguished; no lookahead.
6. **Economics:** fee/rate/slippage/funding provenance per component; missing = BLOCKED, never zero-filled. Verify `describe()`/`require_known()` usage.
7. **Tests:** full suite reports 3905 passed / 41 failed / 10 skipped / 5 errors. Confirm 46 are pin/env classes (no-git, hash, missing `.vscode/mcp.json`) with zero in execution paths. Flag ANY mass-skip or re-pin that hides a failure — none is authorized.
8. **Deployment:** clean-env reproducibility, safe defaults, no secrets/pyc/cache in ZIP (1708 files), rollback/health checks.

## Rules

- Distinguish static review from executed tests. Cite `file:line` for every claim.
- Statuses: IMPLEMENTED / EXECUTED / TESTED / VERIFIED / BLOCKED_EVIDENCE / NOT_PRODUCTION_READY only.
- If a historical digest (`99a47bdd`, `9eff61b7`, `c52e64`, current `1d30793e`) cannot be reproduced from this archive alone, label UNVERIFIABLE, not PASS.
- List findings by severity (Critical/High/Medium/Low), with reproduction steps. Fix nothing; report only.

## Deliverable

Machine-readable findings JSON + concise verdict (`PRODUCTION_READY` only if every gate A–I passes with evidence, else `NOT_PRODUCTION_READY` with blocker list).
