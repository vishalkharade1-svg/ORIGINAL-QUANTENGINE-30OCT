# Phase 196 — HTTP-Method-Bound Order Write Authority Audit

Date: 2026-10-30

## Decision

**IMPLEMENTED AND FOCUSED-TESTED; RELEASE GATE REMAINS HOLD.** Phase 195 bound authority to the exact payload, endpoint and venue URL. The next offline audit found that the token did not bind the HTTP method, even though Delta uses both `POST /v2/orders` for order placement and `DELETE /v2/orders` for cancellation. This phase binds the authorization to the operation as well as the payload.

## Changes

- `core/exchanges/delta/write_authority.py`
  - `WriteAuthorityToken` now carries the authorized HTTP method.
  - Production tokens bind `POST` or `DELETE`; offline-test tokens remain marked `ANY` but are refused at the production signed-REST boundary.
  - Method inference recognizes the exact cancellation payload shape (`id`, `product_id`); malformed order payloads default to placement and are checked against required fields.
  - Testnet `POST` authorization requires `product_id`, `size`, and `side`; side must be `buy` or `sell`; size must be finite, positive, and equal to the preflight-authorized size; post-only and reserved-order details remain enforced.
  - Testnet `DELETE` authorization accepts only the exact `id`/`product_id` cancellation shape and requires a positive order ID.
  - Adapter/REST validation checks the method alongside the endpoint, kind, host, payload digest and one-time nonce.
- `core/exchanges/delta/delta_auth.py`: the signed REST `post()` and `delete()` boundaries pass their actual HTTP method into authority consumption.
- `core/exchanges/delta/delta_exchange.py`: order and cancellation adapter checks require `POST` and `DELETE`, respectively.
- `core/execution/order_executor.py`: live cancellation authority is explicitly bound to `DELETE`.
- `tests/test_phase193b_authority.py`: added adversarial tests for POST-token/DELETE reuse, DELETE-token/POST reuse, and malformed order payloads missing size.

## Verification

- Focused authorization, lifecycle, Delta authority and adapter suite: **133 passed, 9 subtests passed**, 2 multiprocessing deprecation warnings, 2.88 seconds. The snapshot guard started pristine and ended with no restores or added files.
- Expanded Delta authentication/signing/order-executor regression: **93 passed**, 1.20 seconds; snapshot guard pristine.
- Manifest regeneration and verification: **PASS, 0 problems**.
- Secret scan: recorded separately in the release gates after final regeneration.
- Python compilation for modified production modules: PASS.
- Python 3.12 setup: **BLOCKED**. `uv python install 3.12` failed after retries because DNS/network access to the Python build download host was unavailable. No fake runtime/version was used.
- Full suite: **NOT RUN in Phase 196**. The documented pinned runtime remains uncertified; prior Phase 195 full-suite attempt timed out and is not treated as a pass.

## Safety and scope

- No exchange network calls or order writes were performed.
- No real operator public key or signed authorization was provisioned.
- This phase does not prove that cancellation IDs belong to the experiment that created them; order-ID ownership and reconciliation remain separate audit items.
- Operator-key provisioning, historical credential rotation/revocation, and account review remain unverified.
- Strategy edge remains **NOT ESTABLISHED**.
- `RELEASE_GATE = HOLD`; `NOT_PRODUCTION_READY`.
