# Phase 11G-A — Causal Institutional Feature Engineering Report

STAGE A ONLY. No hypotheses. No backtests. No P&L. No winners. No D3.
Economic edge: NOT TESTED.

## A. Executive Summary

STATUS: GREEN — 11G-A feature-engineering infrastructure complete:
capability matrix, contracts, 12 causal feature modules (+shared result
schema), MTF resampler, Wyckoff/mitigation/session/volume engines,
scoreless confluence layer, availability snapshot, 88 causality/
mutation/determinism tests green, main suite 2188 green, Gate A
unchanged ×2, production untouched, D3 sealed, LIVE disabled.

## B. Starting Git State

HEAD `e3e6f4b75bd166529e4c35f59a6a68a53bbc7fbb` (11F methodology
recertification), branch `main`, tree clean except pre-existing
untracked `muse suggetions*.md`. 11F semantic suite re-verified green
pre-work (12/12).

## C. Phase 11F Integrity

Untouched: `git status -- research/phase11f` empty throughout
(enforced by `test_production_isolation.py::test_phase11f_untouched`);
all work under `research/phase11g/` (adapters wrap 11F, never fork it).

## D. Data Capability

`data_capability_matrix.json`: 17 fields classified. OHLCV 1m = REAL
(only historical market data). Trades/side/size, bid/ask/sizes, book,
book deltas, depth, liquidations, funding, OI, volume-at-price,
footprint = UNAVAILABLE (no endpoints, no feeds). HTF files =
UNAVAILABLE (derived-only path). Key finding: `core/orderflow`
replay delta is OHLCV-estimated (`mode="ESTIMATED"`); only the live
provider uses real trades, which has no historical feed and is
research-forbidden. Any "footprint strategy" on this data would be an
OHLCV proxy strategy — the matrix makes that confusion impossible.

## E. Data Lineage

`datasets.py`: D1/D2 descriptors (counts/windows/symbols, CONTAMINATED
by prior 11F exposure, disclosed); content-hash slot explicitly
unfilled until Stage B (no candle reads in Stage A — enforced by test);
D3 SEALED with refusal-before-I/O + access counters (read/hash/load 0).

## F. Feature Contract

`feature_contracts.json`: F(i)=function(bars[0..i]);
availability ≤ decision, availability ≥ confirmation, no backdating;
result schema (name/value/status/formation/confirmation/availability/
source/causal/metadata/provenance). All 4000+ result dicts across
modules conform (schema + timestamp-order test).

## G. Structure

Adapter over certified swings/donchian/range/EMA + new HH/HL/LH/LL
trend derivation, BOS, CHOCH (against-trend only). Confirmation-lag
proven (peak e=2 visible at 3, never 2).

## H. Liquidity

Prior confirmed swing refs, prior-session high/low (day-1 only after
session end; UTC-day convention documented), running session
extremes/volume (prefix-only), range boundaries, equal levels.
Neutral sweep/session-sweep event records (level/type/direction/
penetration/reclaim/confirmation, no signals). 11F sweep thresholds
NOT relaxed (post-result tuning forbidden).

## I. Displacement

Certified `range > mult*ATR14` (frozen mult) + causal body/range/close-
location/consecutive descriptors. Stricter mult provably fires less.

## J. FVG

Certified zones + formation (third bar = first two back)/
confirmation/availability, ATR-normalized size, boundaries, age helper.
Thresholds frozen.

## K. Order Blocks

Frozen anchor rule (last opposite candle, strictly exclusive lookup —
anchor index < reference always, tested). Zone/invalidation exposed;
future-anchor mutation covered.

## L. Breakers

Event representation (failed level, crossing-confirmed, zone,
invalidation); availability = crossing bar; isolation proven (fresh
instance at trigger bar emits nothing — setup/trigger separation).

## M. Mitigation

Deterministic machine: UNTOUCHED→TOUCHED→PARTIALLY_MITIGATED(≥50%)
→MITIGATED(100%/traverse-with-hold)→INVALIDATED(close-through);
first_touch/count/penetration/last_touch; pre-confirmation pending;
future-touch invariance proven. (One genuine gap found by tests and
fixed: through-traversal penetration is now 1.0, not 0.0.)

## N. Volume

