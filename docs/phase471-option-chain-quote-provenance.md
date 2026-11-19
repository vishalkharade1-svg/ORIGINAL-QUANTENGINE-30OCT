# Phase 471 - Option-chain quote timestamp provenance

- Expose the oldest and newest selected quote timestamps on the immutable chain result.
- Expose the measured quote timestamp skew in seconds so downstream analytics and risk gates can inspect the actual snapshot coherence.
- Report all three provenance fields as `None` when no selected contract has a quote; do not substitute assembly time for market-data time.
- Retain the Phase 470 skew rejection threshold and all existing contract integrity checks.

Validation: timestamp-bound/skew assertions and the no-quote provenance case, with Phases 465-470 on Ubuntu and Windows.
