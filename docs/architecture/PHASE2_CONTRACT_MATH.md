# Phase 2 Contract Math

`core.risk.contract_math` is a standalone Decimal calculation boundary. It
requires an explicit `ContractKind`, multiplier, tick/quantity constraints,
and a complete non-null cost model. It supports linear contracts,
fixed-quote inverse contracts, and option-premium contracts. It does not infer
Delta settlement semantics from incomplete metadata and is not connected to
the existing float-based `PositionSizer`.

The cost-inclusive risk budget includes entry/exit fees, two half-spreads,
slippage and per-contract funding. A size is rounded down to the quantity step
and rejected when the budget cannot reach venue minimum quantity.

Before integration, exact Delta product contract settlement, fee tiers,
funding treatment, and quantity constraints require official exchange/sandbox
verification.

`contract_spec_from_instrument()` enforces this rule at the registry boundary.
It only accepts explicit `verified_contract_kind` and
`verified_contract_multiplier` metadata. In particular, it does **not** treat
the current normalizer's `contract_value`/`quantity_step` mapping as proof of
a settlement multiplier.
## Verification provenance gate — 2026-09-16

`contract_spec_from_instrument()` now requires both explicit contract facts and
non-empty `verified_venue_source` / `verified_venue_verified_at` metadata.
`cost_model_from_instrument()` applies the same requirement to entry/exit fees,
half spread, slippage, and funding. An explicitly evidenced zero remains a
valid input; a missing field never becomes a zero-cost default. This is a
construction guard only: it does not assert that the repository currently has
verified Delta product, fee, funding, or settlement facts.
