# Phase 26 — Blocker Register

Status legend: `OPEN_OWNER_BLOCKED` · `OPEN_DATA_BLOCKED` ·
`OPEN_DESIGN_CONSTRAINT` · `CLOSED_REPAIRED` · `CLOSED_DISCLOSED`.

Release gate remains **HOLD**, edge remains **NOT ESTABLISHED**, and
testnet/live execution remains **NOT AUTHORIZED**.

---

## B01 — Non-empty known-secret values in `.env`

- **Severity:** HIGH (security)
- **Status:** `OPEN_OWNER_BLOCKED`
- **Evidence:** Phase-23/25 scan returned non-zero findings; values redacted.
  Pattern names only are recorded; no secret value is stored in any artifact.
- **Impact:** blocks any credential-bearing operation; does not affect offline
  evidence or the frozen OOS verdict.
- **Owner action:** rotate the affected credentials at the provider, replace
  `.env`, and record rotation evidence outside the repository. Editing `.env`
  alone is not remediation.
- **Exit criteria:** owner attests rotation with provider-side evidence; scan
  is re-run and findings are dispositioned.

## B02 — Testnet / live execution authorization

- **Severity:** CRITICAL (gate)
- **Status:** `OPEN_OWNER_BLOCKED`
- **Evidence:** no authorization exists; Phase 17 hostile audit and Phase 22
  certification prohibit activation. No testnet or live order has been placed.
- **Impact:** all execution remains offline/paper.
- **Owner action:** explicit written authorization with scope, limits and
  rollback plan after positive net-of-cost edge evidence.
- **Exit criteria:** owner authorization plus a passing preregistered forward
  validation (see `PHASE26_STRATEGY_VALIDATION_PLAN.md`).

## B03 — Venue fee schedule unknown

- **Severity:** MEDIUM (evidence quality)
- **Status:** `OPEN_OWNER_BLOCKED`
- **Evidence:** no Delta perps fee schedule is available offline; only the
  configured 11F ladders can be applied.
- **Impact:** costs are labeled `CONFIGURED_SIMULATION`; no claim of real
  net-of-fee performance is made.
- **Owner action:** supply authoritative maker/taker schedules (and any
  account-tier adjustments).
- **Exit criteria:** fee schedule recorded in-repo with provenance and applied
  to a fresh evaluation.

## B04 — Dev / pre-Gate-A partition absent

- **Severity:** MEDIUM (methodology)
- **Status:** `OPEN_DATA_BLOCKED`
- **Evidence:** the delivery contains only the certified Gate-A dataset and
  the extended top-up; no bars before the certified boundary.
- **Impact:** dev-partition sensitivity cannot be measured; no parameter was
  changed, so the certified result is unaffected.
- **Owner action:** supply the pre-boundary history or authorize a new
  data-acquisition phase.
- **Exit criteria:** partition exists, passes integrity checks, and is used
  only for research—not for tuning against the frozen OOS.

## B05 — Entry model vs 1:6 realized-RR floor is structurally incompatible

- **Severity:** CRITICAL (evidence/strategy)
- **Status:** `OPEN_DESIGN_CONSTRAINT` (confirmed, not a defect)
- **Evidence:** 32/32 certified orders triggered; 30 refused by the realized
  RR floor (executable RR 0.009–2.94), 2 refused because the next open was
  already beyond the target. Creation-time RR is 21–363, so the gate is
  non-binding at creation and absolutely binding at execution. Median trigger
  occurs 82.8% of the way to target; the fill sits a median of 50 initial
  stop-widths beyond entry.
- **Impact:** the frozen strategy cannot trade this dataset by construction.
  Loosening the floor would violate mission constraints and is prohibited.
- **Required action:** do not modify the frozen strategy. Preregister a new
  entry/stop/target hypothesis family and evaluate on genuinely unseen data.
- **Exit criteria:** new family passes the preregistered sample and
  net-of-cost gates in the validation plan.

## B06 — Byte-exact historical replay infeasible

