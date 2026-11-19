# Phase 466 — Option-chain identity and input hardening

- Reject option contracts with empty/non-string canonical instrument IDs, symbols, or exchange identifiers before grouping.
- Reject duplicate instrument IDs even when symbols differ; retain duplicate-symbol and duplicate-right checks.
- Reject boolean quote-age tolerances rather than silently interpreting True/False as numeric seconds.
- Preserve support for broader provider quote snapshots: unrelated symbols are not consumed, and missing selected-contract quotes remain missing.
- No quote synthesis, network access, order submission, or live authorization is introduced.

Validation: `tests/test_option_chain_phase466.py` plus the existing Phase 465 option-chain suite. CI remains the authoritative cross-platform execution record.
