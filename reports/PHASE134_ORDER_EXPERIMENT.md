# Phase134 bounded order experiment (EXECUTED 2026-10-15, authorized demo-Testnet)

Authorization: operator explicitly allowed demo-Testnet trading with these keys (no real money).
Bounds (from `scripts/bounded_testnet_order_experiment.py:45`): BTCUSD only, max 2x1, ~$200 notional cap, limit at touch, 20s wait then cancel, flat-in/flat-out, Testnet hosts only, Testnet-only key names, secrets never persisted.

## Run

- Dry-run: prechecks ok (bid 80489.0 / ask 80493.5), zero writes.
- Execute (`research/captures/phase134_recon/`): leg 1 buy 1 @80515.5 (order 2175449743) NOT filled in 20s (market moved away); sell leg never opened per plan. WS 2 frames auth OK, no user_trades frames → reconciliation BLOCKED (honest).
- Outcome: clean no-fill, same class as Phase120. Zero fills from our legs. No chasing.

## Safety incident found + fixed

- Cancel initially UNCONFIRMED (open count 1, position flat). Root cause: `DeltaSignedREST.delete` used `client.delete(..., content=...)`, removed in installed httpx 0.28.1 (pinned 0.27.2) → client-side TypeError swallowed → cancel never sent. Real trading-safety defect, not a test pin.
- Fix (`core/exchanges/delta/delta_auth.py:300`): use `client.request("DELETE",...)` when available, fallback to `delete()` shortcut for legacy fakes. Same wire bytes + signature.
- Regression: `tests/test_httpx_delete_compat_phase134.py` (2 tests) + `tests/test_delta_auth.py` 14 passed; combined shard 41 passed.
- After fix: cancel CONFIRMED, order `cancelled`, open count 0, position size 0. Book verified flat. No stragglers.

## Evidence

- `research/captures/phase134_recon/recon_experiment_report.json` (legs, ws, reconciliation BLOCKED, binding WINDOWED on pre-window fills only).
- No secret values in reports/logs/artifacts. `.env` never packaged.
- Fills wanted by operator were not obtained (market away + 20s cap respected). A fill run needs a fresh authorization + re-run; do not widen size/timeout to chase.

Verdict: EXECUTED, TESTED, safe. Production readiness FALSE. LIVE (real-money) never touched.
