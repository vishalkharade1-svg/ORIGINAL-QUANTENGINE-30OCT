# Phase144 trailing-stop short (EXECUTED, ETHUSD, 1 contract) — matrix complete

- Shape (venue-corrected): `market_order` + `stop_loss_order` + `trail_amount: -1.00` (negative for sells — first attempt with +1.00 rejected verbatim, second accepted 200).
- Order 2175474996 `pending`, trigger trailed up 2447.10→2448.69 live, never triggered down in 100s, cancelled VERIFIED, 0 open, size 0. Honest no-fill.

## Complete matrix (demo-Testnet, ETHUSD, 1 contract)

| Type | Long | Short |
|---|---|---|
| limit | FILLED both legs | FILLED both legs |
| market | FILLED both legs | FILLED both legs |
| stop-limit | PENDING shape verified | PENDING shape verified |
| stop-market | PENDING shape verified | PENDING shape verified |
| trailing-stop | PENDING + trail observed | PENDING + trail observed |

Fills: 8 limit/market (4 round trips, nets recorded in Phase141). Stops/trailing: 5 shapes venue-accepted, 0 triggered (honest). reduce_only exits verified. cancel() httpx-0.28 fix holding throughout.
All-symbols sweep: NOT RUN (refused). Old-account ADAUSD long: separate keys, untouched.
Verdict: EXECUTED within bounds. Production FALSE.
