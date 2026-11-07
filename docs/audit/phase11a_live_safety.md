# Phase 11A — LIVE Safety Evidence

Commit: `6f5e608` (parent `3609864`). All counts below are measured, not fabricated.

## What changed (production)

- NEW `core/execution/live_safety_gate.py` — the single centralized boundary:
  `ExecutionMode` (PAPER / LIVE / ANALYZE, conflict + unknown rejected with
  `ConfigurationError`), `LiveSafetyGate.decide / require / require_decision /
  from_settings / test_armed / describe / format_banner`, typed
  `LiveBlockedError`. No secrets in reasons, banners, or audit events.
- `config/settings.py` — NEW `ALLOW_LIVE` (default false) + `EXECUTION_MODE`
  (optional override, default unset).
- `core/execution/order_executor.py` — `execute(intent, *, safety=None)` enforces
  the gate AFTER intent/contract validation and BEFORE payload/transport;
  NEW `InvalidContractError(ValueError)` validates `product_id > 0` and integer
  `price/quantity_precision >= 0` in `_contract()`.
- `core/live/broker_engine.py` — `dry_run=False` requires an armed `safety`
  token at construction; `_route` re-enforces the token on EVERY live route
  and forwards it to safety-capable executors.
- `main.py` — mode resolved once via `ExecutionMode.resolve` (conflict/unknown
  fail closed); auditable startup banner (`EXECUTION MODE / LIVE EXECUTION /
  LIVE SAFETY`, no secrets); LIVE branch arms via `require` and passes the
  token to `BrokerEngine(dry_run=False, safety=...)`. No silent PAPER-wins,
  no silent analyze-only fall-through.
- `core/exchanges/delta/delta_contract_loader.py` — transport/schema failures
  wrapped in NEW typed `ContractLoadError` (no bare `KeyError("result")`).
- `examples/test_delta_order_executor.py` — `DELTA_EXECUTE=1` path arms via the
  gate explicitly.
- `PositionSizer` balance `<= 0` guard: VERIFIED PRE-EXISTING
  (`core/risk/position_sizer.py:59-89`, returns `valid=False, quantity=0`);
  pinned by new tests, behavior unchanged.

## What changed (tests)

- `tests/test_live_block_11.py` — rewritten: 7 vacuous tests replaced by 26
  action-backed tests (mode resolution, gate matrix, real-chain transport
  boundary with counting fake at `rest.post("/v2/orders")`, PAPER lifecycle on
  the real offline `build_paper_engine`, startup shapes, secret-leak check).
- `tests/test_safety_guards_11a.py` — NEW: 14 P1 guard tests (sizer balance,
  contract validation incl. zero-transport proof, loader error wrap).
- Minimal arming updates (assertions unchanged): `test_order_executor.py`
  `test_execute_places_valid_intent` passes `test_armed()`; `test_broker_engine.py`
  `TestBrokerEngineLive._engine` defaults `safety=test_armed()`.

## Measured results

| Check | Result |
|---|---|
| Safety files `pytest tests/test_live_block_11.py tests/test_safety_guards_11a.py -q` | 40 passed, 0 failed |
| Full suite `pytest tests --ignore=_archive --ignore=examples -q` | 1768 passed, 0 failed |
| `python -m scripts.verify_gate_a` | PASS (27 orders, 11 fills, 6W/5L, net 3.80889, IDs identical 1e-6) |
| `python -m compileall -q core` | clean |
| Real exchange order calls | 0 (all transports are local fakes; no network in tests) |
| PAPER run: candles routed | 30/30, live-surface calls 0 |
| Refusals with measured zero transport calls | 5 (executor blocked, settings-default blocked, broker construction, broker per-route re-check, invalid contract) |
| Unknown-mode rejections | 4 tests / 7 invalid inputs |
| Conflict rejections | 2 tests |
| Positive controls (fake posts to `/v2/orders`) | 1 (executor) + 1 (broker route) |

## Mutation proof (temporary local edits, NOT committed)

Gate file hash after restore equals pre-mutation hash (`3e77f6...9c69`).

| Guard removed | Suite effect |
|---|---|
| ALLOW_LIVE check | 4 failed, 22 passed |
| LIVE_EXECUTE check | 1 failed, 25 passed |
| credential check | 1 failed, 25 passed |
| unknown-mode validation | 1 failed, 25 passed |
| PAPER+LIVE conflict validation | 2 failed, 24 passed |

Every critical guard demonstrably fails tests when removed (Gate L).

## Gaps / non-goals (honest)

- `cancel/fetch/balance/positions` pass-throughs are NOT gate-wrapped; only the
  order-submission boundary (`execute`) is. Cancel is a live write and may merit
  gating in a follow-up.
- `core/validation/` math + incremental caches were not re-certified here (out of
  scope; STATUS byte-identical proofs stand).
- PAPER lifecycle intent in the 30-candle run is pipeline-generated-or-absent per
  strategy; the zero-live-call assertion holds either way because candles flowed
  (`routed == 30`) while the live surface was spied.
- `.env` is tracked and contains API-like strings; tests never read real
  credentials (synthetic values + fakes only). Untracking/rotation is a separate
  hygiene task per instructions.

## Safety state at rest

Default configuration (`PAPER_MODE=True`, no `ALLOW_LIVE`, no `LIVE_EXECUTE`):
`EXECUTION MODE: PAPER / LIVE EXECUTION: BLOCKED`. LIVE remains deliberately
armable ONLY via all four conditions plus the gate — proven by the positive
controls against local fakes.
