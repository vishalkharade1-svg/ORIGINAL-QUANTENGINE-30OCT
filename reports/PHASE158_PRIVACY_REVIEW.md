# Privacy review — Phase 158

## What class of package this is

This archive is a **restricted evidence package**, not a distributable. It
deliberately ships raw private venue captures, because they are the evidence of
record for the reconciled experiments and the fee/commission totals that the
economics ledger cites. Two categories of identifier travel with it:

1. the operator's **account identifier**, confined to six enumerated raw
   captures (rule A below);
2. raw **venue order ids**, present in the raw captures and, historically, in
   sealed experiment journals that document those specific orders (rule B).

Phase157 described the captures only as "restricted", which could be read as
*excluded*. They are not excluded: they ship, deliberately. This review states
the position precisely and `scripts/security/scan_privacy.py` enforces it
mechanically.

## Rule A — account-identifier confinement (strict)

The account identifier may appear in exactly these six files and nowhere else.
Each is a raw capture that cannot be replaced by a summary without destroying
the provenance chain the ledger depends on:

| path | bytes | sha256 | why it is allowed |
|---|---|---|---|
| `research/captures/phase146_recon/private_ws_archive.json` | 1,572 | `0949135b8a3988a384d21be2eea1cb13e98290b3dfa0a9f606d9cdb3d5d216c3` | archived private websocket frames for the Phase146 reconciled experiment |
| `research/captures/phase146_recon/private_ws_frames.json` | 997 | `39356f6bb893348a957216cf71cc927d25f9bac2204c37f5e10cbbcf71692064` | private websocket fill frames (v2/user_trades) for Phase146 |
| `research/captures/phase147_ledger/wallet_100.json` | 7,027 | `5aa666cb4d82a6d3c1710e30e735d61f883c2b0672125d3f5870749bebc243eb` | raw wallet ledger pull backing the Phase147 fee/commission totals |
| `research/captures/phase152_recon2/private_ws_archive.json` | 1,574 | `6b9f586726d61f77e413a070180b5d8980da218f3cdb7c8035cccfe49b2e64b3` | archived private websocket frames for the Phase152 reconciled experiment |
| `research/captures/phase152_recon2/private_ws_frames.json` | 999 | `ffdcfc1d4631be3c19d24cce1b46b2ef44543f335a2de472c951d4ed62f035f6` | private websocket fill frames (v2/user_trades) for Phase152 |
| `research/captures/phase153_ledger/wallet_100.json` | 15,527 | `0858922de6cb11e8dbb5cbd2e4f9e0d050c20f1a31d757597a218e4b8f24d079` | raw wallet ledger pull backing the Phase153 fee/commission totals |

The scan enforces **set equality**, not merely "no violations": the set of files
that actually carry the identifier must equal the allowlist exactly, so the
allowlist can neither go stale nor be quietly widened. The identifier value
itself is parameterised in `scripts/security/scan_privacy.py` (assembled at run
time, so the scanner's own source is not a carrier) and is not repeated in any
report, document or prompt in this archive.

## Rule B — raw order ids: new leakage versus historical baseline

The scanner collects every numeric venue order id that appears in
`research/captures/**` — 38 distinct ids across 21 capture files at this
revision. A finding under `reports/`, `docs/` or `research/results/` is then
classified against `reports/PHASE158_INPUT_INVENTORY.sha256`:

* **new leakage** — the id appears in a file that is *not* byte-identical to its
  input-archive member (or is new in this phase). The scan fails. This is the
  machine check behind "raw restricted, reports aggregate-only" for everything
  Phase158 writes.
* **historical baseline** — the id appears in a file that is byte-identical to
  the input archive's member. Reported and enumerated here, **never rewritten**.

Phase158 introduces **zero** new leakage. The historical baseline is 13 sealed
files (17 finding lines):

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

These are the experiment journals of Phases 114–152; they quote the order ids of
the orders they document, which is how a trading journal is normally written.
Phase158 does not edit them — rewriting sealed evidence to satisfy a scanner
would destroy the very record the scanner exists to protect — and it does not
pretend they are clean either. A *distribution* would have to sanitise them;
this package is not a distribution, and says so.

## Publication clearance: none

`PRIVACY_SCAN_PASS` is scoped to this restricted package. The scan report
carries `publication_clearance: "NOT_CLEARED"` with a reason, and neither the
scan nor this review is a clearance to publish or redistribute the archive:
both the six raw private captures and the 13 sealed historical order-id
carriers would have to be dealt with first (see "What a distributable would
require"). A reader who takes a green scan verdict as publication clearance has
misread it — the revision-1 independent audit did exactly that, which is why
the statement is now explicit in the scan output, this review and the audit
prompt.

In one line: **this package is not cleared for publication.**

## Preservation — nothing was sanitised, redacted or re-captured

All six restricted captures are **byte-identical** to their Phase157 archive
members (hash compared against the input archive itself, not against a note):

| path | identical to Phase157 member |
|---|---|
| `research/captures/phase146_recon/private_ws_archive.json` | yes |
| `research/captures/phase146_recon/private_ws_frames.json` | yes |
| `research/captures/phase147_ledger/wallet_100.json` | yes |
| `research/captures/phase152_recon2/private_ws_archive.json` | yes |
| `research/captures/phase152_recon2/private_ws_frames.json` | yes |
| `research/captures/phase153_ledger/wallet_100.json` | yes |

No sanitised derivative exists anywhere in the tree, and all six are covered by
`BUILD_MANIFEST.sha256`, so they ship with integrity evidence rather than by
accident.

## Scan commands and results (worktree, 2026-10-17)

```
python scripts/security/scan_privacy.py --root .
    PRIVACY_SCAN_CLEARANCE NOT_CLEARED (restricted evidence package; not
      sanitised for redistribution -- PRIVACY_SCAN_PASS is not a publication
      clearance)
    PRIVACY_SCAN_PASS
    (0 violations; account-identifier carriers == the six enumerated captures;
     13 historical order-id carriers / 17 findings enumerated as notes;
     0 new leakage)

python scripts/security/scan_secrets.py
    SECRET_SCAN_PASS
```

Machine-readable record of the same run:
`reports/PHASE158_PRIVACY_SCAN.json`.

Negative controls live in `tests/test_phase158_privacy_contract.py`: the
identifier planted in a report is reported; the identifier inside an allowlisted
capture is not; a *new* aggregate file carrying a raw order id is classified as
new leakage and fails; a byte-identical input member is classified historical;
an *edited* historical file forfeits that classification and fails.

## What a distributable would require (deliberately not done here)

1. remove or redact the six private captures — which would break the byte-level
   provenance the ledger's fee/commission totals rest on;
2. sanitise the 13 sealed journals;
3. re-run this scan and the secret scan on the result;
4. re-issue the ledger's provenance statements against the sanitised copies.

That is a different artifact with different evidence, and it is out of scope for
a release-repair phase. This package keeps the evidence of record intact and
declares its class plainly instead.

## Gate separation

* Secret scan (credentials): `reports/PHASE158_SECURITY_SCAN.md`
* Privacy review (this file): account identifiers, private payloads, order ids
* Source integrity (manifest): `reports/PHASE158_MANIFEST_AUDIT.json`
* Dependency security: `reports/PHASE158_DEPENDENCY_REVIEW.md`

A clean result in one of these is not a result in another; they are reported
separately on purpose.