Trailing mean/median/rvol/percentile-rank regimes/expansion —
REAL measurement, neutral labels ("institutional volume" banned by
test). Hand-verified values; no centering (future-append invariance).

## O. Wyckoff

SPRING/UPTHRUST/SECONDARY_TEST/SIGN_OF_STRENGTH as timestamped events
(context/trigger/confirmation/availability/invalidation). Key finding:
ranges MUST be evaluated on strictly-prior bars — an inclusive
Donchian window can never be swept by its own bar (this latent
 unsatisfiability also explains H11F-003/004's 11F-4 zeros; 11F left
frozen, finding reported not repaired). Secondary test requires a
prior spring; SOS requires displacement.

## P. Fibonacci

Thin adapter over certified frozen ratios/anchors; confluence flag
(close within 0.1 ATR, frozen). Confluence-only, never directional.

## Q. Multi-Timeframe

Exact 1m→15m resampler (bucket [T,T+900) available only at T+900;
terminal incomplete bucket excluded; gaps deterministic partial).
HTF trend/range/volatility over closed candles; LTF mapping by
availability. All 8 mandated cases proven incl. hostile future-HTF.
One test assertion corrected during development (boundary-exact append
legitimately closes a bucket — resampler right, test wrong; recorded).

## R. Confluence

Descriptive dict over 11 fixed fields; `score/weight` keys raise;
unknown fields raise; provenance map. No weights anywhere in Stage A.

## S. Causality

Availability ≤ decision on every OK result (24 series × 200 bars);
`known_at`/`confluence_at` hide future-dated entries; hostile
methodology extended per-family (§30 tests).

## T. Mutation Tests

M11G-01…14: future structure/liquidity/displacement/FVG/OB/breaker/
mitigation/Wyckoff/Fibonacci/volume/HTF all DETECTED (prefix
equality); normalization-leak proven catchable (trailing vs full mean
differ, certified path uses trailing); D3 bypass BLOCKED (raises);
provenance honesty pinned. 14/14.

## U. Prefix Invariance

Prefix-vs-full equality (structure×2 shown, pattern general);
MTF closed-bucket stability; mitigation stepwise==batch (pure left
fold proven by construction + test).

## V. Determinism

Double-run identical incl. SHA-256; MTF identical; no
random/wall-clock/network tokens in any module (scanned).

## W. Production Isolation

No execution/credential tokens in 11G sources; monkeypatched
`DeltaOrderExecutor.execute`/`BrokerEngine.__init__` never reached;
11F tree untouched (git-verified); ALLOW_LIVE/LIVE_EXECUTE false.

## X. D3 Isolation

Blocked-before-I/O (raises); counters read/hash/load = 0; source scan
proves no D3 content access in any 11G file; Stage-A tests never call
`content_hash`; datasets carry no D3 metadata beyond the certified
seal fact.

## Y. Gate A

PASS ×2: 27/11/6/5/0/+0.117534, identical IDs. (One invocation timed
out under machine contention with stale processes; stale PIDs cleared,
clean reruns green — no code cause.)

## Z. Full Test Suite

Phase-11G suite: 88 passed, 0 failed. Main `tests/`: 2188 passed,
0 failed, 0 collection errors. `compileall`: clean. `git diff --check`:
clean.

## AA. Performance

7001 bars × 24 series: initially 224.8s/494MB (O(n²) adapters) →
single-pass rewrite (identical outputs, suite green): 2000 bars in
3.9s (~1.9ms/bar, ≈14s per 7001-bar universe). Correctness first,
then measured rewrite — semantics proven unchanged by the same tests.

## AB. Limitations

Listed in full in `research_log.json` + §47 of the authorizing
prompt: OHLCV-only history; no REAL historical order flow; proxies ≠
flow; D1/D2 contaminated; D3 sealed; MTF derived; Wyckoff newly
formalized (needs Stage-B validation); no economic conclusions.

## AC. Recommendation for Stage B

APPROVED TO PROCEED: freeze ≤8 hypotheses (keeps Bonferroni 0.00625;
cut/rebuild the 12-idea list — H11G-010/011 need proxy reframing,
H11G-012 needs the MTF path first), preregister with ablations,
execute on D1/D2 under 11F machinery, D3 sealed. No scores without
preregistered weights. Negative results are success.
