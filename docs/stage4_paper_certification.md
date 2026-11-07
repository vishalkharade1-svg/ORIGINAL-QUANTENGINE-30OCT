# QUANTENGINE — STAGE 4 PAPER CERTIFICATION

```text
PAPER: CONDITIONAL (engineering PASS with documented limitations;
        economics negative — REPORTED, not optimized)
```

This milestone certifies engineering/paper execution behavior only.

It does not certify strategy profitability.

It does not constitute out-of-sample evidence.

It does not constitute live-trading approval.

No strategy is promoted.

LIVE remains NO-GO.

SECURITY remains BLOCKED until operator remediation.

If paper economics are negative, that result is preserved and is not optimized away.

PAPER ONLY / NOT OOS / NOT STRATEGY CERTIFICATION / NOT LIVE
```

Related: `docs/stage123_final_report.md` (§1–§25 baseline),
`docs/stage123_closure_certification.md` (closure gates),
`docs/stage123_baseline_audit.md` (pre-change forensics).

---

## 1. Scope

Build and certify a realistic, deterministic paper/shadow
environment exercising the ACTUAL production pipeline
(`InstitutionalPipeline` → Decision → RiskEngine → OrderIntent →
Backtester/TradeSimulator → OrderRegistry → Account/accounting →
Reconciler semantics) under realistic costs, restarts,
reconciliation, WebSocket failures, lifecycle events, and
prolonged operation. No separate paper-only strategy path was
created. No production safety boundary was moved to make paper
easier. No strategy parameter was tuned.

## 2. Architecture (all reused, nothing duplicated)

- Market data: deterministic seeded `make_candles` (synthetic,
  impulse-bearing, explicitly labeled) + production
  `data/history/BTCUSDT/1m.parquet` replay (flat stub).
- Execution: `Backtester` (canonical replay) + `TradeSimulator` +
  `OrderRegistry` + `Account` + `core/backtesting/accounting`.
- Costs: `CostSpec` + NEW `paper_cost_profile()` (paper-only
  settings; production defaults and research ladders untouched).
- Safety: RiskEngine (kill-switch seam added), PortfolioRiskManager
  gates, Reconciler verdicts, PaperExecutionAdapter boundary.
- Soak runner: test-helper only (in `tests/test_stage4_soak.py`),
  not a production system.

## 3. Paper execution contract (§6) — CERTIFIED

Same Signal/OrderIntent/RiskEngine/sizing/CostSpec/registry/
account/accounting/reconciliation semantics as production
(proven by shared-code tests + real-pipeline runs). Paper: zero
exchange writes (call-counted), no live credentials required for
replay, deterministic order/setup IDs, side/qty/entry/stop/target/
risk preserved, fills explicit. 192/192 soak trades carry full
identity chain (setup/order/trade IDs).

## 4. Cost profile (§7) — CONFIGURATION_REQUIRED for venue claims

Production defaults stay explicit-zero (neutral). NEW paper-only
profile (`PAPER_COMMISSION_PER_TRADE/RATE/SLIPPAGE_BPS`, env
overridable, default zero-neutral, `PAPER_COST_VENUE_REALISTIC`
false). No venue numbers invented: until an operator provisions
venue-realistic values, `PAPER_COST_PROFILE = CONFIGURATION_REQUIRED`
for any profitability-adjacent claim. Every paper artifact states
its profile (`explicit-zero-neutral` here). Research ladders
(11F A/B/C/D incl. scenario C 0.059%+5bp) verified untouched.
Funding: unmodeled (explicit zero, same documented limitation as
11E/11F).

## 5. Cost semantics + accounting (§8/§9) — GREEN

Per-trade `gross_pnl / commission / slippage / total_cost /
net_pnl` exposed; `net = gross − total` both directions, both
profiles; hostile ±epsilon mutations on every leg move net.
Ledger identity `opening + realized − fees = ending` holds across
long/short win/loss, zero-result, fee-only, slippage, sequential
registry runs, rejects, expiry, duplicates, partial-halt.
NaN/inf fail closed (`classify_pnl` raises; sizer `valid=False`;
portfolio guards block).

## 6. RR 1:6 (§10) — GREEN at order level, erosion MEASURED

Single source `MIN_RISK_REWARD = 6.0` preserved (no threshold
change). 5.99 REJECT / 6.00 ACCEPT / 6.01 ACCEPT / tick-short
REJECT / lying-field REJECT re-proven; RiskEngine revalidates
from prices. Real-pipeline finding (this phase): all 10/10
sized orders carried order-time RR ≥ 6.0, BUT `Backtester`
NEXT_BAR_OPEN market fills rewrite `order.entry` to the next
open (pre-existing Phase 5B semantics, dollar-risk preserved via
`_resize_for_actual_entry`) with NO revalidation — realized RR
eroded as low as 0.02 on gapped synthetic opens. A live market
fill cannot be un-filled, so gating the fill would DIVERGE paper
from live; instead the defect class is fixed by observability:
NEW `OrderIntent.actual_risk_reward`, stamped + logged
(`realized_rr=`) at every mutating fill. Order-time gate GREEN;
fill-erosion YELLOW (measured, reported, see soak economics).

## 7. Market data + WebSocket (§11/§12)

Replay: 30,000 synthetic 1m candles + 1,440 production-parquet
candles through the full pipeline. Transport: connect/subscribe/
receive/process, duplicate suppression (256), out-of-order drop,
malformed isolation (pump survives), resubscribe-after-drop,
heartbeat classification, staleness health — all exercised.
`GAP_REPAIR = NOT_IMPLEMENTED` (no sequence numbers on the public
ticker feed; missing-middle candles cannot be detected, only
old/duplicate ones dropped). Paper replay input is complete by
construction; live-gap exposure stays YELLOW (fail-open by
feed design — documented, not claimed).

## 8. Reconciliation + startup + restart (§13/§14/§15)

Verdicts MATCH/IN_FLIGHT/MISMATCH/UNKNOWN→halt + paper SKIP
(zero feed touches) re-exercised; all ten discrepancy classes
halt with zero new orders until explicit `resolve(note)`.
Startup cases A–E green (flat boot arms; journaled-open vs flat
halts; flat vs open halts; corrupt journal degrades; missing
state initializes flat only, never phantom). 12 crash drills:
10 resume-forward (journal → rebuild → reconcile → no dupes),
partial-fill → HALT (paper has no partial execution by design),
mid-reconcile crash → halt re-derived, corrupt journal → HALT.
Durable: reconciler snapshot (+drill JSON journals, test-only).
RAM-only (documented): positions, orders, PnL/drawdown,
cooldowns, pending windows, reservations, halt flag.

## 9. Lifecycle + duplicates (§16/§17) — GREEN

NEW/PENDING/FILLED/CANCELLED/REJECTED/EXPIRED/INVALIDATED +
SUBMITTED/ACKNOWLEDGED/PARTIAL named; `PARTIAL != FILLED` pinned;
unknown fills no-op; duplicate signal/candle/reconnect/restart/
replay/late vectors → exactly one order (registry identity +
expiry path proven).

## 10. Multi-symbol (§18, LIVE scope §19 intact)

BTCUSDT + ETHUSDT independent pipelines/registries/accounts;
shared `PortfolioRiskManager(max_positions=1)` blocks the second
symbol deterministically; failure on A cannot touch B (separate
objects; router-level isolation re-verified Stage 1–3). LIVE
scope NOT expanded (still single-symbol; paper multi-symbol is
not cited as live evidence).

## 11. Breakers (§20) + kill switch (§21) — GREEN (seam added)

Daily-loss ±epsilon boundaries, NaN/inf/missing fail-closed,
caps, reset semantics green. Kill switch WAS write-only
(`AccountState.kill_switch` never read) → minimum seam
implemented in `RiskEngine.analyze` (mandatory path):
`kill_switch` truthy OR `trading_enabled` falsy OR
`QE_KILL_SWITCH` env truthy → zero new orders, state stays
observable, recovery requires explicit clear. Tampered values
fail closed; env persists across restarts by operator action.

## 12. Boundaries (§22/§31/§43) — GREEN

Paper: `execute()` records locally; fetch/balance/positions/
cancel raise `PaperOnlyError` (call-counted). Backtester/
simulator expose no exchange surface. Research harness: no
exchange-write tokens. AI (`core/research/researcher/providers`)
imported ONLY by research; pipeline/risk/execution/broker import
none of it; `ai_analysis` stays `None` through real runs
(advisory-only). `ALLOW_LIVE` false; `LIVE_MODE` false.

## 13. Strategy immutability (§23) — HELD

No threshold/period/scoring/filter/target/stop/frequency/regime/
hypothesis change. The 30k soak lost money (see §14) — REPORTED.

## 14. Soak (§25/§26) + economics (§24/§41)

30,000 continuous 1m candles (seed 42), ONE run, ~15 min:

```text
bars=30000 trades=192 opened=192 balance=1989.548299
realized=-10.451701 (net, zero-cost profile)
violations=[] order_rr_min>=6.0 fractal_cache=5000 (bound holds)
backtester_pending_peak=7 open_peak<=1 registry=192
exchange_writes=0
```

Economics (PAPER ONLY, NOT OOS): gross/net/fees/slippage per
§24 reported with profile label; net −10.45 ⇒ ENGINEERING PASS,
STRATEGY EDGE NOT ESTABLISHED (no tuning performed).
Real-data replay: 1440/1440 production candles, finite state.
30k REAL-data soak: INSUFFICIENT_DATA (only a 1440-candle flat
production stub exists; research zips not consumed — they are
frozen research inputs, not paper fixtures).

## 15. Resources (§27) — GREEN with noted ceiling

fractal_cache ≤ 5000 (hits ceiling exactly — bounded, verified);
pending peak 7 (capped); registry grows with closed trades only
(expected retention, single-slot open); no NaN/inf; no
cross-symbol contamination; no bypass (orders flow only via
RiskEngine → registry → simulator).

## 16. Determinism (§28) + causality (§29) — GREEN

10k double-run metrics JSON byte-identical (340 s background
run, 1 passed). Small-run double identical. Causality:
future-dataset and future-outcome mutations leave all
pre-boundary decisions identical (engineering test, not OOS).

## 17. Config governance (§30) — HELD

`MIN_RISK_REWARD = 6.0` untouched. Shadows (confidence 70 vs 80,
regime 70, sizer scalers, execution fallback) documented,
unchanged. Only additions: paper cost block + kill-switch env
name (both new authority, no shadow).

## 18. Gates (§37)

```text
Repository Integrity : GREEN (closure commit verified, research clean)
Security             : BLOCKED (history exposure; tracked scan clean)
Cost Configuration   : YELLOW (explicit; venue values CONFIGURATION_REQUIRED)
Accounting           : GREEN
RR 1:6               : GREEN (order-time; fill erosion measured YELLOW)
Risk                 : GREEN
Paper Execution      : GREEN
Order Lifecycle      : GREEN
Reconciliation       : GREEN
Restart Recovery     : GREEN (drills; RAM-only limits documented)
WebSocket            : GREEN (gap repair NOT_IMPLEMENTED → YELLOW aspect)
Kill Switch          : GREEN (new seam, tested)
Multi-Symbol Paper   : GREEN
Paper/Live Isolation : GREEN
Resource Bounds      : GREEN
Determinism          : GREEN
Causality            : GREEN
Research Integrity   : GREEN (byte-unchanged, seals green)
OOS                  : ABSENT/BLOCKED
Strategy Edge        : NO EDGE ESTABLISHED
Live Safety          : NO-GO
```

## 19. Verdict

```text
PAPER: CONDITIONAL
ENGINEERING: PASS (one real observability defect found + fixed)
STRATEGY: NO EDGE ESTABLISHED (negative economics preserved)
OOS: ABSENT/BLOCKED | D3: SEALED | LIVE: NO-GO
SECURITY: BLOCKED until operator remediation
```

## 20. Failures found (§45 — none hidden)

1. Fill-RR erosion invisible (found §6): orders gated at RR≥6
   were filled at next-open prices with realized RR as low as
   0.02 and nothing recorded it. SEVERITY: medium (observability;
   dollar risk was preserved; no policy bypass at order level).
   REMEDIATION: `actual_risk_reward` stamped + logged at every
   mutating fill; soak reports distribution. REMAINING RISK:
   erosion itself is market reality (YELLOW).
2. Six Stage-4 test-authoring bugs (wrong API assumptions:
   sizer entrypoint, registry signatures, neutral-cap semantics,
   float repr, print key): all corrected in TESTS only; no
   production change; documented here, not hidden.

## 21. Counts (§44)

```text
QUANTENGINE — STAGE 4 PAPER CERTIFICATION
VERDICT: PAPER CONDITIONAL (engineering PASS; economics negative,
         reported not optimized)

