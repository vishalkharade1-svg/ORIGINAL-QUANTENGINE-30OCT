STATUS: BLOCKED

# Phase 31 Blocker Register

## 1. Open Blockers

| Blocker | Severity | Description | Owner Action Required | What It Prevents | Status |
|---------|----------|-------------|----------------------|------------------|--------|
| **Secret rotation / testnet/live credentials** | HIGH | Owner must rotate; no automated remediation possible | Owner | Provide updated `.env` or disable credential checks | Live/trading-engine auth | BLOCKED |
| **Independent holdout dataset** | HIGH | No unseen dataset after Phase 26; cannot unbiasedly claim edge | Owner | Acquire or generate holdout data before evaluation | Strategy-edge conclusion | BLOCKED |
| **Target-selection policy (reject vs clamp vs configurable)** | MEDIUM | The 1:20 cap leaves ~1 certified order because strategy targets >20R | Owner | Decide and document policy; add configurable mode if needed | Prevents silent tuning on seen OOS data | BLOCKED |
| **Byte-exact historical replay feasibility** | MEDIUM | Phase-18 harness not an ancestor; replay not possible | Owner | Accept replay-unavailable or document limitation | Re-running historic scenarios | BLOCKED |
| **Trailing-stop edge impact verification** | LOW | Current sample too small (0 activations) to confirm benefit/harm | Owner | Run larger-scale simulation or acquire more data | Over-/under-estimating trailing benefit | BLOCKED |

## 2. Detailed Blocker Analysis

### 2.1 Blocker 1: Secret Rotation / Testnet/Live Credentials

**Severity:** HIGH

**What is missing:** Updated `.env` file with valid testnet/live credentials, or explicit operator authorization to disable credential checks.

**Why it matters:** Live/trading-engine authorization cannot be obtained without valid credentials. The kill switch and auth gates are fail-closed by design.

**What the agent can safely complete:** Nothing — credential handling is owner-only. No secrets can be requested, printed, committed, or rotated by the agent.

**What requires owner action:** Owner must rotate credentials, update `.env`, or explicitly disable credential checks for testnet/live paths.

**Exact evidence needed to close:** Updated `.env` file (not committed), or explicit owner authorization to disable credential checks, or documented proof that credential checks are bypassed for research-only paper mode.

**Blocks:** Live authorization, testnet execution, readiness gate closure.

**Final determination:** `BLOCKED` — owner action required.

---

### 2.2 Blocker 2: Independent Holdout Dataset

**Severity:** HIGH

**What is missing:** A genuinely unseen dataset that has not been used for strategy tuning, parameter selection, or any prior evaluation.

**Why it matters:** Without an independent holdout, any edge claim is vulnerable to selection bias and overfitting. The certified and extended datasets are both `SEEN_DATA` — used in Phases 26-30 for development and evaluation.

**What the agent can safely complete:** Nothing — holdout acquisition is owner-only. No feasible data source was identified within this phase.

**What requires owner action:** Owner must acquire or generate unseen data, verify its provenance, and ensure it has not been used for prior strategy selection or parameter tuning.

**Exact evidence needed to close:** Dataset file(s) with SHA-256 hashes, provenance documentation (source, timestamps, venue, instrument), confirmation that the strategy/parameters were not tuned on this data, and inclusion in the evaluation ledger as a `HOLDOUT` classification.

**Blocks:** Strategy-edge conclusion, independent validation, live authorization.

**Final determination:** `BLOCKED` — owner action required.

---

### 2.3 Blocker 3: Target-Selection Policy (reject vs clamp vs configurable)

**Severity:** MEDIUM

**What is missing:** An explicit owner decision on how to handle candidates with planned RR above 1:20. Currently, all such candidates are rejected by `risk_reward_allowed()`, leaving ~1 certified order and ~20% of extended candidates eligible.

**Why it matters:** The 1:20 cap combined with strategy target geometry (>20R targets dominate) severely limits fill counts. Without a documented policy, it is impossible to know whether to reject (current behavior), clamp targets to 20R, or add a configurable selection mode.

**What the agent can safely complete:** Document the alternatives and their consequences. Do NOT change the active policy or implement clamping without owner authorization.

**What requires owner action:** Owner must decide: (a) keep current reject behavior, (b) add configurable clamp mode, or (c) add configurable target-selection mode. Once decided, agent can implement.

**Exact evidence needed to close:** Documented owner decision with rationale, plus updated code if a new mode is implemented.

**Blocks:** Prevents silent tuning on seen OOS data; affects fill counts and RR distribution analysis.

**Final determination:** `BLOCKED` — owner decision required.

---

### 2.4 Blocker 4: Byte-Exact Historical Replay Feasibility

**Severity:** MEDIUM

**What is missing:** A Phase-18-compatible replay harness that can reproduce historical execution byte-for-byte.

**Why it matters:** Without byte-exact replay, historic scenarios cannot be re-run to validate consistency across policy versions. The Phase-18 harness is not an ancestor of the current codebase.

**What the agent can safely complete:** Nothing — this is an infrastructure limitation.

**What requires owner action:** Owner must either accept the limitation (document that byte-exact replay is infeasible) or provide/authorize development of a replacement harness.

**Exact evidence needed to close:** Documented owner acceptance of limitation, or a working replay harness with verification that it reproduces historical results byte-for-byte.

**Blocks:** Re-running historic scenarios for comparison across policy versions.

**Final determination:** `BLOCKED` — owner action required.

---

### 2.5 Blocker 5: Trailing-Stop Edge Impact Verification

**Severity:** LOW

**What is missing:** A sufficiently large sample with trailing-stop activations to measure whether trailing stops improve or harm performance.

**Why it matters:** Under the 1:20 cap, trailing stops never activate (0 activations in both certified and extended datasets). The trailing-stop feature is functionally complete but its edge impact cannot be measured without more data or a looser cap.

**What the agent can safely complete:** Document that trailing stops are functionally complete but inactive under current policy. All 17 invariants verified and passing.

**What requires owner action:** Owner must either acquire more data (with more ≤20R targets) or authorize a larger-scale simulation, or explicitly decide to accept the limitation.

**Exact evidence needed to close:** Trailing-stop activation counts > 0 on a representative dataset, plus comparison of fixed-target vs trailing-stop outcomes on activated trades.

**Blocks:** Quantified trailing-stop benefit/harm assessment; could affect `STRATEGY_EVALUATION` verdict.

**Final determination:** `BLOCKED` — owner action required (data or simulation scale).

---

## 3. Summary

| Blocker | Severity | Blocks | Agent Can Act? | Owner Action Required? |
|---------|----------|--------|----------------|----------------------|
| Secret rotation / testnet/live credentials | HIGH | Live/trading auth | No | Yes |
| Independent holdout dataset | HIGH | Strategy-edge conclusion | No | Yes |
| Target-selection policy | MEDIUM | Silent tuning prevention | No (document only) | Yes |
| Byte-exact replay feasibility | MEDIUM | Historic scenario re-runs | No | Yes |
| Trailing-stop edge verification | LOW | Trailing benefit/harm quantification | No (document only) | Yes |

**Overall Phase 31 Blocker Status:** `BLOCKED` — all 5 blockers remain owner-level actions. No agent-safe resolution exists for any of them.

---

*Blocker register logged at: `F:\vishal 3\near final/QuantEngine_HANDOVER_PHASE161/DELIVERY/QuantEngine_PHASE161_RELEASE_CANDIDATE/reports/PHASE31_BLOCKER_REGISTER.md`*
