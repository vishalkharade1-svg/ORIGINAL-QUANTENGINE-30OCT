# Privacy review — Phase 159

Trust position: UNCHANGED from Phase158, now enforced with one additional
hardening.

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
  is in `reports/PHASE159_PRIVACY_SCAN.json`.
* No credential material and no credential-bearing path exists anywhere
  (`SECRET_SCAN_PASS` — see `reports/PHASE159_SECURITY_SCAN.md`).

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

Phase159 changes to the enforcement machinery (work, not policy):

1. `scripts/security/scan_privacy.py` reads every scanned line with
   `encoding="utf-8-sig"` (Phase158 revision-2 self-audit observation): a BOM on
   line 1 no longer hides a rule from seeing line 1.  BOM-less files decode
   identically.  Regression-pinned.
2. Test fixtures must use **synthetic** identifiers.  The Phase158
   privacy-contract test historically embedded one real historical venue order
   id (ten-digit value recorded only in the audit materials beside the
   delivery, not reproduced here) as fixture data; in this tree every fixture
   id is synthetic (`9000001234`), chosen to collide with no harvested id.  The
   full harvested set, and this rule, are now visible in the test source.
   This record deliberately does not reproduce the value either: an aggregate
   artifact carrying a harvested id is exactly what the scanner must flag, and
   the honest lesson of Phase159 is that the record set is itself subject to
   the rule (the first draft of this review was caught doing it — the digits
   are now out; the fact is preserved in reports/PHASE159_HARDENING.json).

Nothing about what ships changed in Phase159: only the scanners got harder and
the fixtures got cleaner.
