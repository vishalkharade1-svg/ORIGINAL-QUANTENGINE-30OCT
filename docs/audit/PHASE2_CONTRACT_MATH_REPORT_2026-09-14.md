# QuantEngine Phase 2 — Contract Math Report

## Implemented

- Added `core.risk.contract_math`, a Decimal-based, standalone sizing and
  stop-loss boundary for explicit `LINEAR`, `INVERSE`, and `OPTION_PREMIUM`
  contract kinds.
- Required a complete cost model (entry/exit fees, half-spread, slippage, and
  funding); there is no implicit zero-cost constructor.
- Added risk-budget sizing that rounds downward to the quantity step, refuses
  minimum-size dust, and cannot exceed the inclusive stop-loss budget.
- Added `contract_spec_from_instrument`, which requires explicit verified
  contract kind and multiplier metadata. It refuses to reinterpret the
  current `contract_value`/`quantity_step` mapping as settlement truth.

## Verification

| Command | Result |
|---|---|
| `python -m pytest tests/test_contract_math_phase2.py tests/test_quant_math_11b.py tests/test_risk_config_9q.py tests/test_safety_guards_11a.py tests/test_order_executor.py tests/test_live_block_11.py -q` | **137 passed**; one non-fatal `.pytest_cache` permission warning |
| `python -m pytest tests/test_contract_spec_factory_phase2.py tests/test_contract_math_phase2.py tests/test_delta_mapper.py tests/test_delta_loader.py tests/test_instrument_discovery.py tests/test_risk_config_9q.py tests/test_live_block_11.py -q` | **74 passed**; one non-fatal `.pytest_cache` permission warning |
| `python scripts/security/scan_secrets.py` | `SECRET_SCAN_PASS` |
| `git diff --check` | **PASS** |

## External integration gate

The new module is intentionally not wired into `PositionSizer`, risk, or
execution. Before doing so, official Delta product/sandbox evidence must
verify per-product settlement convention, multiplier, quantity increment,
fee tier, funding treatment, and whether stop risk is realized/charged in
quote or settlement currency. Until then the legacy price-distance sizing
remains **not contract-aware**, and new math availability is explicitly
`UNAVAILABLE` rather than guessed.

## Phase 7 increment

The broker reconciliation snapshot now flushes and fsyncs its complete JSON
record before atomic replacement. Restart comparison remains fail-closed and
requires exchange authority; the change adds durability only and does not
perform any exchange action.

## Phase 9 increment

`assess_paper_readiness()` labels paper-run economics as `READY` only when a
nonzero, explicitly venue-realistic cost profile is declared. It is a report
evidence label only; it neither authorizes live trading nor establishes
profitability.
