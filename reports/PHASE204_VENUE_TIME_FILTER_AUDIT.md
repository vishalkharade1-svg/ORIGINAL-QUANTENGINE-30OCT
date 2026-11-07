# QuantEngine Phase 204 — Venue-side historical time filters

## Objective
Replace Phase 203's client-only historical selection with the documented Delta REST time filters for the read-only reconciliation snapshot.

## Documentation basis
Delta's current REST API documentation lists `start_time` and `end_time` as query parameters expressed in epoch microseconds for:
- `GET /v2/orders`
- `GET /v2/orders/history`
- `GET /v2/fills`
- `GET /v2/wallet/transactions`

The same documentation identifies `product_ids` (comma-separated) for the order/fill product filters and cursor pagination via `after`, `before`, and `page_size`. `GET /v2/positions` is documented as a current position snapshot, not a historical event feed; this phase does not add unsupported time filters to it.

Source: https://docs.delta.exchange/ (REST API: Orders, TradeHistory, Wallet; accessed 2026-10-30).

## Implementation
- Converts timezone-aware ISO-8601 window bounds to UTC epoch microseconds without float timestamp arithmetic.
- Expands the requested interval by `overlap_seconds` on both sides, then sends the resulting inclusive bounds as `start_time` / `end_time` to orders, order history, fills and wallet transactions.
- Uses `product_ids=<id>` for order, order-history and fill requests; wallet transactions remain account-wide; positions remain separately product-scoped.
- Retains cursor pagination and fail-closed behavior when pagination metadata is missing, repeated or exceeds the page cap.
- Carries the exact venue filter parameters into the snapshot and coordinator report.
- Distinguishes `VENUE_START_END_TIME_FILTER_PLUS_CLIENT_SIDE_AUDIT` from legacy client-only selection.
- Does not claim venue historical exhaustiveness: pagination completion is not proof that the API returned every event, and no authenticated account exercise was performed.

## Verification
- Focused reconciliation / historical evidence regression: 91 passed.
- Secret-scan tests: 21 passed, 18 subtests passed.
- `compileall`: PASS.
- Strict release manifest verification: PASS, 0 problems.
- Repository test collection: 4,949 collected (collection only; full suite not run).
- No authenticated Delta API calls, no exchange writes, no cancellations, no position modifications.

## Remaining limitations
- No live authenticated venue request was made; exact runtime acceptance and account-specific behavior remain unverified.
- The overlap is a query-boundary expansion, not a repeated independent-window comparison. Late-arriving events across separate captures still require durable cross-capture comparison and a venue/account exercise.
- The positions endpoint is a current snapshot and cannot establish historical position continuity by itself.
- The API's returned page set is treated as complete only when the cursor chain terminates cleanly; this is transport-level pagination completeness, not an independently certified venue archive.
- Full test suite and exact pinned Python/dependency contract remain unverified.

## Decision
`HOLD` — `NOT_PRODUCTION_READY`. Strategy edge remains `NOT_ESTABLISHED`. Automatic resume remains `NEVER`.
