# Phase136 mixed-type pilot (EXECUTED, authorized demo-Testnet, single symbol)

Bounds: ETHUSD only, 1 contract (~$24), limit legs up to 120s wait, market legs fill-or-abort, flat between combos. Max-symbols refused (unbounded exposure + bankruptcy precedent).

## Fills (venue-verified via /v2/fills reload)

- Combo A (limit→market): buy 1 @2438.95 (2175468602, limit) → sell 1 @2437.8 (2175468617, market). Net ≈ -$0.0115 demo.
- Combo B (market→limit): buy 1 @2438.35 (2175468633, market) → sell 1 @2438.35 (2175468648, limit, breakeven).
- Total: 4 orders, 4 fills, 0 open, position 0 — verified flat. 2-min waits honored for limit legs; market legs closed immediately.

## Notes

- New-account book (new keys) is flat. Old-account ADAUSD long (old keys) is separate and untouched by these keys — still needs its own direction.
- WS binding/economics certification remain BLOCKED (silent private WS, fee window) — fills above are real execution evidence, not certification.
- No secrets in artifacts. No further symbols traded; expansion only per-symbol with same bounds on fresh authorization.

Verdict: requested order-type data obtained on one symbol, safely. Production FALSE.
