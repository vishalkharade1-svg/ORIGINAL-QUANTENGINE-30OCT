# Phase154 ledger evidence audit (read-only, raw preserved)

Source (extracted input copy, never modified): `research/captures/phase153_ledger/fills_100.json` (7c27e86112d9), `wallet_100.json` (0858922de6cb). Provenance: Phase147/153 Testnet reads (`/v2/fills`, `/v2/wallet/transactions`, page_size=100); filenames record the REQUEST page size, not returned counts.

## Verified invariants

- 22 fill rows: unique IDs, symbols BTCUSD 12 / ETHUSD 8 / SOLUSD 2.
- 33 wallet rows: unique UUIDs, 22 commission + 10 cashflow + 1 external_deposit.
- Commission cross-check: |fills sum| == |wallet commission sum| (0.62949307, Phase153 ledger).
- Limitations: wallet rows are NOT chronological (venue recency order kept verbatim — no re-sorting, no fabrication); cashflow↔fill linkage is positional, not join-keyed — no complete accounting reconciliation claimed beyond the commission sums.

## Privacy (restricted vs distributable)

- `user_id` present on 33/33 wallet rows; order/fill/client IDs throughout. Raw files are RESTRICTED evidence: kept in research captures, never pasted into general reports.
- Phase141/147/153 reports carry aggregates only (counts, sums, effective-bp rates). Secret scan passes on all of them (values, not just secrets, were excluded by construction).
- No sanitized copy created: aggregates already serve distribution; raw stays restricted. Secret scan PASS ≠ privacy clearance — stated explicitly.

Status: TESTNET_EVIDENCE with stated limits. Funding leg: 0 funding rows (no held-through-settlement). Production readiness: FALSE.
