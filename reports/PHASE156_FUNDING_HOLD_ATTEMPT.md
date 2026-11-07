# Funding-settlement hold — attempt, defect repair, and external blocker (2026-10-16)

Target: India Demo (Testnet), ETHUSD, 1 contract, limit-only, flat-in verified.
Objective: hold a position through a funding settlement, then reconcile the
resulting wallet funding row against the funding rate observed at settlement.

## 1. Defect found in the hold script (fixed)

`scripts/funding_settlement_hold.py` ended its hold with:

```python
if now.day == 16 and (now.hour, now.minute) >= (0, 5):
    break
```

That is one hardcoded past instant. Re-run against any later settlement, the
loop breaks immediately, the reduce-only exit is placed, and the run logs
`settlement_window_passed` then `done` — a clean-looking success that captured
no funding at all. This is the silent-false-success class, found before it
could produce a false evidence record rather than after.

Fixed with computed targeting:

- `target_settlement()` resolves the settlement the run is actually aiming at —
  the next 00/08/16 UTC boundary at least 10 minutes ahead, or an explicit
  `--settlement <UTC ISO>`.
- the hold deadline is settlement + 5 minutes, and the hold has its own timeout;
- `funding_rate_pre` / `funding_rate_post` snapshots (read-only `/v2/products`)
  were added so the wallet row can be reconciled against the rate instead of
  merely counted.

Regression: `tests/test_funding_settlement_targeting.py` — 9 tests, including a
pin that fails if a hardcoded calendar day returns to the hold loop. Green
together with the Phase154 order-script safety contract.

## 2. Capture attempt: REFUSED, fail-closed, zero exchange writes

Command: `python scripts/funding_settlement_hold.py --dry-run`

```
{"event": "refused", "reason": "prefail: HTTPStatusError", ...}
exit 2
```

Read-only diagnosis: HTTP **401 `ip_not_whitelisted_for_api_key`**,
`client_ip 152.58.7.15`. The key's whitelist holds `157.33.197.21` — the address
that worked for the Phase147 captures
(`research/captures/phase147_ledger/fills_100.json`).

The script refuses before any signed write when the pre-check fails. No order
was submitted and no position was opened.

## 3. Finding: a single-IP whitelist cannot hold on this connection

| Time (UTC) | Egress IP | Signed pre-check |
|---|---|---|
| 15:33 | 152.58.7.15 | 401 ip_not_whitelisted |
| 15:34 (4 polls over 45 s) | 152.58.7.15 | stable |
| 15:50 | **152.58.7.109** | 401 ip_not_whitelisted |

The address rotated again within 20 minutes and never returned to the
whitelisted one. The entry window (settlement − 10 min) is far shorter than the
observed rotation interval, so a whitelist pinned to a single address cannot
reliably support a scheduled capture.

Recommendation for the operator: remove the IP restriction on the **India
Testnet** key (demo scope, no real funds), or accept that captures run only when
the current address happens to match. Whitelisting one address will keep losing
this race.

## 4. Outcome

- 16:00 UTC settlement (2026-10-16): **NOT CAPTURED** — blocked before entry.
- Next settlement windows: 00:00 and 08:00 UTC.
- Gate `funding_through_settlement_evidence`: **BLOCKED (external)**.
- Evidence: `research/captures/phase148_funding/hold_log.jsonl` (refusal trail),
  `research/captures/phase148_funding/ip_whitelist_blocker.json` (blocker record
  with the observed addresses and the required operator action).

## 5. Release consequence

The fix, the new regression, and the capture evidence are post-Phase155
worktree changes, so the Phase155 archive no longer describes the worktree. The
worktree was observed drifting by exactly 6 manifest problems before this
rebuild:

```
uncovered:research/captures/phase148_funding/hold_log.jsonl
uncovered:research/captures/phase148_funding/ip_whitelist_blocker.json
uncovered:tests/test_funding_settlement_targeting.py
mismatch:NEXT_ACTIONS.md
mismatch:scripts/funding_settlement_hold.py
mismatch:tests/test_release_consistency_phase155.py
```

Rebuilt under the frozen ordering rule as
`QuantEngine_PHASE156_RELEASE_CANDIDATE.zip`, detached record
`../RELEASE_HASH_PHASE156.txt`. The Phase155 archive is preserved unchanged as
historical evidence. The release-consistency contract now names the current
candidate, so it guards the artifact being shipped.
