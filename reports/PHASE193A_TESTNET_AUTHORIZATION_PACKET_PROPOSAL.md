# PHASE 193A TESTNET AUTHORIZATION PACKET  PROPOSAL (NOT APPLIED)

Created: 2026-10-22 (Phase 12 Workstream F). Status: **PROPOSED  NOT APPLIED  BLOCKED (operator action required)**.
This packet is a fill-in template for the operator. It does NOT authorize anything by itself.
`reports/PHASE193A_TESTNET_AUTHORIZATION.md` remains `PENDING_OPERATOR_APPROVAL` /
`STRICTLY_BLOCKED / NOT_AUTHORIZED_FOR_EXECUTION` and continues to fail-closed every experiment script.

## Verification performed before this proposal

- State re-read (read-only): `reports/PHASE193A_TESTNET_AUTHORIZATION.md` lines 5/6/8.
- Fail-closed enforcement re-verified in all three experiment scripts at
  `scripts/bounded_testnet_order_experiment.py:74..139`,
  `scripts/bounded_testnet_reconciled_experiment.py:105`,
  `scripts/funding_settlement_hold.py:32/86`.
- No signature, scope fingerprint, or signed timestamp has been inserted by anyone.

## Packet (operator completes each REQUIRED* field by hand; hashes/signature must come from the operator)

