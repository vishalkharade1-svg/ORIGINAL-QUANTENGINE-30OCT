# Phase137 short + stop pilots (EXECUTED, authorized demo-Testnet, ETHUSD only)

## Short-direction limit round-trip (fills)

- S1: sell 1 @2436.4 FILLED (2175473344, limit).
- S2: buy 1 @2436.2 FILLED (2175453350→2175473350, limit, reduce_only:true — venue accepted reduce_only on exits).
- Net ≈ +$0.002 demo. Verified flat (size 0, 0 open). Completes long+short coverage for limit/market types.

## Stop-limit entry (venue shape verified, untriggered)

- Payload (per official CreateOrderRequest schema): `limit_order` + `stop_order_type: stop_loss_order` + `stop_price: 2438.00` + `stop_trigger_method: mark_price` + `limit_price: 2438.05`.
- Order 2175473363 reached `pending` (correct untriggered stop state — proves shape accepted), no trigger in 120s (mark stayed ~2436.3), cancelled VERIFIED (True), 0 open, size 0. Honest no-fill.
- Note: shell 120s timeout killed the wait loop; order recovered via open-orders re-query, never assumed.

## Not run (explicit)

- Stop-market and trailing-stop entries (both fire market orders at trigger — highest slippage class), all-symbols matrix, short-via-market. Each needs its own single-symbol pilot with flat checks; trailing additionally needs realized-R disclaimer (no fixed target).
- Old-account ADAUSD long: separate account/keys, untouched.

## Evidence

- Order IDs, states, and fills above reload-verified via `/v2/orders` + `/v2/positions`. No secrets in artifacts.
- Verdict: EXECUTED within bounds. Production FALSE.
