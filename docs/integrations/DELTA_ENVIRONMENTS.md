# Delta Environments — Authority & Sandbox Boundary

Status: sandbox endpoint VERIFIED (live, responding, demo-shaped);
sandbox credentials PRESENT but venue-REJECTED (2026-09-25 live
probe: variables loaded, correct testnet endpoint, canonical
signing, HTTP 401 `invalid_api_key` — the key itself is not
testnet-accepted; not a signing/timestamp/IP/endpoint defect).
No account/contract/economics/lifecycle evidence obtainable.
Canonical gate artifact:
`data/fixtures/delta/sandbox_external_evidence_20260925.json`
(`SANDBOX_EXTERNAL_EVIDENCE_BLOCKED` / `AUTHENTICATION_REJECTED`,
deterministic id `075e0f2f…`; builder
`scripts/build_sandbox_external_evidence.py`; schema
`core/exchanges/delta/sandbox_evidence.py`). Full G0–G14 gate
matrix: `data/fixtures/delta/evidence_gate_matrix_20260925.json`
(matrix id `934b3b25…`; model `core/evidence/gates.py`, runner
`scripts/evaluate_evidence_gates.py`): G0/G1/G8/G9/G10/G11/G12/
G14 VERIFIED; G2 BLOCKED (venue rejection recorded);
G3/G5/G6 BLOCKED_BY_PREREQUISITE; G4/G7 independently BLOCKED
(no fresh observation); G13 BLOCKED/EXECUTED (9M suites run:
92 tests, 87 pass, 5 pre-existing strategy-digest pins).
External aggregate `SANDBOX_EXTERNAL_EVIDENCE_BLOCKED`;
`is_production_ready = FALSE` throughout.

## Supported environments

| Environment | REST endpoint | Status |
|---|---|---|
| `PRODUCTION` | `https://api.delta.exchange` | Pre-existing default, unchanged |
| `SANDBOX` | `https://testnet-api.delta.exchange` | Verified live 2026-09-23 (public catalog only) |
| `UNKNOWN` (incl. unset) | none — resolution refused | Fail-closed |

## Endpoint evidence (credential-free, read-only)

- Official Delta API docs (`https://docs.delta.exchange/`, retrieved
  2026-09-23) document a testnet/demo environment with separate
  endpoints and environment-bound API keys (demo keys work only on
  testnet; India keys only on production). The docs explicitly name
  the India testnet host (`cdn-ind.testnet.deltaex.org`).
- Direct probing (public `/v2/products`, no auth):
  - `api.delta.exchange`: 408 products, `BTCUSDT` perp, USDT/USDT,
    commissions 0.0001/0.0001 → PRODUCTION Global.
  - `testnet-api.delta.exchange`: 285 products, `BTCUSDT` perp,
    USDT/USDT, commissions **0/0** → demo-shaped Global catalog
    (distinct product set, zero-fee simulation marker).
  - `cdn-ind.testnet.deltaex.org`: 734 products, `BTCUSD`
    (USD-settled) → India demo venue (different universe; NOT this
    repository's venue).
- Sandbox WebSocket host: UNVERIFIED — no testnet WS host confirmed;
  sandbox WS resolution is refused until one is verified.

## Authority

One mapping: `core/exchanges/delta/delta_environments.py`.
Environment selection is explicit (`DELTA_ENVIRONMENT`) and
observable; there is no credential-sniffing fallback. Existing
client constructors keep exact production defaults (pinned).

## Credential separation

- Production: `DELTA_API_KEY` / `DELTA_API_SECRET` (unchanged).
- Sandbox: `DELTA_SANDBOX_API_KEY` / `DELTA_SANDBOX_API_SECRET`
  (new, unset by default → `SANDBOX_CREDENTIALS = UNAVAILABLE`).
- Sandbox resolution never substitutes production keys (venue binds
  keys to environments); missing keys refuse instead of falling back.

## Fail-closed matrix (all tested)

UNKNOWN→refuse; SANDBOX+production host→refuse;
PRODUCTION+sandbox host→refuse; missing/malformed endpoint→refuse;
sandbox WS→refuse; no implicit fallback (removing config raises).

## What sandbox verification does NOT grant

Sandbox evidence is evidence, never production authorization:

```text
is_production_ready = FALSE
NOT_LIVE_READY = TRUE
```

The public product snapshot
(`observed_global_products_public_20260923.json`) remains
parser/ingestion evidence only: public ≠ private ≠ sandbox ≠
production authority.
