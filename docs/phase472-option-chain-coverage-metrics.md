# Phase 472 - Option-chain quote coverage metrics

- Expose total supplied contract count and validated quoted-contract count.
- Report quote coverage as a ratio from 0.0 to 1.0 across supplied contracts.
- Report missing call/put contract legs separately from present contracts whose quote is missing.
- Preserve the distinction between an absent contract and an unquoted contract; neither is synthesized.
- Metrics are derived from the immutable assembled chain and do not authorize trading.

Validation: quote coverage, missing quote, missing leg, and zero-quote cases plus Phases 465-471 on Ubuntu and Windows.
