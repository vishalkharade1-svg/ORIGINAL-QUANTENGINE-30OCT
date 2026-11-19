# Phase 467 — Exchange-bound option chains

- Require every option contract in a chain to belong to the same canonical exchange.
- Expose the verified exchange on the immutable `OptionChain` result so downstream analytics cannot infer it from an arbitrary leg.
- Reject mixed NSE/BSE or other cross-venue contract sets before quote pairing.
- Preserve existing underlying, expiry, lot-size, multiplier, identity, and quote-source gates.
- No provider calls, quote synthesis, order submission, or live authorization are introduced.

Validation: Phase 467 mixed-exchange and exchange-identity tests, together with Phase 465/466 regressions, on Ubuntu and Windows.
