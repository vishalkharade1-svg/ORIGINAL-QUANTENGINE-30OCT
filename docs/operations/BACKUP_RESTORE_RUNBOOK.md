# Backup & restore runbook (2026-10-11)

Scope: operator data and evidence. Code itself is version-controlled
elsewhere; this covers what version control must NOT carry.

## What to back up (in priority order)

1. `data/runtime/risk_policy_overrides.json` — active trading-policy
   overrides (global + per-instrument). Loss of this file silently
   reverts execution to compiled defaults. Back up on every change.
2. Reconciler snapshot journals (`broker-snapshot-v1`, configured
   `snapshot_path`) — crash evidence + restart authority. Never delete
   to "clean up"; age them out only with an explicit retention rule.
3. `research/results/*.json` — phase/evidence ledgers (the audit trail).
4. `research/captures/` — raw venue evidence + manifests.
5. `data/history/` caches (gitignored datasets) — re-downloadable via
   the fetch scripts, but large; back up if bandwidth is constrained.

## What must NEVER enter a backup shared beyond the operator host

- `.env`, `env/.env.py`, or any file containing `DELTA_API_KEY` /
  `DELTA_API_SECRET` / `CONTROL_API_TOKEN` values. Exclude by name
  before archiving: `.env`, `.env.*`, `*.pem`, `*.key`, `*.secret`.
- Checkpoint ZIPs must exclude secrets, caches, virtual environments,
  and transient files (same exclusion list as archives).

## How (example, operator host)

```sh
# Integrity-checked archive of operator state (no secrets):
tar --exclude='.env' --exclude='.env.*' --exclude='*.key' \
    -czf qe-operator-state-<date>.tgz data/runtime research/results \
    research/captures
sha256sum qe-operator-state-<date>.tgz > qe-operator-state-<date>.sha256
```

## Restore

1. Verify the `.sha256` before unpacking.
2. Restore `data/runtime/` first (policy authority), then evidence dirs.
3. Restart the runtime and confirm the reconciler startup check runs
   against exchange authority before any routing (live) — a restored
   snapshot that disagrees with the exchange halts, by design.
4. Re-provision credentials via the secret store / local `.env`; never
   restore secrets from an archive.

## Expectations

- RPO: policy file — zero (back up on change); evidence — last capture.
- RTO: minutes (unpack + restart + reconcile).
- Drill history: 2026-10-11 isolated drill (synthetic tree, marker
  secrets only) PASSED — completeness, sha256, policy/evidence restore,
  secret exclusion, restore-before-credentials ordering. Toy scale
  (0.08s) proves the PROCEDURE, not production timing: the first
  full-size restore remains a supervised drill, not an incident
  response.

## Known limitation (disclosed, not built here)

Paper runtimes keep ledger/account state in memory: a paper restart
begins a fresh paper book by design. Live recovery is via the
reconciler journal + exchange authority (audited Phase 95). Full
risk/cooldown/PnL restore across restarts is absent (see stage-123
report) and deferred — speculative persistence machinery was judged
higher-risk than the disclosed limitation it would close.
