# Phase138 short-via-market (EXECUTED, ETHUSD, 1 contract)

- M1: market sell 1 @2438.25 FILLED (2175473683).
- M2: limit buy 1 @2437.15 FILLED (2175473702, reduce_only:true).
- Net ≈ +$0.011 demo. Verified flat (size 0, 0 open).

## Coverage matrix (demo-Testnet,、有 fills unless noted)

| Entry \ Exit | limit | market |
|---|---|---|
| limit long | FILLED (Phase136 A) | FILLED (Phase136 A) |
| market long | FILLED (Phase136 B) | — (same-tick, no data value) |
| limit short | FILLED (Phase137) | — |
| market short | FILLED (this run) | — |
| stop-limit long | PENDING shape verified, untriggered no-fill (Phase137) | — |
| stop-market | NOT RUN | NOT RUN |
| trailing-stop | NOT RUN (market-firing, highest risk) | — |

All-symbols sweep: NOT RUN (refused as unbounded). Old-account ADAUSD long: separate keys, untouched.
Verdict: EXECUTED within bounds. Production FALSE.