Repository: HEAD = stage4 commit below; branch main; tree clean
  except two pre-existing unrelated notes ("muse suggetions*.md",
  seal-exempted, left untracked)

Security: BLOCKED (6 history commits / 5 blobs reachable;
  tracked-source scan clean; no rotation/push performed)
Cost: YELLOW (formula+abstraction GREEN; venue values
  CONFIGURATION_REQUIRED; soak ran explicit-zero-neutral)
Accounting: GREEN | Risk: GREEN
Reconciliation: GREEN | Restart: GREEN (limits documented)
WebSocket: GREEN (GAP_REPAIR = NOT_IMPLEMENTED → YELLOW aspect)
Order Lifecycle: GREEN | Kill Switch: GREEN (new seam)
Multi-Symbol: GREEN | Production Isolation: GREEN
Determinism: GREEN | Causality: GREEN
Soak: GREEN (30000 synthetic; real-data 1440 replay GREEN;
  30k real-data INSUFFICIENT_DATA)
Research: UNCHANGED (git diff empty; freeze f803fe7d; D3 sealed)
OOS: ABSENT/BLOCKED | Strategy: NO EDGE ESTABLISHED | Live: NO-GO

Stage 4 tests: 57 (cert, incl. WS storm) + 3 (soak file:
  30k invariants, 10k×2 determinism, parquet replay) = 60,
  all passed
