# Phase135 multisymbol bounded run (EXECUTED, limit-only, authorized demo-Testnet)

Scope authorized: 2–3 symbols max, limit only (market refused). Bounds per symbol: 1 contract, ~$200 cap, 20s wait, verified cancel, flat-in per symbol.

## Outcomes (genuine venue responses)

- ETHUSD (id 1699, tick 0.05, cval 0.01): buy 1 @2375.8 FILLED (2175451023); sell 1 @2375.75 unfilled→cancelled; exit sell 1 @2373.5 unfilled→cancelled; exit sell 1 @2370.40 FILLED (2175451223). Net ≈ -$0.05 demo. Final: 0 open, size 0. COMPLETE round-trip.
- ADAUSD (id 101760, tick 0.00001, cval 1): buy 1 @0.23327 FILLED (2175451255); sell 1 @0.22964 REJECTED 400 `out_of_bankruptcy` (loss-breaching exit refused by venue); exit sell 1 @0.23327 (breakeven) placed (2175451369) unfilled 20s → cancelled True. Final: 0 open orders, LONG 1 @0.23327000 OPEN (~$0.23 exposure).
- BTCUSD: flat, 0 open (Phase134 order cancelled verified).

## Safety events

- httpx 0.28 `delete(content=)` cancel outage found + fixed in Phase134 (`delta_auth.py:300`, request-with-fallback); all cancels since VERIFIED (True).
- ADAUSD float-noise price (`0.23327000000000003`) caused one 400; Decimal tick alignment used thereafter.
- Venue `out_of_bankruptcy` respected fail-closed: no market order forced (limit-only scope). No chasing, no widened timeouts.

## Evidence

- `research/captures/phase134_recon/` (BTCUSD no-fill, reconciled attempt), `research/captures/phase135_multisymbol/multisymbol_report.json` (this run), REST fills reload-verified. No secrets in artifacts.
- Fills obtained: ETHUSD 2 (entry+exit), ADAUSD 1 (entry). WS binding BLOCKED (silent private WS, as before).

## Open exposure (explicit, not hidden)

- LONG 1 ADAUSD @0.23327 (~$0.23). Zero working orders. Awaiting operator direction: hold working breakeven exit, retry exit later, or separately authorize a market/accept-loss exit (out of current limit-only scope).

Verdict: EXECUTED within bounds. Production FALSE. No further orders without direction on the open long.
