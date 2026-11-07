# Privacy review — Phase 160

Trust position: UNCHANGED from Phase159, now enforced with the boundary closure
the Phase159 vendor-audit handoff declared.

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
  is in `reports/PHASE160_PRIVACY_SCAN.json`.
* No credential material and no credential-bearing path exists anywhere
  (`SECRET_SCAN_PASS` — see `reports/PHASE160_SECURITY_SCAN.md`).

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

Phase160 changes to the enforcement machinery (work, not policy):

1. Both scanners decode by **content**, not by a suffix allowlist
   (`scripts/security/text_decode.py`): UTF-8 with optional BOM, UTF-16 LE/BE
   with or without BOM, UTF-32 with BOM.  This closes the model boundary the
   Phase159 handoff declared: the 12 carried UTF-16LE members and the
   suffix-excluded members were invisible to every content rule; they are now
   content-inspected and probe clean (zero hits for the account identifier,
   the harvested order ids and credential patterns).  Regression-pinned on
   both scanners.
2. **Coverage is now a rule, not an assumption.**  Rule E: every member is
   either content-inspected or a declared opaque class (`*.zip`, `*.parquet`).
   An undeclared binary member fails the scan (`opaque_member_not_declared`);
   the declared members are enumerated by path in the scan output and in the
   report's `content_coverage` block (schema `quantengine.privacy-scan.v2`).
   The release's containers can no longer sit silently outside the scan.
3. Test fixtures remain **synthetic** (the `9000001234` fixture rule of
   Phase159 is carried; see `reports/PHASE159_HARDENING.json` — preserved
   unchanged).
4. This record and the whole Phase160 record set are themselves subject to the
   rules: no harvested value is reproduced in prose, and the scanners re-run
   against the final tree — they would flag this file if it were.

Nothing about what ships changed in Phase160: the same member set ships, plus
this cycle's records; the scanners got harder, the declared boundary closed,
and the fixtures stay clean.
