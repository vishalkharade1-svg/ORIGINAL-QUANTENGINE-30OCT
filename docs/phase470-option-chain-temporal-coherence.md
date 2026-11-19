# Phase 470 - Option-chain quote temporal coherence

- Validate that all selected option quotes are not only individually fresh but also close enough in time to form one coherent chain snapshot.
- Add a configurable finite, non-negative `max_quote_skew_seconds` limit (default: 2 seconds).
- Reject a chain when the oldest and newest selected quote timestamps exceed the allowed skew, even if each quote independently passes its age gate.
- Keep missing quotes explicit; absent quotes do not fabricate timestamps or prices.
- No provider calls, order submission, or live authorization is introduced.

Validation: stale-but-individually-fresh skew rejection, within-limit acceptance, and invalid-limit tests plus Phases 465-469 on Ubuntu and Windows.
