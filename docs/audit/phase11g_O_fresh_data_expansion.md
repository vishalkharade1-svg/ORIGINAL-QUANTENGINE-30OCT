# Phase 11G-O — Controlled Fresh Data Expansion + OOS Readiness Certification

DATA/INFRASTRUCTURE ONLY. No hypothesis run, created, modified, or
evaluated. No economics (no PnL/expectancy/Sharpe/PF/win-rate/
drawdown/baseline/Monte-Carlo anywhere in code or artifacts — proven
by scan). No optimization. No D3 contact (counters 0/0/0 before,
during, after). Frozen 11G-K hashes re-verified; H004/H007 stay
failed; nothing resurrected, nothing promoted.

## 1. Starting HEAD / Final HEAD / Branch / Tree

Start: `7c9d156d6076b0cc974fb5e0cf24bbe40c2ec3d2`
(`research(phase11g): audit fresh-data scale and research
eligibility`), branch `main`, tree clean except the two
pre-existing untracked notes files. Final HEAD = the O commit (see
git log). No history rewritten.

## 2. Prior-Data Boundary / Fresh-Data Cutoff

Latest exposed research minute (verified from the N artifact, not
assumed): 2026-09-08T23:59Z (1788911940). Deterministic cutoffs (no
wall clock): PRE_CUTOFF 1788751380 (oos end; N BTC filter, re-used
verbatim) and FRESH_START_O 1788912000 (2026-09-09T00:00Z). Rule:
the next expansion acquires only events >= FRESH_START_O. O clean
spans end strictly before FRESH_START_O (gap is real, not assumed).

## 3. Provider/Source Matrix

Binance Vision (official public archive, MIT, per-zip CHECKSUMs):
UM-futures daily aggTrades + 1m klines downloaded for 09-07/09-08
(BTC+ETH) in phase N and re-verified here (source == provider ==
local sha256 for all 8 zips). Live availability probe (observation,
2026-09-09, provenance metadata only): 09-09→09-15 all HTTP 404 both
symbols — the archive lags ~1 day, so 09-08 is the newest acquirable
day. The N estimate naming 09-13 was treated as estimate per the
correction: verified, not assumed. No scraping, no mirrors, no
endpoint invention.

## 4. Dataset Inventory (Per Symbol/Date)

| Dataset | Bars clean | Events clean | Source sha (prefix) | Normalized sha | Freshness | Overlap |
|---------|-----------|--------------|---------------------|----------------|-----------|---------|
| BTCUSDT 2026-09-07 | 1,236 (204 oos minutes dropped) | 592,555 | provider==local | 2d0f70795b23… | REUSED | ZERO (5/5) |
| BTCUSDT 2026-09-08 | 1,440 | 1,028,583 | provider==local | 333a4a458b78… | REUSED | ZERO |
| ETHUSDT 2026-09-07 | 1,440 | 829,122 | provider==local | c30af11f5c8a… | REUSED | ZERO (3/3) |
| ETHUSDT 2026-09-08 | 1,440 | 974,949 | provider==local | 2b9d554d72ef… | REUSED | ZERO |

Clean totals: BTC 2,676 bars / 1,621,138 events (+147,029
oos-dropped events excluded from scale); ETH 2,880 / 1,804,071.
Origins: all 11G-N (re-verified immutable; O acquired zero new
files — nothing newer exists). Freshness REUSED (N descriptive
exposure, no fits, no economics — a future preregistration decides
admissibility); D3 overlap UNKNOWN (sealed; limitation).

## 5. Data-Quality Results

All acquired rows re-parsed: 0 rejected, 0 duplicate IDs, 0
out-of-order, 0 bad-precision. Klines 1,440/1,440 every day, 0
rejected. Trade-built vs provider closes: 1,440/1,440 matched per
day, max abs diff 0.0, 0 mismatches. Every reject class
instrumented; nothing dropped silently.

## 6. REAL / PROXY / UNAVAILABLE Matrix

Price/quantity/ms-timestamp/agg-IDs/provider aggressor side REAL;
OHLCV/delta-class quantities DERIVED_FROM_REAL; event model
aggregate (aggTrade != fill, explicit). PROXY: none. UNAVAILABLE:
L2/quotes/resting/queue/book-depletion/spread/liquidations/funding/
OI/mark (bulk). No PROXY→REAL upgrades.

## 7. Regime Coverage (Descriptive)

BTC+ETH spans resemble N's (same minutes): mixed intraday movement,
both symbols net-down over the window; ATR/return deciles recomputed
in-artifact. Thin trend variety stands as a limitation. No
thresholds fit; deciles must not be reused.

