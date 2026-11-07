# Phase 11G-P — Fresh Data Accumulation + Full OOS Readiness Gate

DATA-ACCUMULATION AND READINESS ONLY. No hypothesis run, created,
modified, or evaluated. No economics of any kind (proven by scan —
no PnL/expectancy/Sharpe/Sortino/PF/win-rate/drawdown/baseline/
Monte-Carlo tokens in code or artifacts). No optimization. No D3
contact (counters 0/0/0 before, during, after). Frozen 11G-K hashes
re-verified; H004/H007 stay failed; nothing resurrected, nothing
promoted.

## 1. Starting HEAD / Final HEAD / Branch / Tree

Start: `501f082d1b037f1d9461d243310d68b95282a2a7`
(`research(phase11g): certify fresh-data expansion and OOS
readiness`), branch `main`, tree clean except the two pre-existing
untracked notes files. Final HEAD = the P commit (see git log). No
history rewritten.

## 2. Latest Known Exposed Timestamp / Fresh Cutoff

Re-derived from artifacts (not assumed): latest exposed research
minute 2026-09-08T23:59Z (1788911940, N clean spans). Deterministic
cutoffs: PRE_CUTOFF 1788751380 (oos end; BTC pre-cutoff drop
re-applied verbatim) and FRESH_START_P 1788912000
(2026-09-09T00:00Z). Rule: P datasets require every event >=
FRESH_START_P. All P clean minutes end strictly before it
(BTC 09-07T03:24→09-08T23:59; ETH 09-07T00:00→09-08T23:59) — the
next-expansion gap is real and recorded.

## 3. Provider Availability (Observed, Not Assumed)

Live Vision CHECKSUM probes at analysis time: HTTP 404 for
09-09→09-16 daily aggTrades, both BTCUSDT and ETHUSDT; 09-08 remains
the newest acquirable day. Result: DATA_NOT_YET_AVAILABLE (recorded
as provenance observation metadata, excluded from deterministic
hashes). No scraping, mirrors, invented endpoints, or fabrication.
P new files acquired: 0.

## 4. Dataset Inventory (Per Symbol/Date)

| Dataset | Bars clean | Events clean | Source == provider sha | Freshness | Overlap |
|---------|-----------|--------------|------------------------|-----------|---------|
| BTCUSDT 2026-09-07 | 1,236 | 592,555 | yes | REUSED | ZERO (5/5) |
| BTCUSDT 2026-09-08 | 1,440 | 1,028,583 | yes | REUSED | ZERO |
| ETHUSDT 2026-09-07 | 1,440 | 829,122 | yes | REUSED | ZERO (3/3) |
| ETHUSDT 2026-09-08 | 1,440 | 974,949 | yes | REUSED | ZERO |

N store re-verified immutable (all 4 zips re-hash to acquisition
manifests). Clean totals: BTC 2,676 bars; ETH 2,880 bars;
3,425,209 events. Freshness is REUSED, not FRESH: N/O performed
descriptive analysis on these minutes (no fits, no economics — but
exposure is exposure, and §18 admits only FRESH toward the
threshold). D3 overlap UNKNOWN_BY_SEAL (never inspected, by design).

## 5. Data-Quality Results

Re-parsed 3,572,238 rows: 0 rejected, 0 duplicate IDs, 0
out-of-order, 0 bad-precision. Contiguity: BTC 2,676/2,676 expected,
ETH 2,880/2,880, gaps 0/0, largest gap 0. Nothing dropped silently
(the 204 pre-cutoff BTC minutes + ~147k events are excluded by the
deterministic rule and counted, not hidden).

## 6. REAL / PROXY / UNAVAILABLE Matrix

Trade price/quantity/ms-timestamp/agg-IDs/provider aggressor side
REAL; trade-built OHLCV/delta/CVD/footprint/imbalance/aggression
DERIVED_FROM_REAL; event model aggregate (aggTrade != fill).
PROXY: none. UNAVAILABLE: L2/quotes/resting/queue/book-depletion/
spread/liquidations/order-book data. No upgrades.

## 7. Regime Coverage (Descriptive)

Return-bps deciles, ATR context, up/down day splits, and
events/minute recomputed per symbol (same minutes as N/O; values
consistent). Thin trend variety stands as a limitation. No
thresholds fit; descriptives must not be reused.

## 8. Symbol Coverage

