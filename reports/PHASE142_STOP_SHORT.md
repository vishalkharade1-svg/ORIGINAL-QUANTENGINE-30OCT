# Phase142 stop-limit short (EXECUTED, ETHUSD, 1 contract)

- Payload mirror of verified long shape, side inverted: `limit_order` + `stop_loss_order` + `stop_price: 2446.95` (below mark) + `limit_price: 2446.45` + `mark_price` trigger.
- Order 2175474687 `pending` (correct untriggered state), no trigger in 100s, cancelled VERIFIED, 0 open, size 0. Honest no-fill.
- Remaining: stop-market short, trailing-stop short. All-symbols sweep NOT RUN. Old-account ADAUSD long untouched.
- Verdict: EXECUTED within bounds. Production FALSE.
