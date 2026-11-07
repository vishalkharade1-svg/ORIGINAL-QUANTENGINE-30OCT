# Delta Credential Exposure — Operator Runbook

## Scope

This runbook applies to the historical and local Delta credentials identified
by the Phase 0 audit.  Do not paste a key or secret into tickets, terminal
history, chat, Git commits, CI variables, logs, screenshots, or this file.

## Immediate containment

1. In the authorized Delta account, revoke both exposed API credentials.
2. Review API-key permissions, IP allowlists, created/changed orders,
   withdrawals, login sessions, and audit activity for the exposure window.
3. Confirm the replacement key has the minimum required permissions; do not
   enable withdrawal permission for QuantEngine.
4. Keep `PAPER_MODE=True`, `LIVE_MODE=False`, `ALLOW_LIVE` empty, and
   `LIVE_EXECUTE` empty until the live-readiness programme authorizes a
   separate canary procedure.
5. Store any replacement credentials only in the approved deployment secret
   manager.  The local ignored `.env` is not a secret manager.

## Git remediation (repository maintainer only)

1. Coordinate a maintenance window with all clone owners and CI operators.
2. Make a verified backup of repository refs in access-controlled storage.
3. Use an approved history-rewriting tool/procedure to remove the historical
   `.env` blobs containing credential assignments from every reachable ref.
4. Force-push rewritten protected branches only under the hosting provider's
   approved process; invalidate caches, artifacts and release bundles that
   may retain old blobs.
5. Require collaborators to re-clone or safely reset their local clones.
6. Run `python scripts/security/scan_secrets.py --check-history` locally and
   record a clean result without publishing credentials.
7. Enable or verify GitHub secret scanning/push protection in repository
   settings.  The committed workflow checks new working-tree content but
   cannot erase existing remote history by itself.

## Verification record

Record only the following non-secret evidence in the incident ticket:

- credential IDs or opaque provider references, not values;
- revocation timestamp and operator identity;
- reviewed account activity window and outcome;
- rewritten-ref list and force-push approval;
- history-scan result;
- post-remediation `LiveSafetyGate` and paper-mode test result.

## Completion criteria

Phase 0 P0-03 closes only after the provider confirms revocation, the
repository's reachable history scan is clean, clone/cache remediation is
complete, and the safety regression suite remains green.
# Credential Incident Runbook

## Published-history remediation complete

On 2026-09-15 the GitHub `main` branch was rewritten to a clean 164-commit
lineage and independently verified with `git log origin/main -- .env`. The
current published tip, `3592007d9051a91b6f5356c7c838ea3baef21b72`, remains
clean after the Phase 20 and endpoint-observation commits. This does not revoke
copied credentials or clean old local clones, worktrees, forks, CI caches, or
GitHub object retention immediately.

## Required local-clone retirement

1. Rotate/revoke every credential that was ever present in `.env`.
2. Preserve intentional uncommitted work as a patch or a new clean-branch
   commit based on the rewritten `origin/main`.
3. Delete or reclone every checkout/worktree whose reachable history includes
   the old commits. Do not rely on `git pull` to repair rewritten history.
4. Clear CI build caches and tell collaborators to discard stale clones/forks.
5. Run `python scripts/security/scan_secrets.py` on the new checkout and
   `git log origin/main -- .env` before restoring any local work.

This procedure does not authorize live execution. Keep `ALLOW_LIVE` disabled
until Phase 10 readiness evidence and the existing `LiveSafetyGate` are both
satisfied.
