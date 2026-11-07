# Privacy review — Phase 161

Trust position: UNCHANGED from Phase160 (the scanner-model boundary stays
closed; this cycle changed the environment and the evidence, not the policy).

What ships, and why it is ship-able:

* The raw restricted captures under `research/captures/` (the six restricted
  evidence paths declared in the privacy policy) carry the operator's account
  id and venue order ids **deliberately**: they are the evidence of record —
  what actually happened on the operator's paper/Testnet sessions.  They ship
  inside the release package and are integrity-covered by
  `BUILD_MANIFEST.sha256`, so they travel with evidence, not by accident.
* The account identifier is allowed in exactly the enumerated raw restricted
  captures and nowhere else (`privacy.ACCOUNT_IDENTIFIER_VALUE` policy in
  `scripts/security/scan_privacy.py`; contract:
  `tests/test_phase158_privacy_contract.py`).
* Raw venue order ids found outside the captures are split against the input
  archive's inventory (`reports/PHASE158_INPUT_INVENTORY.sha256`): a finding in
  an artifact byte-identical to its Phase157 input member is **historical** —
  enumerated and reported, never rewritten; anything new is a scanning failure.
  This run re-classified the sealed historical carriers; the full enumeration
  is in `reports/PHASE161_PRIVACY_SCAN.json`.
* No credential material and no credential-bearing path exists anywhere
  (`SECRET_SCAN_PASS` — see `reports/PHASE161_SECURITY_SCAN.md`).

Publication clearance:

```
Publication clearance: none
```

`PRIVACY_SCAN_PASS` is scoped to this restricted package. The scan report
carries `publication_clearance: "NOT_CLEARED"` with a reason, and neither the
scan nor this review is a clearance to publish or redistribute the archive: both
the raw private captures and the sealed historical order-id carriers would have
to be dealt with first. A reader who takes a green scan verdict as
publication clearance has misread it — the revision-1 independent audit did
exactly that, which is why the statement is explicit in the scan output and in
this review. In one line: **this package is not cleared for publication.**

Phase161 changes to the enforcement machinery: none — and that is the point.

1. The scanners (`scripts/security/scan_secrets.py`,
   `scripts/security/scan_privacy.py`) and the shared decoder
   (`scripts/security/text_decode.py`) are byte-carried from Phase160: the
   content-decoding boundary closure and rule E content coverage stay exactly
   as closed.  This cycle re-ran them under the adopted environment
   (python-dotenv 1.2.2 / pyarrow 23.0.1 / pytest 9.0.3) against the same
   carried member set plus this cycle's records.
2. Test fixtures remain **synthetic** (the `9000001234` fixture rule of
   Phase159 is carried; see `reports/PHASE159_HARDENING.json` — preserved
   unchanged).
3. This record and the whole Phase161 record set are themselves subject to the
   rules: no harvested value is reproduced in prose, and the scanners re-run
   against the final tree — they would flag this file if it were.

Nothing about what ships changed in Phase161: the same member set ships, plus
this cycle's records; the environment moved, the policy and the enforcement
machinery did not.
