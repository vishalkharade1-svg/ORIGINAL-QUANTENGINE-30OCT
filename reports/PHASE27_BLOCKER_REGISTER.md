STATUS: BLOCKED

# Phase 27 Blocker Register

## Open blockers

| Blocker | Severity | Evidence | Owner | Required action | What it prevents |
|---------|----------|----------|-------|-----------------|------------------|
| **Secret rotation / testnet/live credentials** | HIGH | Owner must rotate; no automated remediation possible | Owner | Provide updated `.env` or disable credential checks | Live/trading‑engine auth |
| **Independent holdout dataset** | HIGH | No unseen dataset after Phase 26; can’t unbiasedly claim edge | Owner | Acquire or generate holdout data before evaluation | Claiming strategy edge |
| **Target‑selection policy (reject vs clamp vs configurable)** | MEDIUM | Active 1:20 cap leaves ~1 certified order because strategy targets >20 R | Owner | Decide and document policy; add configurable mode if needed | Preventing silent tuning on seen OOS data |
| **Byte‑exact historical replay feasibility** | MEDIUM | Phase‑18 harness not an ancestor; replay not possible | Owner | Accept replay‑unavailable or document limitation | Re‑running historic scenarios |
| **Trailing‑stop edge impact verification** | LOW | Current sample too small to confirm benefit/harm | Owner | Run larger‑scale simulation or acquire more data | Over‑/under‑estimating trailing benefit |

## Summary

- All active 1:6 enforcement has been removed.
- New 1:1‑1:20 RR policy is in place and tested (68 focused tests pass, 3 trailing‑primitive tests pass).
- Trailing‑stop implementation is complete for the supported `R_DISTANCE` method.
- Remaining blockers are policy/organisational; code changes are finished.
- Owner action required for holdout data, secret rotation, and target‑selection decision.