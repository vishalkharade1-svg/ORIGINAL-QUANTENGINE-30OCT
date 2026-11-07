# Phase157 adversarial self-audit (2026-10-16)

**This is not an independent audit.** The same agent that wrote the code under
audit ran these checks. It cannot substitute for the pending independent
forensic review and does not close that gate. What it can do is hunt for defects
in the shipped bytes and hand the independent auditor a verified starting point.

Artifact under audit: `QuantEngine_PHASE157_RELEASE_CANDIDATE.zip`.
Method: a read-only mechanical harness (zips opened in memory, nothing written
into the repository) plus targeted greps, following the twelve check families of
`docs/CLAUDE_PHASE154_INDEPENDENT_AUDIT_PROMPT.md`, adapted from the Phase154
artifact to the current one.

## Findings

| # | Check family | Result |
|---|---|---|
| 1 | Archive identity | PASS |
| 2 | Manifest | PASS |
| 3 | Provenance | **ONE GAP FOUND AND FIXED** (see below) |
| 4 | MCP configuration | PASS |
| 5 | Error taxonomy | PASS |
| 6 | DELETE signing | PASS |
| 7 | Ledger | PASS |
| 8 | Script safety | PASS (check wording now stale — see below) |
| 9 | Suite honesty | PASS |
| 10 | No weakening | PASS |
| 11 | Change completeness | PASS |
| 12 | Verdict logic | PASS |

Two further entries are recorded below as **false positives of my own audit
heuristics**, because an auditor who trips over the same strings deserves to know
they were already checked.

## The gap: the record did not state the versions used

The audit prompt requires the provenance record to name "the Python/pytest
versions actually used". The Phase154 provenance file did; the Phase157 records
did not. That is a real completeness defect: without it, a reader cannot reject a
substitution claim, and the very check that exists to catch a fabricated
environment had nothing to bite on.

Fixed in this same rebuild — `reports/PHASE157_RELEASE_GATES.json` now carries:

```json
"verification_environment": {
  "python": "3.12.10", "pytest": "8.4.2",
  "platform": "Windows-10-10.0.19045-SP0"
}
```

with a note that the dependency evaluation ran in an isolated venv on the same
Python with pytest 9.0.3, and that any claim of 3.13.x or 9.0.x for the
authoritative runs would be false. The environment is also recorded in the
detached record.

## Check detail

**1. Archive identity — PASS.** SHA-256 recomputed from the bytes:
`72fe28e0…` (superseded by this rebuild; the current value is in the detached
record). 1,817 members, `testzip` clean. No absolute paths, no `..` traversal,
no backslashes, no symlinks, no executable bits, no `.exe/.dll/.bat/.ps1/.pyd/.so`
members, no duplicate names. Phase156 (1,810 members) and Phase153 (1,770) were
recomputed for comparison. The `.zip` members inside the package are research
data (Binance 1m/aggTrades), not nested release archives, and they are covered
by the manifest.

**2. Manifest — PASS.** Full sweep, not a sample: all 1,816 non-manifest members
are listed, **0 missing, 0 extra, 0 hash mismatches**, and the manifest does not
list itself. `scripts/generate_manifest.py` is deterministic (two in-memory
renders byte-identical), and the packaged manifest is byte-identical to the
worktree manifest (195,535 bytes, 1,816 CRLF line endings). Exclusions match the
documented contract; research ZIPs are covered.

*Method note.* My first comparison reported a mismatch here. It was my own bug:
I read the worktree file in text mode, which translates newlines, and compared it
to a raw decode of the zip member. The bytes are identical. Recorded because an
auditor comparing the same two files the same careless way would raise the same
false alarm.

**3. Provenance — PASS after the fix above.** The detached record's hash was
recomputed independently and agreed; the record is correctly *not* packaged; no
packaged text file embeds the shipped archive's hash, nor the superseded Phase155
or Phase156 hashes; historical `MANIFEST_SHA256_PHASE131.txt` is byte-identical
to the copy in the Phase153 input archive.

