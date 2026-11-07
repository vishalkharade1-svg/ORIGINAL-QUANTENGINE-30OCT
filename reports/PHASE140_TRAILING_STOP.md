# Phase140 trailing-stop entry (EXECUTED, ETHUSD, 1 contract)

- Shape (venue-corrected, official schema): `market_order` + `stop_order_type: stop_loss_order` + `trail_amount: 1.00` ONLY (venue 400: "Only stop_price or trail_amount should be specified for stop loss orders" — first attempt with both rejected, second with trail-only accepted 200).
- Order 2175474201 `pending` with venue-derived stop 2445.02 trailing down to 2443.06 live (genuine trailing semantics observed), never triggered up in 100s, cancelled VERIFIED, 0 open, size 0. Honest no-fill.
- Realized-R disclaimer stands: trailing fires a market order at trigger with no fixed target — no R:R certified on this type, consistent with `order_executor.py:270` fail-closed and `post_cost_trailing` plan-vs-realized split.

## Full order-type matrix (demo-Testnet, single-symbol, 1 contract)

| Type | Long entry | Short entry | Exit evidence |
|---|---|---|---|
| limit | FILLED | FILLED (+reduce_only cover) | limit reduce_only verified |
| market | FILLED | FILLED | immediate |
| stop-limit | PENDING shape verified, untriggered | NOT RUN | — |
| stop-market | PENDING shape verified, untriggered | NOT RUN | — |
| trailing-stop | PENDING + live trail observed, untriggered | NOT RUN | — (no fixed target, never certify R) |

All-symbols sweep: NOT RUN (refused). Old-account ADAUSD long: separate keys, untouched.
Verdict: EXECUTED within bounds. Production FALSE.
