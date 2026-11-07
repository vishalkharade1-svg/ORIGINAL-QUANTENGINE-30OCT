# Phase133 Testnet probe (EXECUTED 2026-10-15, read-only, no orders)

CMD (values never printed): bounded `run_phase85_delta_testnet_capture.py --environment india_testnet --symbol BTCUSD --duration 10 --min-observations 1 --output-dir research/captures/phase133_probe` with `.env`-loaded `DELTA_INDIA_TESTNET_*` only.

## Result (genuine TESTNET_EVIDENCE)

- DNS: `cdn-ind.testnet.deltaex.org`, `socket-ind-pub.testnet.deltaex.org`, `socket-ind.testnet.deltaex.org` all RESOLVED.
- Public L2: CAPTURED (12 observations).
- Authenticated REST fills: CAPTURED (8 fills, `rest_fills.json` 3072 B).
- Private WS: `FAILED_OR_NO_FILLS` (`no v2/user_trades frames`) — honest negative evidence, not synthesized.
- Reconciliation: BLOCKED (needs WS match). Economic certification: BLOCKED.
- `order_placement: DISABLED`, `credentials_persisted: false`, `production_ready: false`.

## Artifacts (SHA-256 prefix / size)

- `l2/capture_manifest.json` 00818a133e70 / 573 B
- `l2/delta_ob_updates_archive.json` bfc8de8df0c3 / 75772 B
- `l2/market_friction_evidence.json` afc8b732ad76 / 3338 B
- `phase85_capture_report.json` 77a51d9c5a93 / 1113 B
- `rest_fills.json` e32287a40fea / 3072 B

Scanner on capture dir: SECRET_SCAN_PASS. No secret values in report, logs, or artifacts. `.env` never packaged/committed.

## Blocker update

- E-authenticated-REST: RESOLVED for this symbol/window (8 fills). WS binding + fee/funding certification remain BLOCKED (need WS frames + fee window + simultaneous friction).
- No orders placed. Further captures need only bounded read-only authorization; any order experiment needs separate explicit approval.