- **Severity:** LOW (provenance)
- **Status:** `CLOSED_DISCLOSED`
- **Evidence:** recorded revision `6eb35d8` is not an ancestor of HEAD; the
  Phase-18 harness is absent at that commit; the current 9-file composite
  (`473e5942…`, canonical `05986916…`) differs from the recorded pin
  (`c52e648…`). Behavioral reproduction is exact (32 orders, 32 triggers,
  30 expirations, 2 invalidations, per-period split 2/0/2/3/8/0).
- **Impact:** provenance is behavioral rather than byte-identical. No effect
  on the zero-fill diagnosis.
- **Owner action:** none required for Phase 26; retain this disclosure in all
  future references to the certified baseline.

## B07 — Funding head gap (six settlements omitted)

- **Severity:** HIGH (evidence)
- **Status:** `CLOSED_REPAIRED`
- **Evidence:** Phase-25 request started 09:45Z, inside an 8-hour funding
  block; the endpoint returned only whole aligned blocks, dropping the
  10:00–15:00Z settlements and creating a 22,500-second head gap.
- **Repair:** `scripts/capture_funding_evidence_phase26.py` with aligned
  start and pad; new strict artifacts; 529 hourly events; first event
  2026-09-05T00:00Z; head gap 0; six recovered settlements verified.
- **Preservation:** Phase-25 artifacts unchanged (`67c33b5538994d18`,
  `494d17a2821e6c82`).
- **Exit criteria:** met; regression test asserts coverage and continuity.

## B08 — No persisted per-order lifecycle evidence in the certified run

- **Severity:** HIGH (observability)
- **Status:** `CLOSED_REPAIRED`
- **Evidence:** Phase-18 recorded terminal funnels only; the reason for each
  rejection was not persisted.
- **Repair:** opt-in `order_trace` sink in the canonical executor; per-order
  records for the global and all per-period runs; classification, geometry,
  timing and RR fields; funnel-preservation regression test.
- **Exit criteria:** met; `reports/PHASE26_ORDER_LIFECYCLE.json` complete.

## B09 — Extended-dataset funnel differs from the older-revision record

- **Severity:** MEDIUM (evidence provenance)
- **Status:** `CLOSED_DISCLOSED`
- **Evidence:** Phase-30 recorded 21 orders / 3 fills; at current HEAD the
  same extended data yields 82 orders / 2 fills. The certified Phase-18
  funnel still reproduces exactly. The extended set is therefore
  different-revision evidence.
- **Impact:** extended results can never be used to support edge or to
  compare against certified numbers.
- **Required labeling:** `DIFFERENT_REVISION_EVIDENCE` on every reference.

## B10 — Sample sufficiency unmet (0 completed trades)

- **Severity:** CRITICAL (evidence)
- **Status:** `OPEN_DESIGN_CONSTRAINT`
- **Evidence:** the 9M plan requires ≥60 completed trades across ≥5 surviving
  periods; the certified OOS produced none.
- **Impact:** no statistical statement about edge is possible.
- **Dependency:** B05.
- **Exit criteria:** new preregistered family meets the sample gates on unseen
  data with costs and funding applied.

## B11 — Delta instrument metadata is a synthetic spot fallback

- **Severity:** LOW (paper-session fidelity)
- **Status:** `OPEN_OWNER_BLOCKED`
- **Evidence:** Phase-25 paper session used the fallback metadata; clearly
  labeled synthetic.
- **Impact:** limits fidelity of paper fills, not the offline OOS result.
- **Owner action:** provide authoritative Delta perp instrument metadata.

## B12 — `ORDER_SKIPPED_INVERTED_FILL` log verb is misleading

- **Severity:** LOW (observability)
- **Status:** `CLOSED_DISCLOSED`
- **Evidence:** the verb is emitted by the shared directional-geometry gate;
  both certified cases are beyond-target overshoots, not stop gaps.
- **Decision:** retain the verb for compatibility with existing evidence
  parsing; the tracer classifies precisely from prices.
- **Exit criteria:** met; documented in code, artifact and report.

---

## Owner action summary (in priority order)

1. Rotate leaked credentials and provide rotation evidence (B01).
2. Supply authoritative venue fee schedules (B03) and perp metadata (B11).
3. Authorize (or continue to withhold) testnet/live access (B02).
4. Supply pre-Gate-A history if dev-partition sensitivity is required (B04).
5. Review and approve the preregistered validation plan for a new hypothesis
   family (B05/B10).
