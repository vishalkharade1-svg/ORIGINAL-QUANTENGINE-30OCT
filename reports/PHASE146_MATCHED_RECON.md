# Phase146 first MATCHED reconciliation (EXECUTED, BTCUSD bounded 2x1)

- Legs: buy 1 @82496.5 FILLED (2175475317) → sell 1 @82492.5 FILLED (2175475319). Cleanup: 0 open, flat.
- Private WS: 4 frames (protocol + trade frames), auth OK.
- Reconciliation: **MATCHED**, 2/2 fills, REST sha `4964b1e3…`.
- Fill/friction binding: buy slippage 3.0 ($0.003 notional? 0.36bp vs touch, 55ms alignment); sell leg bound similarly. First simultaneous-friction evidence in this account.
- Fix from Phase145 verified end-to-end (no crash; REST artifact written, `rest_fills.json` 1149 B).
- L2 concurrent: manifest + 211KB archive + friction evidence persisted.
- No secrets in artifacts. Old-account ADAUSD long untouched (separate keys).

Remaining for certification: funding leg (hold through settlement), fee-window history, repeated-match robustness. Production FALSE.
