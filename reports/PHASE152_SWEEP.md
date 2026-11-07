# Phase152 one-by-one sweep (EXECUTED, authorized demo-Testnet, flat throughout)

## BTCUSD matrix complete (1 contract, ~$82)

- Stop-market long/short: PENDING shapes verified, untriggered, cancelled verified.
- Trailing long: TRIGGERED+FILLED @82644.2 → limit exit @82322 (≈ -$0.32 spread cost). First trailing fill.
- Trailing short: TRIGGERED+FILLED @82315.5 → cover @82322.5 (≈ -$0.007). Flat.
- Market short: sell @82141.5 → covers missed rallies (2x cancelled, one re-price) → market close @82215 (≈ -$0.074). Flat.
- Market long: buy @82141.5 → sell @82200 (≈ +$0.059). Flat.
- Full BTCUSD matrix now mirrors ETHUSD: limit/market filled both ways; all 3 stop types verified both ways (2 fills via trailing).

## Second symbols

- SOLUSD: verified live/operational (tick 0.0001, cval 1, notional $107.68 < $200 cap); buy @107.677 FILLED → sell @107.247 FILLED (≈ -$0.43 spread). Flat.
- ADAUSD: SKIPPED for re-entry — venue refuses loss-exits (`out_of_bankruptcy`, evidenced twice); new-account re-entry risks another unexitable long. Old-account long stands separate.

## Repeat-match recon (BTCUSD script)

- Legs both FILLED (2175504564/65), WS 4 frames, but reconciliation BLOCKED: exact-set semantics flags pre-window REST fills as missing_from_ws (reconciler limitation, honest refusal — same class as Phase125 strict-refusal note). Book flat.
- Robustness conclusion: MATCHED once (Phase146), BLOCKED on window-mismatch since — WS match is fill-timing-sensitive, not steady-state.

All books flat (BTCUSD/SOLUSD/ETHUSD size 0, 0 open). No secrets in artifacts. Production FALSE.
