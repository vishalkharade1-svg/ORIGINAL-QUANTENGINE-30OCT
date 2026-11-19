# Phase 468 - Immutable option contract snapshots

- Replace mutable `Instrument` references inside option legs with a frozen scalar `OptionContractSnapshot`.
- Capture contract identity, venue, right, expiry, strike, tick/quantity rules, lot size, and multiplier at chain-build time.
- Mutating the original registry object or its metadata after assembly cannot rewrite the chain's contract facts.
- Export the snapshot type from `core.options` for explicit downstream typing.
- Normalized quotes remain frozen; this phase introduces no provider calls, quote synthesis, order submission, or live authorization.

Validation: mutation-isolation and frozen-instance tests plus Phase 465-467 option-chain regressions on Ubuntu and Windows.
