# Phase 469 - Option contract precision validation

- Require finite positive premium tick size, quantity step, and minimum order quantity before including a contract in a chain.
- Reject NaN, infinity, zero, negative, and non-numeric precision metadata rather than carrying unusable order-sizing facts downstream.
- Preserve the existing lot-size, multiplier, exchange, expiry, identity, and quote-freshness gates.
- No order sizing or order submission is added; this is contract-data validation only.

Validation: parameterized precision-corruption tests plus Phase 465-468 regressions on Ubuntu and Windows.
