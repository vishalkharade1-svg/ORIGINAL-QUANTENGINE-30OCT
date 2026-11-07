# Privacy review — Phase 183

## What class of package this is

This archive is a **restricted evidence package**, not a distributable. It
deliberately ships raw private venue captures, because they are the evidence of
record for the reconciled experiments and the fee/commission totals that the
economics ledger cites. Two categories of identifier travel with it:

1. the operator's **account identifier**, confined to twelve enumerated raw
   captures (rule A below);
2. raw **venue order ids**, present in the raw captures and, historically, in
   sealed experiment journals that document those specific orders (rule B).

This review states the position precisely and `scripts/security/scan_privacy.py` enforces it mechanically.

## Rule A — account-identifier confinement (strict)

The account identifier may appear in exactly these twelve files and nowhere else.
Each is a raw capture that cannot be replaced by a summary without destroying
the provenance chain the ledger depends on:

| path | why it is allowed |
|---|---|
| `research/captures/phase146_recon/private_ws_archive.json` | archived private websocket frames for the Phase146 reconciled experiment |
| `research/captures/phase146_recon/private_ws_frames.json` | private websocket fill frames (v2/user_trades) for Phase146 |
| `research/captures/phase147_ledger/wallet_100.json` | raw wallet ledger pull backing the Phase147 fee/commission totals |
| `research/captures/phase152_recon2/private_ws_archive.json` | archived private websocket frames for the Phase152 reconciled experiment |
| `research/captures/phase152_recon2/private_ws_frames.json` | private websocket fill frames (v2/user_trades) for Phase152 |
| `research/captures/phase153_ledger/wallet_100.json` | raw wallet ledger pull backing the Phase153 fee/commission totals |
| `research/captures/phase162_recon/private_ws_archive.json` | archived private websocket frames for the Phase162 reconciled experiment |
| `research/captures/phase162_recon/private_ws_frames.json` | private websocket fill frames (v2/user_trades) for Phase162 |
| `research/captures/phase167_recon/private_ws_archive.json` | archived private websocket frames for the Phase167 reconciled experiment |
| `research/captures/phase167_recon/private_ws_frames.json` | private websocket fill frames (v2/user_trades) for Phase167 |
| `research/captures/phase168_ledger/balances.json` | authoritative wallet balances backing the Phase168 equity reconciliation |
| `research/captures/phase168_ledger/wallet_100.json` | authoritative wallet ledger pull backing the Phase168 fee, cashflow, and balance reconciliation |

The scan enforces **set equality**, not merely "no violations": the set of files
that actually carry the identifier must equal the allowlist exactly. The identifier value
itself is parameterised in `scripts/security/scan_privacy.py` and is not repeated in any
report, document or prompt in this archive.

## Rule B — raw order ids: new leakage versus historical baseline

The scanner collects every numeric venue order id that appears in
`research/captures/**`. A finding under `reports/`, `docs/` or `research/results/` is then
classified against the historical inventory:

* **new leakage** — the id appears in a file that is *not* byte-identical to its
  historical record. The scan fails.
* **historical baseline** — the id appears in a file that is byte-identical to
  sealed archives. Reported and enumerated here, **never rewritten**.

Phase 183 introduces **zero** new leakage. The historical baseline is 13 sealed files:

```
reports/PHASE134_ORDER_EXPERIMENT.md
reports/PHASE136_MIXED_TYPE_PILOT.md
reports/PHASE137_SHORT_STOP_PILOTS.md
reports/PHASE138_SHORT_MARKET.md
reports/PHASE146_MATCHED_RECON.md
reports/PHASE150_BTCUSD_MARKET.md
reports/PHASE151_BTCUSD_SHORT.md
reports/PHASE152_SWEEP.md
research/results/phase114_order_experiment.json
research/results/phase116_ws_reconciliation.json
research/results/phase120_clean_nofill.json
research/results/phase124_cancel_shape_fix.json
research/results/phase125_full_reconciled_run.json
```

## Publication clearance: none

`PRIVACY_SCAN_PASS` is scoped to this restricted package. The scan report
carries `publication_clearance: "NOT_CLEARED"` with a reason, and neither the
scan nor this review is a clearance to publish or redistribute the archive:
both the raw private captures and the 13 sealed historical order-id
carriers would have to be dealt with first.

In one line: **this package is not cleared for publication.**

## Gate separation

* Secret scan (credentials): `scripts/security/scan_secrets.py` -> `SECRET_SCAN_PASS`
* Privacy review (this file): account identifiers, private payloads, order ids -> `PRIVACY_SCAN_PASS`
* Source integrity (manifest): `BUILD_MANIFEST.sha256`
* System posture: `NOT_PRODUCTION_READY` | `EDGE NOT ESTABLISHED`
