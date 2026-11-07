# Paper Preview — Safety

PAPER ONLY. LIVE EXECUTION IS DISABLED. PRODUCTION_READY = FALSE.

## Hard boundaries (all tested)

- No order submission path exists in the preview: the transport
  imports no exchange write path; the dashboard has no buttons,
  forms, or POST calls; the API exposes no order/trade mutation
  routes (only the pre-existing PAPER lifecycle `/control`).
- Paper runtimes run `BrokerEngine(dry_run=True)`; paper orders
  cannot reach `DeltaOrderExecutor`.
- Minimum R:R 6.0 enforced (inclusive boundary preserved).
- Missing contract/economics keep existing paper semantics
  (UNAVAILABLE pass-through / vacuous cost layer — never venue
  truth, never performance evidence).
- `is_production_ready` is permanently False; readiness stays
  NOT_LIVE_READY (unchanged by this preview).

## Failure semantics

- Market-data outage: transport `on_down` → worker reconnect
  policy → dashboard RECONNECTING; no candles, no orders.
- Stale data: dashboard marks STALE from real timestamps (never
  LIVE merely because the process runs).
- Paper engine stopped: API surfaces lifecycle state; dashboard
  shows stopped, not frozen prices.
- Restart: fresh in-memory state replays deterministically;
  registry identity rules prevent duplicate orders/positions.

## Limitations (honest)

- 1m REST polling (~15s): not tick-precise; closes observed with
  up to one poll interval of delay plus bar finality.
- Fills are PAPER-MODELLED (existing deterministic simulator:
  limit-touch/next-bar-open, configured costs, no latency or
  liquidity model).
- Instruments use the explicit-universe synthetic fallback unless
  provider discovery supplies venue metadata (logged warning).
- Preview P&L is logic validation only, never performance evidence
  (readiness still gates NOT_EVIDENCE_READY by default).
