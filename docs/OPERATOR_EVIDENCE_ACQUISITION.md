# QuantEngine — Operator Evidence Acquisition Guide

Read-only operator documentation. This guide authorizes no code changes,
no trading, and no production activation. It defines exactly what
external evidence would close each remaining blocker, how to submit it,
and how it will be evaluated.

Related machine-readable artifacts (authoritative for automation):

* `scripts/evidence_closure_matrix.py` — 21-blocker closure matrix
* `scripts/recertify_strategy_digest.py` — read-only digest procedure
* `scripts/capture_delta_public_frames.py` — bounded public capture
* `scripts/verify_delta_global_evidence.py` — Global evidence verifier

## 1. Current certification boundary

* Internally certified (code, tests, determinism, isolation).
* External evidence blocked (no venue claim verified).
* `is_production_ready = FALSE`.
* `NOT_LIVE_READY = TRUE`.
* No strategy promotion has occurred or is authorized.
* No production directives exist.
* No order, ledger, position, paper, or live mutation capability exists.
* Local parser/readiness evidence, negative evidence (silence samples),
  and advisory fixtures must never be presented as venue verification.

## 2. Evidence request matrix

### E1 — Genuine Global rollover

* Required evidence: bounded public capture from
  `wss://public-socket.delta.exchange` showing an actual
  instrument/session rollover transition (pre-boundary observations,
  transition, post-boundary observations, timestamps, continuity).
* Acceptable source: the repository capture utility or an equivalent
  bounded credential-free capture with preserved raw frames.
* Minimum contents: endpoint, instrument (BTCUSDT), channels
  (`candlestick_1m` + `trades`), subscription echo, ≥2 distinct `cst`
  exactly 60s apart with multiple updates sharing one `cst`.
* Current status: BLOCKED (schemas observed; three silence samples;
  no transition in ~25 min historical + 150s + 330s windows).
* Can close: `ROLLOVER = VERIFIED` for the observed session only.
* Cannot prove: reliability across sessions, server recovery,
  finality, production readiness.
* Operator action: run a boundary-timed capture until a transition is
  observed; submit raw bundle + hash.

### E2 — Genuine server-side disconnect and recovery

* Required evidence: provider-initiated disconnect with client
  detection, reconnect, resubscription, resumed authoritative data,
  and duplicate/stale audit.
* Acceptable source: a genuine provider event captured with connection
  logs; never a sabotaged link.
* Minimum contents: disconnect origin, detection evidence, reconnect
  timestamps, resubscription echo, post-recovery frames, continuity
  report.
* Current status: NOT_OBSERVED (client-initiated drills only).
* Can close: `SERVER_RECOVERY = VERIFIED` for the observed event.
* Cannot prove: future outage behavior, production reliability.
* Operator action: preserve connection logs if a genuine provider
  outage occurs; submit them unaltered.

### E3 — Authoritative contract specification

* Required evidence: per-instrument venue specification covering tick
  size, price precision, contract multiplier, quantity step, minimum
  quantity, minimum notional, settlement, expiry/rollover, margin and
  leverage/order constraints.
* Acceptable source: Delta product/metadata endpoint response or
  versioned venue documentation, with retrieval context.
* Minimum contents: instrument, each field with value + units,
  source + timestamp/version, parser output, validation report.
* Current status: UNVERIFIED (fragments in source; zero runtime
  callers; local cache is Phase-17 era, stale by age).
* Can close: per-field VERIFIED + runtime enforcement, once ingested
  through the existing contract abstraction with regression tests.
* Cannot prove: economics, execution quality, lifecycle.
* Operator action: supply a fresh authorized product snapshot with
  retrieval context; never hand-write values from memory.

### E4 — Authoritative fee/economic specification

* Required evidence: maker/taker fees per instrument, funding/carry
  semantics where applicable, multiplier/tick value, minimum
  notional, and execution-quality/slippage evidence where applicable.
* Acceptable source: venue fee schedule endpoint/docs plus
  execution-quality observation.
* Minimum contents: fee type, unit, validity, evidence hash, runtime
  consumer mapping. UNKNOWN must stay distinct from EXPLICIT_ZERO.
* Current status: UNVERIFIED (formula verified; values unverified;
  `require_realistic`/`apply_costs` defined but unwired).
* Can close: enforced economics with fail-closed unknown handling.
* Cannot prove: profitability, execution quality at scale.
* Operator action: supply the versioned fee schedule; do not assume
  zero means free or verified.

### E5 — Authorized private sandbox lifecycle evidence

* Required evidence: per-state order lifecycle (accepted, rejected,
  cancelled, expired, partial, filled, duplicate, unknown), fill
  records (fill/order IDs, qty, price, fee, timestamp), positions
  (side, qty, average, realized/unrealized), balances
  (equity/available/margin/currency), restart reconciliation
  (persist → restart → remote snapshot → halt/continue).
* Acceptable source: authorized sandbox/testnet with documented
  schemas. No production account, no live trading.
