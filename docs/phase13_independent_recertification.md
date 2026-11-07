# PHASE 13 — INDEPENDENT RECERTIFICATION, STRATEGY VIABILITY & TRUE OOS READINESS

Status: RESEARCH / RECERTIFICATION. Not optimization. Not live. Not promotion.
Parent: Phase 12 commit `c145f06`. Frozen strategy untouched. 1:6 invariant untouched.

## 1. BASELINE REPRODUCTION (all VERIFIED)

- HEAD `c145f06`, parent `3973350`, branch `main`, tree clean except 2 pre-existing
  untracked notes.
- `pytest tests/ --collect-only -q`: **2849 collected** (stable across consecutive runs).
  - Note: Phase-12 baseline number was 2836. Delta +13 is exactly the uncommitted
    Phase-13 test additions present at audit time: lookahead 3, simulator-sign 5,
    SHORT-gap 3, LONG-gap 2. No other delta.
- Gate-A (`python -m scripts.verify_gate_a`): **PASS, byte-identical double run** —
  orders 25, fills 2, wins 0, losses 2, breakevens 0, net -0.206452. Recalculated
  from execution records (not from the report line): registry shows
  15 EXPIRED / 8 INVALIDATED / 2 FILLED = 25. VERIFIED.
- `is_production_ready`: permanently False (research report guards raise; verified
  in source). LIVE defaults deny (PAPER_MODE true, LIVE_MODE/ALLOW_LIVE false).

## 2. PHASE-12 CLAIM VERIFICATION

| Claim | Verdict | Evidence |
|---|---|---|
| P0-1 ack-before-FILLED | VERIFIED | `core/execution/order_ack.py` states + `classify_ack/_exception`; broker consumes at route/fetch/sync; 23 ack tests green |
| P0-2 executor exceptions | VERIFIED | try/except route seam, `_live_trade=None`, `_last_error`, halt; exception tests green |
| P0-3 security/history | VERIFIED | `.env` untracked, example keys-only, log untracked, banner secret-free; history compromise documented not purged |
| P1 kill switch | VERIFIED | seam consulted in RiskEngine creation, backtester pending+legacy, broker dry+live route, paper fills; 25 gate tests green |
| P1 loss limits | VERIFIED | `loss_limit_blocked()` wired in RiskEngine; UTC/ISO/month rolling; equality blocks; non-finite fail-closed; tests green |
| P1 max positions | VERIFIED | structural single-slot + pinned test (no silent second fill) |
| P1 legacy path | VERIFIED | backtester legacy branch gated (kill+geometry+RR); paper fallback gated (Phase-13 addition); production callers enumerated — all gated |
| P1 geometry | VERIFIED | `directional_geometry_ok()` canonical; builder+risk+legacy+paper gates; unit tests green |
| P1 actual-fill RR | VERIFIED | pre-mutation revalidation; erosion refusals logged with values; + Phase-13 inverted-fill fix (see §4) |

## 3. GATE-A EROSION DECOMPOSITION (frozen 5000-bar snapshot, zero-cost config)

Funnel: **3687 setup-discovery events → 25 orders (0.68%) → 2 fills (8% of orders)**.
Order terminals: 15 EXPIRED / 8 INVALIDATED / 2 FILLED. Fills: BULLISH actual 7.44,
7.911 (both ≥ 6 — invariant held on every fill).

Refused (23): 22 triggered-then-evaluated + 1 never-triggered (pre-trigger
invalidation). Creation gate held 100%: pre-fill RR ≥ 6 on 23/23 refused
(median 44.20, mean 67.91, min 6.47, max 351.00).
At the actual open: median 0.332, mean 1.110, min 0.0441, max 7.911.
Erosion delta (pre − actual): median 43.97, mean 68.59, worst 350.73, best 0.00.
Adverse open gaps (signed by direction): median 273 pts, min 0.0, max 1948.0;
**favorable-gap refusals: 0**. Median risk distance 22.5 vs median reward 646.4 —
tight stops make any next-bar gap fatal to 6:1.
Actual RR ≥ 6 after trigger: 1/22 evaluated (that one EXPIRED via correct
single-position block against its filled sibling, not via erosion).
Fees/slippage erosion: exactly 0.0 (zero-cost defaults) — classification is
21× ENTRY_GAP + 1× never-triggered + 1× position-blocked; 0× SLIPPAGE/FEES.

Hand-verified worst case (BULLISH E 77483.5 / O 77760.0 / S 77482.5 /
T 77834.5): pre 351.0 → actual 0.2685, matches `order_rr` exactly.
Smallest-adverse-gap refusal: 40-pt gap erodes 9.05 → 4.15 (refused correctly).

## 4. EXECUTION-MODEL FINDINGS

- NEXT_BAR_OPEN semantics VERIFIED: trigger-at-close (high> E and close > E /
  mirror), fill at OPEN of trigger+1 (`_next_bar_open_price`, close-fallback only
  for open-less fabricated bars), invalidation-before-fill ordering, SL-first
  ambiguity, resize-then-stamp ordering.