Full-suite tests: 2726 passed + 16 tree-seal = 2742 total;
  post-commit 2742 passed, 0 failed, 0 errors, 0 skipped,
  0 collection failures
Compileall: clean
Soak events: 30000 candles (seed 42, BTCUSDT)
Symbols: BTCUSDT (soak) + BTCUSDT/ETHUSDT (multi-symbol cert)
Orders: 192 opened / Fills: 192 / Rejected: 0 (scripted-path
  rejects covered in cert) / Expired: covered in cert
Duplicate suppressions: registry identity asserted across 6
  vectors / Reconciliation halts: all 10 classes + startup B/C
Restart drills: 12/12 safe (10 resume, 1 partial-halt, 1 relatch)
WS reconnects: resubscribe path exercised / Malformed frames:
  >0 isolated, pump survives / Stale events: health degrades,
  no order surface / Gap events: jump delivered, never repaired
  (NOT_IMPLEMENTED, documented)
Resource maxima: fractal_cache 5000 (bound holds),
  pending_peak 7, registry 192, open_peak ≤ 1
Determinism result: byte-identical (10k×2 + small runs)
Causality result: pre-boundary decisions identical under both
  future mutations
Exchange write calls: 0 (paper) / 0 (research) / 0 (AI — no path)
Research modifications: 0
```
