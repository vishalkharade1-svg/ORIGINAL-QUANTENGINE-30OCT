# Phase 202 — Account Adjustment and Fill-Type Reconciliation Audit

## Scope
Extend the Phase 199 read-only Delta snapshot and Phase 200 coordinator with account wallet-transaction evidence and explicit fill-type review. This phase is diagnostic only. No network calls, order writes, cancellations, or position modifications were performed.

## Official venue documentation reviewed
- Delta REST API documentation: `GET /v2/wallet/transactions` supports cursor pagination (`after`, `before`, `page_size`) and returns transaction `id`, `amount`, `transaction_type`, `meta_data`, optional `product_id`, `asset_id`, `asset_symbol`, and `created_at`.
- Documented transaction types include funding, settlement, liquidation_fee, commission, commission_rebate, fill_appropriation, revert, and other account credits/debits.
- Delta fill schema enumerates `normal`, `adl`, `liquidation`, `settlement`, and `otc` fill types.
- Delta position schema documents signed size: negative for short and positive for long. This supports the sign convention, but does not prove every account mode or reconcile every exceptional event.

## Implementation
- `DeltaReconciliationSnapshot` now includes `wallet_transactions`.
- `DeltaReconciliationReadAdapter.capture()` performs an authenticated GET to `/v2/wallet/transactions` and follows the documented `meta.after` cursor. The wallet endpoint is account-wide, so no unsupported product filter is sent.
- Wallet transaction rows require stable `id`, `amount`, `transaction_type`, and `created_at`; product linkage remains optional because the venue schema marks it optional.
- The wallet transaction endpoint is now a required completeness component. Missing pagination metadata, transport errors, repeated cursors, or the page safety cap prevent a complete snapshot.
- The coordinator retains product-linked exceptional events and unscoped exceptional events. It never applies wallet transaction `amount` to contract quantity.
- Fill evidence with a non-normal `fill_type` or missing `fill_type` is separately surfaced for operator review. The signed BUY-minus-SELL arithmetic remains a diagnostic quantity check, not an automatic clearance.
- `safe_to_resume_submissions` remains false and `automatic_action` remains NONE.

## Classification policy
Exceptional wallet transaction types currently flagged for review:
`funding`, `settlement`, `liquidation_fee`, `fill_appropriation`, `revert`, `trading_credits_paid_liquidation_fee`.

Fill types other than `normal`, plus missing fill type, are flagged for review. They are not silently discarded from the position quantity reconstruction; the review flag prevents a matching quantity from being treated as a clean account state.

## Tests and verification
- Focused regression: 79 passed across Phase 191/192 reconciliation regressions and Phase 198–201 recovery/reconciliation modules.
- Repository collection: 4,935 collected (collection only; not a full-suite pass).
- Manifest strict verification: PASS, zero problems.
- Secret scan: PASS.
- Fresh extraction verification: PASS (recorded separately).
- Full repository suite: NOT RUN.
- Pinned Python 3.12 environment: NOT CERTIFIED; current environment remains Python 3.13.5 / pytest 9.0.2 with pyarrow unavailable.
- Authenticated venue exercise: NOT PERFORMED.
- Exchange network calls and order writes: NONE.

## Limitations
- Wallet transaction history is account-wide; rows without product IDs cannot be reliably attributed to a product. The coordinator therefore blocks on unscoped exceptional events.
- The adapter's bounded pagination cap can make old/large account histories incomplete. An incomplete wallet history keeps the entire reconciliation snapshot incomplete.
- Wallet transaction amounts are asset-denominated cash ledger entries and are not contract quantities. No arithmetic conversion is attempted.
- Position quantity semantics are supported by official docs for signed long/short sizes, but account-mode-specific behavior and all possible manual adjustments are not fully certified.
- No authenticated live/testnet account was used to validate the current response payloads.

## Decision
HOLD. This phase improves forensic evidence and fail-closed classification; it does not authorize order submissions or establish strategy edge.
