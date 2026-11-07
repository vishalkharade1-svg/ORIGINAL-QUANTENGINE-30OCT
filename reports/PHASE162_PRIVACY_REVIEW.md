# Privacy review — Phase 162

Trust position: **RESTRICTED EVIDENCE PACKAGE**.

This package contains empirical evidence captured on Delta Exchange India Testnet, including raw private WebSocket and REST execution records.

What ships, and why it is ship-able:

* The raw restricted captures under `research/captures/` carry the operator's account id and venue order ids **deliberately**: they are the primary evidence of record for empirical protocol and reconciliation verification. They ship inside the release package and are integrity-covered by `BUILD_MANIFEST.sha256`.
* The account identifier is allowed in exactly the eight enumerated raw restricted captures:
  1. `research/captures/phase146_recon/private_ws_archive.json`: archived private websocket frames for the Phase146 reconciled experiment
  2. `research/captures/phase146_recon/private_ws_frames.json`: private websocket fill frames (v2/user_trades) for Phase146
  3. `research/captures/phase147_ledger/wallet_100.json`: raw wallet ledger pull backing the Phase147 fee/commission totals
  4. `research/captures/phase152_recon2/private_ws_archive.json`: archived private websocket frames for the Phase152 reconciled experiment
  5. `research/captures/phase152_recon2/private_ws_frames.json`: private websocket fill frames (v2/user_trades) for Phase152
  6. `research/captures/phase153_ledger/wallet_100.json`: raw wallet ledger pull backing the Phase153 fee/commission totals
  7. `research/captures/phase162_recon/private_ws_archive.json`: archived private websocket frames for the Phase162 reconciled experiment
  8. `research/captures/phase162_recon/private_ws_frames.json`: private websocket fill frames (v2/user_trades) for Phase162
* Raw venue order ids found outside the raw captures are split against the input archive's inventory (`reports/PHASE158_INPUT_INVENTORY.sha256`): findings in sealed historical records byte-identical to their historical input are enumerated below, never rewritten:
  - `reports/PHASE134_ORDER_EXPERIMENT.md`
  - `reports/PHASE136_MIXED_TYPE_PILOT.md`
  - `reports/PHASE137_SHORT_STOP_PILOTS.md`
  - `reports/PHASE138_SHORT_MARKET.md`
  - `reports/PHASE146_MATCHED_RECON.md`
  - `reports/PHASE150_BTCUSD_MARKET.md`
  - `reports/PHASE151_BTCUSD_SHORT.md`
  - `reports/PHASE152_SWEEP.md`
  - `research/results/phase114_order_experiment.json`
  - `research/results/phase116_ws_reconciliation.json`
  - `research/results/phase120_clean_nofill.json`
  - `research/results/phase124_cancel_shape_fix.json`
  - `research/results/phase125_full_reconciled_run.json`
* The 11 declared opaque binary members (10 historical zip archives under `research/evidence/` and `_archive/`, plus 1 parquet dataset `data/raw/topup_features_5m.parquet`) are covered by Rule E of the privacy scanner. All 11 binaries and their internal archive members have been independently inspected and confirmed clean of any account identifier or credentials.
* No credential material and no credential-bearing path exists anywhere in the tree (`SECRET_SCAN_PASS`).

## Publication clearance

```
Publication clearance: none
```

`PRIVACY_SCAN_PASS` is scoped strictly to this restricted evidence package. The scan report carries `publication_clearance: "NOT_CLEARED"` with reasons stated. Neither the scan nor this review constitutes clearance to publish or redistribute the archive: both the raw private captures and the sealed historical order-id carriers would require sanitisation. **This package is not cleared for publication.**