**4. MCP configuration — PASS.** Packaged `.vscode/mcp.json` present with
`DELTA_MCP_ENV=india_testnet` and no credential or placeholder keys; `.gitignore`
carries the narrow `!.vscode/mcp.json` negation; all 6
`test_delta_mcp_config_safety.py` tests pass in the worktree and standalone in the
extracted package.

**5. Error taxonomy — PASS.** `EmptySymbolWindowError` is defined once and raised
at exactly one site; both capture scripts map it — `bounded_testnet_reconciled_experiment.py`
by `except`, `run_phase85_delta_testnet_capture.py` by `isinstance` — and the 9
taxonomy tests distinguish malformed, non-list, duplicate, timestamp, auth and
response failures.

**6. DELETE signing — PASS.** The signing test file references no live hostname;
its 5 tests use in-memory doubles; no order is placed or cancelled by any test.

**7. Ledger — PASS.** 22 unique fill ids, no duplicates. Fill commissions sum to
**exactly 0.62949307** — the audit prompt's figure is an aggregate, not a single
row. Zero funding rows (every `fund_id` is null; no funding/interest/settlement
mention anywhere). Wallet↔fill linkage is complete in both directions: 22 of 22
wallet rows carrying a `fill_uuid` match a fill id, no fill lacks a wallet row,
and every wallet amount equals the negated commission of its fill to 1e-9.
`user_id` is a single account id (masked here) contained in six raw captures —
private WS archives/frames and the wallet ledgers — and in **zero** reports,
matching "raw restricted, reports aggregate-only". The `_100` filenames denote
the request page size, documented in `reports/PHASE154_LEDGER_EVIDENCE_AUDIT.md`.

**8. Script safety — PASS, with stale wording.** All three order-capable scripts
require `--execute`, bind Testnet endpoints, and read only
`DELTA_INDIA_TESTNET_*` credential names. The check's original wording — confirm
`funding_settlement_hold.py` "never executed here (no `hold_log.jsonl`)" — can no
longer be satisfied literally, because the log now exists: it is the refusal
trail from the 16:00 UTC settlement attempt. Its *intent* holds: the packaged log
contains **zero order events**.

**9. Suite honesty — PASS.** Raw logs are packaged. No new skip or xfail markers:
four files carry one marker each, all four pre-existing in the Phase153 input.
The post-run drift fixes are covered by focused green runs, not by editing
expectations. The 43 pre-existing failures are unchanged in kind.

**10. No weakening — PASS.** **Zero** test files carry fewer assertion-like
statements than in the Phase153 input archive. Against Phase156: one test file
added, one changed (constants naming the shipped candidate), none removed.

**11. Change completeness — PASS.** All twelve claimed fixes and artifacts were
verified present **in the ZIP**, not in the worktree: the windowed reconciler and
its `fingerprint` import, the strict reconciler preserved, the funding script's
`target_settlement` with the hardcoded-day check absent, the MCP config, the
gitignore negation, the taxonomy tests, the windowed tests, and the dependency
evaluation report.

**12. Verdict logic — PASS.** `NOT_PRODUCTION_READY` while the authoritative suite
gate is FAIL and the funding-evidence gate is BLOCKED. No `PRODUCTION_READY` claim
appears anywhere in the package.

## Two false positives of my own heuristics

Recorded so they are not re-investigated as if they were open:

- `scripts/build_sandbox_external_evidence.py` matched an "order endpoint,
  ungated" heuristic. It is read-only by design: the `/v2/orders` string is a
  hardcoded prehash sanity check (`GET1542110948/v2/orders?product_id=1`), and its
  only authenticated call is a GET of wallet balances on sandbox credentials.
- `scripts/bounded_testnet_reconciled_experiment.py` matched "endpoint not bound"
  because the hostname is not a literal in the file. It binds the endpoint through
  `exp.TESTNET_REST` and validates it at runtime with
  `validate_endpoints("india_testnet", …)`, which refuses on mismatch.

## What this audit cannot say

It cannot say the artifact is correct — only that the twelve mechanical families
came back clean against the bytes, minus the one record gap now fixed. It cannot
see a defect that requires reading the code with fresh eyes, which is exactly what
the pending independent review is for. The funding-through-settlement and
repeat-match *evidence* gates remain BLOCKED for an external reason unrelated to
anything audited here.
