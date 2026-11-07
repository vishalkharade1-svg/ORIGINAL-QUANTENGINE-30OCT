# Build handoff — Phase 129 audit repairs

Date: 2026-10-11

## Source and scope

This build was produced from the uploaded `Upgraded QuantEngine_PHASE85_TESTNET_CAPTURE_ORCHESTRATOR.zip`, which contains later Phase 127 work and a Phase 128 continuation queue despite the archive name. The source ZIP's credential-bearing `.env` and `env/.env.py` entries were deliberately excluded from this output. No credential values were copied into this handoff.

## Implemented in this repair

### F1 — Package security and hygiene

- Repacked from source files only; excluded `.env*` except `.env.example`, `env/`, Python bytecode/cache, pytest cache, `.git`, and nested ZIP archives.
- India Testnet capture/experiment scripts now use dedicated `DELTA_INDIA_TESTNET_API_KEY/SECRET` variables only. They no longer reuse generic `DELTA_API_KEY/SECRET`; the two bounded experiment scripts validate their REST/private-WS endpoint pair against the independent India Testnet environment mapping rather than relying only on a self-comparison.
- Added a package-level security and status explanation to `README.md`.
- Kept `.env.example` as a non-secret template. Credential rotation/revocation remains an operator action; packaging cannot rotate a key.

### F2 — Trailing-stop planned R:R semantics

- `post_cost_trailing()` now accepts an optional qualification target and symbol.
- When a target is present (as it is when RiskEngine converts a fixed-target plan to trailing management), it validates the **post-cost planned-target R:R** against the active per-instrument minimum and maximum before accepting the fill.
- The returned verdict reports planned-target R:R rather than a misleading `0.0`.
- The reason string explicitly states that planned-target qualification does **not** guarantee the realized R of a trailing-managed exit.
- Costed target-less trailing trades now fail closed because no planned R:R can be certified. Zero-cost test/replay paths still rely on their upstream structural gates; no claim is made that a target-less trailing plan satisfies target-R policy.

### F5 — Symbol-key normalization

- Policy keys now normalize case and common formatting separators (`BTC-USD`, `BTC/USD`, `BTC_USD` → `BTCUSD`).
- Quote assets and venue prefixes remain meaningful. `ETHUSD` is not silently aliased to `ETHUSDT`, and `DELTA:BTCUSD` is not silently treated as `BTCUSD`.
- This prevents accidental cross-market policy application while resolving superficial spelling differences. Explicit venue instrument metadata should be the source of any additional aliases.

### F7 — Maximum R:R at backtest erosion gate

- The breakout continuation fill gate now calls the shared `risk_reward_allowed()` authority for actual fill R:R, enforcing both configured minimum and maximum and rejecting non-finite ratios consistently.
- This retains the configurable default policy (1R–20R) and does not reintroduce a hidden 6R execution floor. `MIN_RISK_REWARD=6.0` remains research/governance configuration only where documented.

### Documentation

- Replaced the stale phase-11A README with a current, conservative build/readiness description.
- Updated `NEXT_ACTIONS.md` and `project_status.md` to mark the credential-bearing upload as a security incident and distinguish completed local repair tests from unresolved external evidence.
- Appended this phase to `IMPLEMENTATION_STATE.md`; historical phase records remain historical rather than being rewritten as current truth.

## Verification performed

Command:

```bash
python -m pytest tests/test_trading_policy.py tests/test_level4_rr_exit_policy.py tests/test_breakout_policy_erosion_phase99.py tests/test_policy_authority_guard_phase100.py tests/test_simulator_post_cost_gate_13.py tests/test_backtester.py tests/test_backtester_breakout.py tests/test_backtester_economics_wiring_66.py tests/test_backtester_hardening.py tests/test_post_cost_rr_13.py tests/test_risk_execution_contract.py tests/test_risk_gates_12.py tests/test_trade_simulator.py tests/test_operational_robustness_11c.py -q -p no:cacheprovider --tb=short
python -m pytest tests/test_delta_environment_phase82.py tests/test_delta_sandbox_environment_15.py tests/test_delta_rest_environment_phase91.py tests/test_phase85_capture_orchestrator.py tests/test_security_12.py tests/test_secret_scan_phase0.py tests/test_india_testnet_credential_isolation.py -q -p no:cacheprovider --tb=short
```

Result at initial repair checkpoint: **197 passed**. The tests include the trailing cost qualification, policy symbol normalization, policy boundaries, and backtest policy gate regressions. Re-run the command against the final ZIP after extracting it. The complete test suite has not been run to a clean pass for this build; earlier phase reports described known failures and are not evidence of a green full suite.

## Still blocked / not certified

- Full suite green and reproducible on the pinned Python/dependency environment.
- Exchange fee/funding/slippage model certification and remaining economics evidence.
- Global WebSocket wiring/continuity, reconnect/recovery, private fill reconciliation, and production transport evidence.
- Security key rotation/revocation by the account owner and any provider/account review.
- Strategy digest/OOS lineage reconciliation and independent quantitative edge validation.
- Production readiness, live order placement, or profitability. None is claimed here.

## Important semantic distinction

A setup's post-cost planned-target R:R is an entry qualification. Trailing management can close at a smaller or larger realized R. If the business rule is instead a guaranteed minimum *realized* R, a trailing stop cannot guarantee that rule by itself; that would require a different exit/acceptance design and cannot be solved by mislabeling planned R:R as realized R.