* Minimum contents: one evidence record per state/field above, each
  tagged `GENUINE_SANDBOX_EVIDENCE` (never production evidence).
* Current status: BLOCKED (`open_orders()` parses tolerantly but no
  verdict consumes it; local drills only).
* Can close: per-category VERIFIED up to full venue reconciliation.
* Cannot prove: production behavior.
* Operator action: provision sandbox + schemas + test credentials via
  environment only. Never place credentials in the repository.

### E6 — Canonical OOS dataset and re-certification

* Required evidence: canonical dataset, exact source revision,
  gate-80 corrected source, deterministic execution, OOS outputs,
  statistical/multiple-testing outputs, review and re-registration.
* Acceptable source: versioned dataset artifact plus the existing
  9M pipeline executed under the current source.
* Minimum contents: dataset hash, source revision, configuration,
  deterministic output hash, per-finding classification (VALIDATED /
  PROMISING / INCONCLUSIVE / REJECTED / UNAVAILABLE).
* Current status: BLOCKED (canonical caches are git-ignored and
  absent from clean checkout; historical digest `c52e64…`
  irreproducible by construction and stays untouched).
* Can close: a NEW canonical research certification only — never a
  silent re-pin of the historical digest.
* Cannot prove: future edge, profitability.
* Operator action: restore the canonical dataset, authorize compute,
  review and deliberately re-register the new digest.

### E7 — Operator credential rotation/revocation

* Required evidence: rotation/revocation records from the provider.
* Acceptable source: provider operator action per the incident
  runbook (`docs/operations/DELTA_CREDENTIAL_INCIDENT_RUNBOOK.md`).
* Minimum contents: confirmation that rotation occurred; no secret
  values anywhere in the evidence.
* Current status: OPERATOR_CONTROLLED (runtime guards verified:
  env-backed loading, blank-gating, redaction; rotation itself is
  intentionally not automated).
* Can close: rotation demonstrated (status remains operator-owned
  by design; no repo subsystem will be built for it).
* Cannot prove: anything about strategy or readiness.
* Operator action: rotate/revoke per runbook. Never commit secrets.

## 3. Evidence submission checklist

Every submission must state:

* venue (`DELTA_GLOBAL`, `DELTA_INDIA`, sandbox name, or research).
* endpoint or source system and schema version.
* instrument(s) and session identifier(s).
* capture start/end (source timestamps; timezone explicit, UTC
  preferred).
* raw frame preservation (unmodified bytes plus SHA-256 file hash).
* source command/script and its version or commit.
* redaction procedure applied, if any, with before/after field list.
* explicit confirmation that no credentials, tokens, cookies, or
  private keys are included.
* evidence class: `GENUINE_VENUE`, `GENUINE_SANDBOX_EVIDENCE`,
  `NEGATIVE_EVIDENCE` (e.g., silence sample), `LOCAL_PARSER_EVIDENCE`,
  `REPLAY`, or `SYNTHETIC_TEST_ONLY` (never accepted as venue proof).

Do not place credentials in the repository — environment-backed
credentials only, and only in operator-controlled environments.

## 4. Acceptance rules

Evidence is accepted only when it is:

* traceable to the stated venue, instrument, and session;
* integrity-verifiable (hash matches submitted bytes; schema parses);
* covering exactly the claimed behavior (a candle frame proves
  schema, not rollover; an echo proves subscription, not publication);
* temporally coherent (timestamps ordered; no future-dependent
  construction);
* free of synthetic substitutions for the claimed behavior;
* scoped honestly (local/parser evidence is never silently upgraded
  to venue verification; India evidence never substitutes for Global).

Partial evidence yields at most PARTIAL status for the covered slice;
all other slices remain blocked.

## 5. Explicit next-step gate

No further implementation phase is authorized unless at least one of
the following occurs:

* genuine external evidence arrives;
* canonical OOS data becomes available;
* an actual implementation defect is discovered;
* an explicit engineering requirement changes.

Internal certification without new evidence is complete. Further
audits without new inputs add no information and are not authorized.

## 6. Re-certification procedure

After evidence arrives, the safe sequence is:

1. Preserve the evidence immutably (raw bytes + hash + checklist).
2. Validate provenance and hashes before any code reads it.
3. Run the relevant focused tests (existing suites first).
4. Re-evaluate only the affected claim; leave all other claims at
   their current status.
5. Update the evidence matrix (`scripts/evidence_closure_matrix.py`)
   for the affected rows only, with tests proving the new state.
6. Re-run required deterministic checks (byte-identity, hashes,
   classifications) and production-isolation checks.
7. Re-run the full suite only when operationally feasible; on
   timeout record TIMEOUT, never PASS.
8. Keep unresolved claims blocked with explicit reasons.
9. Never infer production readiness from partial closure:
   `is_production_ready` requires every mandatory category genuinely
   verified, and `NOT_LIVE_READY` stays true until then.
