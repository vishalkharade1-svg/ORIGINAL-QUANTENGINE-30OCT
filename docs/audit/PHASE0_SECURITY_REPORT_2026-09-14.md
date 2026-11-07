# QuantEngine Phase 0 — Security and Trading Safety Report

## Changed

- Sanitized the local ignored `.env`: `DELTA_API_KEY` and
  `DELTA_API_SECRET` are now empty.  Values were not copied into code,
  logs, tests, or this report.
- Added `scripts/security/scan_secrets.py`, a value-redacting scanner for
  the working tree (including ignored `.env` files).  It also offers the
  opt-in `--check-history` diagnostic, which reports only commit IDs and
  rule names.
- Added `.github/workflows/secret-scan.yml`, which runs the working-tree
  scanner on every GitHub push and pull request.
- Added `docs/operations/DELTA_CREDENTIAL_INCIDENT_RUNBOOK.md`, an
  operator-safe handoff for the required provider revocation and coordinated
  Git-history remediation.
- Added `tests/test_secret_scan_phase0.py` for blank/non-empty credential
  behaviour and a current-worktree regression check.

No live-safety, execution, risk, or exchange behaviour was changed.

## Why

The audit found non-empty Delta credentials in the local `.env` and in
five reachable historical revisions.  Ignoring a file prevents a new
commit; it does not protect an already exposed credential or local file.
The scanner is deliberately non-disclosing so its own diagnostic output
does not repeat a secret.

## Tests

| Command | Result |
|---|---|
| `python scripts/security/scan_secrets.py` | `SECRET_SCAN_PASS` |
| `python -m pytest tests/test_secret_scan_phase0.py tests/test_security_12.py tests/test_live_block_11.py tests/test_order_executor.py -q` | **45 passed**; one non-fatal `.pytest_cache` permission warning |
| `.venv\\Scripts\\python -m compileall -q scripts/security tests/test_secret_scan_phase0.py core/execution/live_safety_gate.py core/execution/order_executor.py` | **PASS** |
| `git diff --check` | **PASS** |
| `python scripts/security/scan_secrets.py --check-history` | **FAIL EXPECTED:** five historical `.env` revisions contain non-empty known Delta assignments; values were not printed. |

## Live-safety verification

- Defaults remain `PAPER_MODE=True`, `LIVE_MODE=False`, with empty live
  arming flags.
- The only discovered exchange-write chain remains
  `DeltaOrderExecutor.execute/cancel` -> `DeltaExchange.place_order/cancel_order`.
- The focused tests demonstrate refused live states cause no fake transport
  write and that paper mode remains non-writing.  This is **VERIFIED** only
  against local fakes, not a live venue.

## Remaining / stop condition

**P0-03 remains open only for provider-side containment and legacy-clone
retirement.** Local removal cannot revoke an already exposed credential or
erase clones, backups, CI logs, and retained Git objects. An authorized Delta
account operator must revoke/rotate the two keys, review account activity, and
update the secret manager.

On 2026-09-15 the published `origin/main` history was rewritten and verified
clean with `git log origin/main -- .env`; the current remote tip is
`3592007d9051a91b6f5356c7c838ea3baef21b72`. The current checkout is based on
that clean lineage. Every stale clone, fork, cache, and separately owned
worktree still retaining old commits must be retired or rebuilt before the
incident can close. A local `--check-history` result may still flag such a
separate legacy ref; it is not evidence that the published main branch was
left unremediated.

The audit also found no reason to weaken `LiveSafetyGate`; it was not
modified.  Phase 1 must not start automatically while this P0 remains
open.

## Risks

- The scanner covers explicit known assignment formats and PEM headers; it
  is a guardrail, not proof that every possible secret encoding is absent.
- The `.env` file is ignored, so its sanitization does not appear in Git
  diff.  The scanner validates its current state locally.
- Old clone/worktree remediation remains destructive and impacts their
  owners; it must be coordinated before those legacy refs are removed.

## Architecture impact

None.  This adds a repository hygiene control only; the runtime routing,
risk gate, execution path, and market-data architecture are unchanged.

## Verification status

- Working-tree secret absence: **VERIFIED** for scanner rules.
- Existing live-safety regression suite: **VERIFIED** against fakes.
- Secret revocation and account activity: **EXTERNAL VERIFICATION REQUIRED**.
- Published Git history remediation: **VERIFIED** for `origin/main`.
- Legacy clone/worktree retirement: **EXTERNAL VERIFICATION REQUIRED**.
# Phase 0 Security Remediation Status

## Current local controls

- The local ignored `.env` no longer contains credential values.
- `scripts/security/scan_secrets.py` and its CI workflow scan the worktree
  without echoing values.
- Current worktree secret scan: `SECRET_SCAN_PASS`.

## Unresolved published-history incident

`python scripts/security/scan_secrets.py --check-history` on 2026-09-14 found
non-empty known-secret assignments in `.env` in these commits:

- `2f9bf0eab6570549110090e3a54ed5d264954a24`
- `e49f61e163290ca05203db68ba2660dc24303343`
- `d5846fc38815ca51df9dee97ff0414eedd59d0c2`
- `e686ccd56fd088ddb0153ecedde75cc78ad80d6d`
- `63cd4f1d8a9ee840f53d66557551df2627245575`

The configured remote is
`https://github.com/vishalkharade1-svg/quantengine-spring-41.git` on `main`.
No rewrite or force-push was performed. Credential values must be revoked at
their provider before any history rewrite can reduce exposure risk. After
revocation, an authorized maintainer must coordinate a history rewrite and
force-push, then require every clone/fork/cache to refresh or be retired.
