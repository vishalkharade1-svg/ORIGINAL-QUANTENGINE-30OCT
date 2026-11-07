# Phase139 stop-market entry (EXECUTED, ETHUSD, 1 contract)

- Payload (official schema + stop-limit mirror minus limit_price): `market_order` + `stop_order_type: stop_loss_order` + `stop_price: 2445.10` + `stop_trigger_method: mark_price`.
- Order 2175474025 reached `pending` (correct untriggered stop state — proves shape accepted), mark never hit trigger in 100s, cancelled VERIFIED (True), 0 open, size 0. Honest no-fill.
- Outstanding: trailing-stop entry only (fires market at trigger with trail semantics — highest slippage class; needs realized-R disclaimer). All-symbols matrix NOT RUN (refused). Old-account ADAUSD long untouched.
- Verdict: EXECUTED within bounds. Production FALSE.