BTC: 09-07T03:24→09-08T23:59, 2,676 bars, ~606 ev/min. ETH:
09-07T00:00→09-08T23:59, 2,880 bars, ~626 ev/min. Evaluated
separately; never pooled.

## 9. Registered WF Geometry / Per-Symbol Feasibility

Authoritative 2000/1000/150/25/1000/4 → 6,175 bars required. Actual
certified builder probed per symbol: BTC 2,676 → raises
(FULL_WF_INFEASIBLE, folds []); ETH 2,880 → raises
(FULL_WF_INFEASIBLE, folds []). Positive control: 7,000-bar build
yields nested expanding trains [0,2000)→[0,5000) with registered
test/purge/embargo boundaries. No shrinkage, no rolling, no custom
folds, no stitching.

## 10. D3: READ 0 / HASH 0 / LOAD 0

Before, during (in-artifact), after. No D3 use for overlap, scale,
freshness, sample-size, selection, cutoff, or benchmarking. A D3
access attempt is refused in-test with counters still 0.

## 11. Mutation Results (MUT-P1..P18)

P1 future contamination GREEN. P2 duplicate IDs GREEN. P3 ordering
GREEN (totals invariant, sequence flagged). P4 timestamp corruption
GREEN. P5 negative quantity GREEN. P6 invalid aggressor GREEN
(60/60 rejected). P7 source-hash tampering GREEN. P8 code-hash pin +
tamper GREEN. P9 symbol binding GREEN (manifest == directory).
P10 venue/cutoff tampering GREEN. P11 freshness tampering GREEN.
P12 overlap tampering GREEN (detector positive control + tamper
hash). P13 contiguity manipulation GREEN. P14 WF shrink GREEN. P15
rolling GREEN. P16 D3 access GREEN. P17 hypothesis modification
GREEN. P18 economics attempt GREEN (no econ tokens in P code; no
econ keys in artifacts).

## 12. Lookahead Result

Fixture-level: future-appended trades leave earlier bars, volumes,
quality counters, overlap hits, and freshness labels identical.
Full-analysis determinism: `analyze_p()` rerun byte-identical vs
committed `readiness_p.json`.

## 13. Production Isolation Result

AST import scan of `research/phase11g_p/`: stdlib + `research.*`
only (no httpx even — probes were manual observations, not repo
code). Zero production/execution/risk/order/ledger/position/paper/
shadow/live imports, tokens, or config writes.
`PReadinessReport.is_production_ready` permanently False (enforced;
verdict→recommendation mapping pinned). Production tree clean; LIVE
unset.

## 14. Test Counts (Reconciled, §31/§32)

Phase P file: 47/47. Research suites: 422/422 (P implementation
carries no test files under `research/`; P tests live in `tests/`
per convention). Main suite: 2,272 + 47 = 2,319 collected
(2,181 baseline + 42 N + 49 O + 47 P — each delta explained):
0 failed, 0 errors, 0 skipped. Two additive tree-allowlist edits
disclosed (N and O tree tests gained the three P paths; post-commit
behavior identical — tree shows notes alone). No test weakened; no
production file touched. Compileall clean. `git diff --check`
clean. Gate A ×2: 27/11/6/5/0/+0.117534, identical IDs.

## 15. Documentation Convention (§35)

No STATUS.md / import_manifest / project_manifest updates: git log
proves 11G-K/L/M/N/O (all research-only) made none — those manifests
track production files, and P adds none. PHASE 11G-P recorded here.

## 16. Final Decision: PATH B — MORE DATA REQUIRED

Contiguous qualifying bars 2,676/2,880 << 6,175 required, and
qualifying FRESH bars = 0 (REUSED minutes cannot satisfy §18).

```
RECOMMEND_NEXT_PHASE = DATA_EXPANSION_REQUIRED
```

Re-audit trigger (arithmetic): ≥6,175 contiguous zero-overlap clean
bars with FRESH (not REUSED) classification on one symbol, all
events >= FRESH_START_P. STOP. No OOS economics, no D3 opening, no
new hypotheses.

## 17. Limitations

Two symbols/two days; REUSED minutes; D3 era unknowable; Vision lag
+ retrospective provider updates; no bulk quotes/L2/funding/OI;
thin trend variety; pre-cutoff boundary drops excluded from scale;
freshness-vs-checkable-set only (D3 UNKNOWN_BY_SEAL); any future
preregistration must re-derive admissibility of described minutes.