- **Phase-13 regression found and fixed**: unsigned-only erosion check admitted a
  gap-THROUGH-target fill (LONG open > target can still read RR ≥ 6 only in
  degenerate geometries; the reachable hole was gap-through-target with
  mid-size RR). Fix: `directional_geometry_ok()` runs FIRST at execution time
  (`ORDER_SKIPPED_INVERTED_FILL`); gap-through-stop was already unreachable
  (any such bar breaches first → INVALIDATED, proven by test). No threshold or
  strategy logic touched; Gate-A re-ran IDENTICAL after the fix (25/2/−0.21).
- Gap matrix (LONG/SHORT × above-target/below-stop/between): refused-or-
  invalidated in all 8 cells, proven by new adversarial tests; boundary
  O==S / O==T refused. No inverted or phantom fills exist on any gated path.
- Simulator: exits at stop/target levels only; SL-first; gross from actual
  entry; net of booked commission/slippage; sign-adversarial tests (incl.
  same-bar ambiguity both directions) green. No WIN-with-negative-gross reachable.
- Invariant holds: **NO POSITION MAY BE CREATED WITH ACTUAL-FILL RR < 6** on any
  production path (LIMIT: entry==intended; breakout: revalidated; legacy/paper:
  gated; direct `open_trade` callers are tests only — enumerated).

## 5. STRATEGY VIABILITY (frozen strategy, no tuning)

- Executable opportunity rate: 2 fills / 5000 bars = 0.04 per 100 bars
  (~1 fill per 2500 bars; ~52 days of 1m data per symbol for 30 trades).
- Pre-fill RR ≥ 6: 25/25 (100%). Post-trigger actual RR ≥ 6: 2/24 (8.3%).
- Fill rate 8% of orders; RR-rejection-at-fill 87.5% (21/24); expiry 60% of
  orders; invalidation 32%.
- Median actual-fill RR over evaluated: 0.332. Mean 1.110. Worst 0.0441.
- Economics: gross = net = −0.206452 on N=2 — reported, never a claim.
- **Outcome B: LOW EXECUTABLE OPPORTUNITY.** The engine correctly enforces its
  rules; the frozen BreakoutContinuation strategy almost never survives them on
  observed data. This is strategy/execution interaction, NOT a software defect
  (erosion math hand-verified; §4 fix closed the one real hole).
- Per §41: no RR lowering, no stop/target/threshold/filter changes made or proposed.

## 6. MARKET DATA — Status: PARTIAL (unchanged, itemized)

Covered: closed-only routing, forming-candle suppression, per-symbol builders,
timestamp normalization (s/ms/us/ns, bulk == streaming), bounded router dedupe
(watermark makes eviction safe — prior re-admission claim disproven by test),
gap DETECTION with per-symbol counters, deterministic repair_gaps() via
injectable fetcher (normalize+validate+sort+dedupe; never fabricated/merged),
DATA_GAP_UNREPAIRED exposure, paginated under-fetch fix, legacy WS marked
DEPRECATED. Missing for production-grade connectivity: venue sequence numbers
(venue provides none on this feed), automatic repair wiring (explicit call
only), socket-level heartbeat on legacy path (deprecated, not retrofitted),
REST/WebSocket disagreement policy beyond staleness/health. No upgrade claimed.

## 7. RECONCILIATION — Status: PARTIAL (unchanged, itemized)

Authoritative source: exchange (positions/fetch/balance reads). RAM mirror is
working state only; journal (atomic tmp+replace, ack_state+order_seq, schema v1
additive) is crash evidence, not truth. Cadence: ~30-bar runtime checks +
startup check + halt on any unexplained divergence (halt NOT persisted —
re-derived on restart, documented). Reconnect: workers own retry with backoff;
resubscribe replays are duplicate-dropped by the router. Partial fills halt
(never booked as FILLED). Cancelled/expired orders clear the watch. Position/
balance mismatch → halt. A live system depending indefinitely on RAM is not
endorsed: LIVE = NO-GO remains on this ground among others.

## 8. H2 / H3 — DEFERRED WITH JUSTIFICATION (not silently complete)

- H2 (async scheduler wiring): performance optimization (provider-poll p95),
  not a correctness gate; sync scheduler is correct, merely blocking. DEFERRED.
- H3 (live equity sync while in position): affects only the never-armed live
  path (LIVE blocked; paper uses the local account). DEFERRED until any live
  consideration, which is itself blocked.

## 9. RESEARCH INTEGRITY — preserved

`research/` + `docs/audit/` byte-unchanged (verified via git diff empty).
H004/H007 FAIL, H001–H003 insufficient, H005/H006/H008 no-evidence, L no-edge,
M NO-GO, Q–U data-insufficient, 11G-Q full-WF gate intact (`gate.py` present,
threshold 6,175 bars preserved). Freeze tests green. No reinterpretation.

