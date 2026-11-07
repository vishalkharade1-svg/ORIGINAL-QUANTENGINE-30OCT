# Phase 204 Release Record

Phase 204 implements Delta-documented venue-side time filtering for authenticated, read-only reconciliation GETs.

- Order, order-history, fill and wallet-transaction requests now include inclusive `start_time` / `end_time` in epoch microseconds when a window is supplied.
- Requested overlap expands both boundaries.
- Orders/history/fills use documented `product_ids`; wallet transactions remain account-wide; positions remain a current product-scoped snapshot.
- Coordinator evidence labels the actual venue filter and still does not certify historical exhaustiveness.

Verification: 91 focused tests passed; 21 secret-scan tests passed with 18 subtests; compileall passed; strict manifest passed; 4,949 tests collected only. Full suite not run. No authenticated venue calls or exchange writes were performed.

Decision: HOLD / NOT_PRODUCTION_READY. Strategy edge NOT_ESTABLISHED. Operator authorization and venue exercise remain outstanding.