## 8. Symbol Coverage

BTC: 2,676 contiguous bars, 09-07T03:24→09-08T23:59, ~606 ev/min.
ETH: 2,880, 09-07T00:00→09-08T23:59, ~626 ev/min. Gaps 0/0,
missing 0/0. Never pooled (per-symbol WF evaluated separately).

## 9. Registered WF Geometry / Per-Symbol Feasibility

Authoritative 2000/1000/150/25/1000/4 → 6,175 bars required. BTC
2,676 → INFEASIBLE (builder raises). ETH 2,880 → INFEASIBLE
(builder raises). Folds: [] (none manufactured). Expanding origin
preserved (positive control: 7,000-bar build yields [0,2000) →
[0,5000) nested trains). No shrinkage, no rolling, no custom folds.

## 10. D3 Seal: READ 0 / HASH 0 / LOAD 0

Before, during (in-artifact), after. No D3 use for overlap, scale,
freshness, sample-size, selection, or benchmarking. Unknown D3 era
stays UNKNOWN by design (temporal-cutoff strategy, not inspection).

## 11. Mutation Results (MUT-O1..O17)

O1 future contamination GREEN. O2 duplicate IDs GREEN. O3 ordering
GREEN (totals invariant, sequence flagged). O4 timestamp corruption
GREEN. O5 negative quantity GREEN. O6 invalid aggressor flag GREEN
(60/60 rejected). O7 source-hash tampering GREEN. O8 normalized-hash
tampering GREEN. O9 symbol substitution GREEN (file-level binding).
O10 venue substitution GREEN. O11 freshness tampering GREEN. O12
overlap tampering GREEN (detector positive control + tamper hash).
O13 WF shrink GREEN. O14 rolling GREEN. O15 D3 access GREEN
(refused, counters 0). O16 hypothesis modification GREEN. O17
economics attempt GREEN (no econ tokens in O code; no econ keys in
artifacts).

## 12. Deterministic Rerun

`analyze_o()` rerun byte-identical vs committed `feasibility_o.json`
(in-test). No random/UUID/clock/process-hash in deterministic paths;
observation timestamps live only in provenance metadata outside
hashes.

## 13. Production Isolation

AST import scan: stdlib + `research.*` + `httpx` (probe/fetcher
only) — zero production/execution/risk/order/ledger/position/paper/
shadow/live imports or tokens. `OReadinessReport.is_production_ready`
permanently False (enforced; maps verdict→recommendation
deterministically). Production tree clean; LIVE unset.

## 14. Test Counts (Reconciled, §32)

Phase O file: 49/49. Research suites: 422/422 (no O files under
`research/` except implementation — O tests live in `tests/` per
convention). Main suite: 2,272 collected = 2,181 baseline + 42 N +
49 O (prior "2,223" was pre-O; delta fully explained): 0 failed, 0
errors, 0 skipped. One pre-commit adjustment disclosed: the N tree
test's untracked-allowlist gained the three O paths (additive only;
post-commit behavior identical — tree shows notes alone). No test
weakened; no production file touched. Compileall clean.
`git diff --check` clean. Gate A ×2: 27/11/6/5/0/+0.117534,
identical IDs.

## 15. Documentation Convention (§34)

No STATUS.md / import_manifest / project_manifest updates: git log
proves 11G-K/L/M/N (all research-only) made none — those manifests
track production files, and O adds none. Convention followed;
PHASE 11G-O recorded here with mission/acquisition/lineage/
freshness/quality/WF/limitations/boundary/decision.

## 16. Final Decision: PATH B — MORE DATA REQUIRED

Fresh, quality-clean, zero-overlap data exists (2,676/2,880
contiguous bars), but FULL_WF remains INFEASIBLE (need 6,175).

```
RECOMMEND_NEXT_PHASE = DATA_EXPANSION_REQUIRED
```

Re-audit trigger (arithmetic, not a date promise): ≥6,175
contiguous zero-overlap clean bars on one symbol (≈5 clean days from
FRESH_START_O onward). Per the corrected chain: when that scale
exists, the next phase is a NEW PREREGISTERED OOS EXECUTION phase
(frozen hypotheses only) — not paper trading; paper/shadow follow
only genuine OOS evidence.

## 17. Limitations

Two symbols/two days only; REUSED (not pristine) minutes; D3 era
unknowable (UNKNOWN); Vision lag + retrospective provider updates;
no bulk quotes/L2/funding/OI; thin trend variety; boundary drops
(204 BTC minutes) excluded from scale; contaminant-free status
rests on the checkable-set list (§18 roster); any future
preregistration must re-derive admissibility of N/O-described
minutes.