## 10. CONNECTIVITY — Market Structure CONNECTED; Liquidity CONNECTED;
Displacement CONNECTED; FVG CONNECTED; OB CONNECTED; Order Flow ORPHANED
(`price_ladder_stage` zero production importers); Wyckoff RESEARCH_ONLY
(descriptive research features; prod mentions are comments); Fibonacci
RESEARCH_ONLY (same). No wiring added (would be strategy expansion).

## 11. MICROSTRUCTURE TRUTH

Historical candles are OHLCV-only (timestamp/open/high/low/close/volume/closed/
symbol — verified in `core/history/candle.py`; no tick/aggressor/bid-ask/depth
fields anywhere in the loader). Maintained: FOOTPRINT = UNAVAILABLE,
ORDER_FLOW_DELTA = UNAVAILABLE, CVD = UNAVAILABLE, HISTORICAL_L2 = UNAVAILABLE.
Nothing OHLCV-derived is called footprint.

## 12. ECONOMIC REALISM

Fees/slippage: explicit-zero defaults (placeholder for live economics, honest
for gross-theoretical backtests; every report carries its cost_basis label).
Spread: unmodeled (mark=bid=ask=close). Funding: absent (no field; perps carry
no funding leg in the simulator — documented limitation). Minimum order
constraints: contract-validated live-only; generic dust/precision on paper
paths (fidelity gap stated). Zero-cost results are never production economics.

## 13. OOS — INFRASTRUCTURE AVAILABLE, EVIDENCE ABSENT

Frozen 11G-Q gate (6,175 fresh bars) intact and unmet. No new OOS claimed.
Single-holdout evidence (7E) exists but rejected its hypothesis; multi-period
OOS (OOS-1..N with per-period sample/trades/expectancy/drawdown reporting)
does not exist. Sample-size rule enforced: Gate-A N=2 fills is reported as
data, never as evidence of anything.

## 14. TEST INTEGRITY (§31) — 40 files audited, verdicts:

- NEW (strict, all green): 8 files — ack (23), risk-gates (25), confirmed-bar
  (9), market-data (8), memory (4), security (6), lookahead (3); plus added
  classes: accounting-geometry (10), cost-basis (2), simulator-sign (5).
- VALID CORRECTION (~20 files): sub-6:1 scripted fixtures → compliant geometry
  (hardening, contract, paper, position, portfolio ×5, optimizer, walk-forward,
  router, comparison, journal, feasibility, breakout opens); economics pins
  updated arithmetically (no assertion removed, several added).
- REQUIRED UPDATE: Gate-A pin (honest baseline move, determinism subject
  untouched), cert/soak seeds 42→6 (fills must exist; disclosed), freeze-guard
  re-scope (research freeze preserved, disclosed supersession), demo-file
  import guards (pipeline_runner network-at-import fixed).
- WEAKENING: none. QUESTIONABLE: none. (Optimizer mixed_series loss-leg →
  ride-through is disclosed with coverage pointer; portfolio sum 0→8.5
  preserves the identity structure.)

## 15. GATE MATRIX

| Gate | Result | Blocker? |
|---|---|---|
| P0 execution correctness | PASS (ack truth + inverted-fill fix, tested) | No |
| executor exception safety | PASS (typed failure, cleanup, alive) | No |
| security | CONDITIONAL (tree clean; history compromise = operator action) | Yes (operator) |
| kill switch | PASS (creation+pending+legacy+paper+live-route) | No |
| loss limits | PASS (daily/weekly/monthly wired, boundaries tested) | No |
| max positions | PASS (structural single-slot, pinned) | No |
| legacy path isolation | PASS (all production callers gated; direct calls test-only) | No |
| stop geometry | PASS (canonical helper, all gates) | No |
| actual-fill R:R | PASS (pre-mutation + geometry, 8-cell gap matrix) | No |
| market data | PARTIAL (itemized §6) | Yes (for live) |
| reconciliation | PARTIAL (itemized §7) | Yes (for live) |
| strategy connectivity | PASS (as documented; orphans classified) | No |
| research integrity | PASS (frozen, verdicts stand) | No |
| test integrity | PASS (40/40 classified, none weakening) | No |
| determinism | PASS (identical double-runs; multi-boundary lookahead) | No |
| lookahead | PASS (3 boundaries × 3 futures, byte-identical pre-T) | No |
| OOS infrastructure | AVAILABLE (gate intact) | — |
| OOS evidence | ABSENT | Yes (for promotion) |
| economic realism | HONEST (labeled gross-theoretical; costs zero by config) | Yes (for live) |
| production isolation | PASS (FORBIDDEN-token tests + mock guards) | No |
| live readiness | NO-GO (gates above + viability outcome B) | Yes |

## 16. FINAL STRATEGY CLASSIFICATION

EDGE = NOT ESTABLISHED (unchanged). Viability outcome: **B — LOW EXECUTABLE
OPPORTUNITY**. No optimization, no promotion, no live trading. The correct
next step, if any, is a research decision about the strategy family — explicitly
out of scope for this phase. STOP.