| Field | Value / rule |
|---|---|
| Purpose | Bounded, serial, post-only limit order lifecycle experiment on DELTA INDIA TESTNET only |
| Environment | India Testnet endpoint `https://cdn-ind.testnet.deltaex.org` (exact-match enforced at runtime) |
| Instruments | BTCUSD (product re-verify live; mismatch aborts) |
| Max order size | NOTIONAL cap ≤ testing budget to be entered here: **[OPERATOR_ENTRY_REQUIRED]** |
| Open-order concurrency | Exactly 1 open order; Order N+1 blocked until N terminal |
| Resting policy | 120.0 s max; active cancel at 120 s; no market chasing |
| Order-write limit | Total order writes ≤ **[OPERATOR_ENTRY_REQUIRED]** for the entire experiment |
| Loss limit | Hard abort at **[OPERATOR_ENTRY_REQUIRED]** realized loss (non-optional) |
| Credential binding | Credentials must be entered BY THE OPERATOR in `.env` locally; scripts only pass them to the exchange; no values printed/logged/copied |
| Expiry | Authorization valid **[OPERATOR_ENTRY_REQUIRED]** signed timestamp, hard expiry enforced |
| Abort conditions | Any endpoint mismatch, product mismatch, auth failure, size/limit breach, loss-limit breach, 120 s timing breach, connectivity loss, unclean cancellation |
| Signature | Detached PGP signature over the EXACT packet body (operator's key) |
| Scope fingerprint | `scope_fingerprint_sha256` over the finalized Section-2 boundaries using the recorded procedure |
| Signed timestamp | Signed timestamp UTC (from the operator's local signing flow) |
| Evidence storage | Outcomes land in `reports/PHASE193A_*` + `EVIDENCE/PHASE19X_FORENSIC/`; BUILD_MANIFEST regenerated after each tracked-file edit |
| Reconciliation/cleanup | End-of-run positions reconciled-to-flat; open order canceled and verified absent; ledger entry + failure register updated |

## Operator required-action sequence after filling the packet

1. Replace ALL `[OPERATOR_ENTRY_REQUIRED]` placeholders above with concrete decisions.
2. Substitute operational scope block into `reports/PHASE193A_TESTNET_AUTHORIZATION.md` 2 (frozen ordering: text first, then manifest).
3. Compute `scope_fingerprint_sha256` per the 2 body hash procedure; insert into 4 with the PGP signature and signed timestamp.
4. Update the `state:` line to `OPERATOR_APPROVED` ONLY after the signature exists.
5. Regenerate `BUILD_MANIFEST.sha256` (tracked-file edit) and run `python scripts/generate_manifest.py --root .`.
6. Then (and only then) run `scripts/bounded_testnet_order_experiment.py --dry-run` first; only after a clean dry-run and explicit re-authorization use `--execute`.
7. Attach all evidence to the ledger; set `RELEASE_GATE` per the formal release policy (HOLD unless every release requirement is met).

---

## P192 OWNERSHIP / AMENDMENT PROPOSAL (PROPOSED  NOT APPLIED  BLOCKED: OWNER ACTION)

### Discrepancy as documented (both claims, unaltered)

- Claim A  `reports/PHASE193A_DATASET_CORPUS_AUDIT.md` row (line 19):
  file `research/captures/phase192_l2/raw_l2_capture_20261021T091410Z.jsonl`,
  expected size **121,682** bytes, expected SHA-256 **`c7bf98c56fa244196d44ae4b54e3d93fd9fc177f10b777a83492576b911b332b`**, 104 frames. **REPORTED BUT NOT REPRODUCED** (file absent).
- Claim B  prompt-spec/history claim (prior investigation notes):
  same filename, size **121,682** bytes, hash **`c7bf98c56fa769dbe06eeeb4e28e4693a129037cbe113ea4b81585223dd588b3`**. **REPORTED BUT NOT REPRODUCED** (absent).
- Both claims START with the same 9-hex prefix `c7bf98c56fa` and then diverge; exactly one of them (or both) references a file that never existed in this delivery tree. No file anywhere on this machine matches either hash.

### Verified reality (current bytes)

- `research/captures/phase190_l2/raw_l2_capture_20261021T064426Z.jsonl` size 237,803 sha256 `fb583558` VERIFIED-BY-BYTE/HASH-CHECK.
- `research/captures/phase191_l2/raw_l2_capture_20261021T073820Z.jsonl` size 118,802 sha256 `464430627e` VERIFIED-BY-BYTE/HASH-CHECK.
- `research/captures/phase192_l2/raw_l2_capture_20261021T085017Z.jsonl` size 83,636 sha256 `bc3ea0f2` VERIFIED-BY-BYTE/HASH-CHECK.
- All three decode strict-UTF-8; frame counts match; sequence continuity verified in Phase 9/11 recompute.
- `hold_log.jsonl` (1,806 B) and four earlier capture epochs (043530Z/043754Z/052513Z/052549Z) also present and parseable; none matches either phantom hash.

### Proposed amendment wording for the owner (exact replacement for row 19)

> `Phase 192` capture file `research/captures/phase192_l2/raw_l2_capture_20261021T091410Z.jsonl`
> does not exist in this delivery tree and never matched the verified corpus. It was MISRECORDED during the
> hand-over process and BOTH published hash values (claim A `c7bf98c56fa2`, claim B `c7bf98c56fa7`) are
> UNRECOVERABLE from the delivered artifacts. The actual Phase-192 capture is
> `raw_l2_capture_20261021T085017Z.jsonl` (83,636 B, sha256 `bc3ea0f233c89010`), verified. The trailing
> totals column (478,287 B / 454 frames) must be lowered to 440,241 B / 403 frames. Row is hereby
> AMENDED by the owner; the old claim is retained above for traceability and marked NOT-REPRODUCIBLE
> (per data-retention policy on historical notes); no capture bytes were synthesized.

### What the owner must do (in order)

1. Sign-off decision: append this amendment text verbatim to `reports/PHASE193A_DATASET_CORPUS_AUDIT.md` (do not silently overwrite the row  append so the historical text remains auditable) and/or the row-19 correction.
2. Regenerate `BUILD_MANIFEST.sha256` (re-audit row edit = tracked file change).
3. Optional stronger evidence: run a FRESH capture against DELTA INDIA TESTNET inside an authorized evidence-collection window; verify its `flash-pts` against a signed record; ONLY the fresh capture must be added as a NEW row; do not treat it as P192.
4. Until that decision, P192 remains `NOT VERIFIED / BLOCKED` and the corpus totals stay uncorrected.

---

# PHASE 13 EXTENSIONS (2026-10-22T19:50Z)

## Testnet authorization VALIDATION CHECKLIST (operator executes; NEVER agent)

For each row: FIELD | VALIDATION PROCEDURE | PASS CONDITION

1. state | read `reports/PHASE193A_TESTNET_AUTHORIZATION.md` line 67 `state:` | EXACTLY `OPERATOR_APPROVED` (not "approved", not "APPROVED_BY_OPERATOR", no extra text)
2. experiment purpose | packet Purpose + auth doc 1 | instruments/limits match packet EXACTLY (binary-compare content)
3. venue/environment | `scripts/bounded_testnet_order_experiment.py` enforced value + auth 2 row | endpoint https://cdn-ind.testnet.deltaex.org EXACT; production endpoints prohibited; domain mismatch abort
4. product identity | run-time re-verify (script) + packet cap | BTCUSD product id must match provider listing; mismatch = abort
5. max order size (notional cap) | packet field + script fail-closed value | non-zero, positive, and COMPUTED-notional never exceeds it at placement time
6. order-write limit | packet field + script counter | total writes <= cap; exceeded = abort + log
7. loss limit | packet + script | realized-loss breach => immediate self-cancel all-terminal
8. concurrency | packet | exactly one open order; N+1 blocked until N terminal (verified by the suite)
9. resting policy | packet | 120.0s max; auto-cancel dispatch + verification
10. expiry | packet | denominated signed timestamp; aborts past the stamp
11. signature | detached PGP block in auth doc 4 | verifiable against the operator's public key; signature covers the EXACT 2 body text (byte-for-byte, incl. trailing newline policy)
12. signed timestamp | auth doc 4 | syntactically valid ISO-8601 UTC Z; matches PGP signature date within tolerance
13. scope_fingerprint_sha256 | computed over 2 body | must equal what the operator recorded in their signing flow; recompute independently before execution
14. credential binding | `.env` (LOCAL, values never printed) | DELTA_INDIA_TESTNET keys present; production DELTA keys ABSENT; PAPER_MODE unchanged; no change to local settings interfaces
15. reconciliation + cleanup | script's --dry-run then --execute flow | end flat; ledger/register updated; BUILD_MANIFEST regen'd after each tracked edit

EXECUTION HIERARCHY: (a) all 15 PASS => `--dry-run` authorized; (b) dry-run SUCCESS + 15 checklist PASS + operator's 2nd explicit confirm => `--execute` authorized ONCE.
A successful dry-run is NEVER authorization for --execute. All experiment scripts keep failing closed on the PENDING record until (1) is flipped by the operator.

## P192 DECISION RECORD (owner decision record; PRESERVES both historical claims verbatim)

Both conflicting phantom-hash claims PRESERVED exactly: CLAIM A (audit row L19: c7bf98c56fa244196d44ae4b54e3d93fd9fc177f10b777a83492576b911b332b, 121,682 B, 104 fr) and CLAIM B (investigation-note variant: c7bf98c56fa769dbe06eeeb4e28e4693a129037cbe113ea4b81585223dd588b3, 121,682 B). NEITHER exists anywhere in the tree; the 3 audited artifacts (fb583558/46443062/bc3ea0f2) remain byte-verified, and totals-column (478,287 B / 454 fr) stays MIS-NOTED by default per text.

Decision options (choose ONE by appending the phrased decision after this list):
- DEC-P192-1 (Recommended): APPROVE the traceable amendment in `reports/PHASE193A_DATASET_CORPUS_AUDIT.md` per the Phase 12 packet wording (append-only amendment), and regenerate BUILD_MANIFEST.sha256. Effect: P192 row = the actual capture (83,636 B, bc3ea0f2..., 108... no 53 frames), the phantom rows become explicitly marked NOT-REPRODUCIBLE (historical text preserved), totals column corrected to 440,241 B / 403 fr.
- DEC-P192-2: DENY amendment; authorize a FRESH capture with explicit staging budget + evidence-collection window (per the packet); new capture appended as a NEW row (NOT a P192 relabel).
- DEC-P192-3: DEFER; P192 stays NOT VERIFIED / BLOCKED = permanent documented red per corpus integrity.
