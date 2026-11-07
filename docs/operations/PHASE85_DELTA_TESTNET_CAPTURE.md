# Delta Testnet evidence capture — operator runbook (updated 2026-10-11, Phases 86–92)

This is a **non-trading** workflow. No runner herein submits, modifies, or
cancels orders. Order placement stays hard-disabled in code.

## Prerequisites

1. Network path to the three Testnet hosts (`cdn-ind.testnet.deltaex.org`,
   `socket-ind.testnet.deltaex.org`, `socket-ind-pub.testnet.deltaex.org`).
   The runner probes DNS first and stops before any authenticated request
   when resolution fails.
2. A fresh **Demo-site (Testnet)** key pair with **read permission**
   (`/v2/fills`, `v2/user_trades`). Trading permission is not needed.
   Rotate/revoke any key ever exposed in chat, tickets, or logs.
3. Never commit secrets. Preferred: process-environment injection
   (`DELTA_API_KEY` / `DELTA_API_SECRET`). Local alternative: the
   gitignored root `.env` (empty template; fill locally, never share).
   `.env.example` must stay placeholder-only.

## Public-only capture (no credentials needed)

```sh
python scripts/run_phase85_delta_testnet_capture.py --environment india_testnet --symbol BTCUSD --duration 30 --output-dir research/captures/<label> --capture-id <label>
```

Public L2 proceeds without credentials; REST/private legs report
`BLOCKED_CREDENTIALS_NOT_CONFIGURED` and are skipped without network use.

## Authenticated capture (Demo key configured)

Same command with the key pair present. Expected outcomes:

| Report field | Meaning |
|---|---|
| `real_public_l2: CAPTURED` | Genuine ob_updates frames, hash-bound archive |
| `authenticated_rest_fills: EMPTY_RESPONSE` | Key valid, account has no rows for the symbol — honest negative evidence |
| `authenticated_rest_fills: FAILED (401)` | Key unknown to Testnet (production key or inactive) — do NOT retry against production |
| `private_ws_fills: FAILED_OR_NO_FILLS` | No `v2/user_trades` frames in-window (no account activity), or auth rejection (see error) |
| `rest_ws_reconciliation: MATCHED` | Only when both legs yield identical fill sets |

## Current state (2026-10-10/11)

- DNS resolves in the operator environment (earlier packaged-env DNS block lifted).
- Demo key verified (REST 200 + WS key-auth OK). The Demo account holds no
  fills, so reconciliation and economic certification stay BLOCKED.
- REAL evidence banked: BTCUSD L2 ×3 (59/33/34 obs, 0 gaps), ETHUSD L2 ×1
  (19 obs, thin book), Testnet BTCUSD contract snapshot (647-product catalog).
- No fills may be manufactured via orders without a separate, explicit,
  bounded Testnet order-experiment authorization.

## Order experiments (authorized invocations only)

Three executed runs (Phases 114/115/120/125) established this venue-verified
procedure. No experiment runs without explicit per-invocation operator
authorization recorded with its exact bounds.

1. Dry-run first: product re-verified live, account flat (positions +
   open orders), touch read, notional under the hard cap. Any refusal
   stops everything.
2. Venue shapes that differ from older assumptions:
   - Cancel is `DELETE /v2/orders` + `{id, product_id}` body; the
     `/{id}` route 404s. Cancels are verified by state re-query, and
     cleanup re-checks the open count (never assume).
   - `/v2/positions` requires `product_id` and returns one object.
   - CaptureIdentity accepts only PRODUCTION/SANDBOX (Testnet = SANDBOX).
   - Fill rows carry `product_symbol` + ISO-8601 timestamps; the fills
     endpoint ignores the symbol filter (client-side per-symbol split).
   - `v2/user_trades` frames carry microsecond `t` and NO sequence
     numbers; REST is the completeness authority.
3. Keys need Trading permission AND a whitelisted egress IP
   (`ip_not_whitelisted_for_api_key` names the IP). Failures must be
   read from response bodies, not just status codes.
4. Concurrent L2 + private WS during placement yields reconcilable,
   bindable fills. Limit-at-touch fills measured 0.0 slippage vs touch.

## Standing rules

- Testnet/production endpoint mismatches fail closed; production retry of a
  Testnet-rejected key is forbidden by scope.
- A hash proves stored-byte integrity, not venue provenance by itself.
- `production_ready` remains false. Testnet evidence never implies
  production profitability.
