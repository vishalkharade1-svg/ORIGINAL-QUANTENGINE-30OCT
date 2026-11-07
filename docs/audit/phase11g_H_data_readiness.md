# Phase 11G-H — Historical Data Readiness Report

INFRASTRUCTURE ONLY. No economic experiments. No hypothesis changes.
No winners. D3 sealed. LIVE disabled. Production untouched.

## 0. Session anomaly disclosure (read first)

The 11G-H prompt expected HEAD `34e5072`; live verification showed
HEAD is actually `4c593d4` (11G-G replication, with 11G-E substrate
`95c5d38` and 11G-F family `56b777c` already in history — see reflog).
The substrate modules, order-flow truth model, registry, adapters,
storage, and test files this phase was to build already exist in
committed form and are byte-identical to the working tree
(`git diff HEAD` empty for all of them), so no duplicate or
overwriting work was committed. The GENUINE 11G-H delta in this
commit is: live public-endpoint probes with provenance (`data/
probe_public.py`, `data/probes/`), probe findings (`docs/
probe_findings_11gh.md`), the research-log 11G-H entry, and this
report. All verdicts below rest on live re-verification performed
this session (probe fetch 22:03, suites, Gate A), not on prior claims.

## PHASE: 11G-H
## METHODOLOGY: GREEN

Live public-endpoint verification + provenance capture + seal
re-verification, on top of the committed 11G-E substrate (10 modules,
5 capability docs, 6 test files — pre-existing, verified intact, not
re-authored here).

## DATA CAPABILITY (verified, §5 audit)

Historical: OHLCV 1m (+ multi-TF incl. direct 15m, proven live).
Recent-only: 50 latest trades WITH aggressor roles; L2 snapshot.
Live snapshot: ticker OI/funding/mark. No historical trades/quotes/
book/funding/OI/liquidations/VAP. Mark/OI/funding HISTORY REST paths
unverifiable → UNVERIFIED (not claimed).

## REAL ORDER FLOW: UNAVAILABLE

Decisive probe: `/v2/trades/{symbol}` ignores window params (same 50
returned) — count-capped recent feed. REAL source, zero historical
depth. Replay delta remains OHLCV-estimated. No silent fallback exists.

## PROXY ORDER FLOW

Candle-directional estimates only, explicitly labeled; spread/depth
have NO candle proxy (committed implementation; re-verified live this
session).

## D3: READ 0 / HASH 0 / LOAD 0

No D3 paths in new code (scan-enforced); all seal suites green;
registry refuses D3 registration.

## PRODUCTION DIFF: NONE

`core/ config/ data/ execution/ risk/ backtesting/ main.py` untouched
(status-verified). 11F/11G-A–D artifacts untouched.

## TESTS

Substrate suites re-run live this session: 51 passed across the 6
data/orderflow/registry/seal files, 0 failed. Full 11G suite:
205 passed. Main `tests/`: 2188 passed, 0 failed, 0 collection errors.
`compileall`: clean. `git diff --check`: clean.

## GATE A

PASS ×2: 27 orders / 11 fills / 6 wins / 5 losses / 0 BE /
net +0.117534, identical IDs. (One invocation timed out under machine
contention with two stale Gate-A processes from the killed call; stale
PIDs cleared, two clean reruns green — no code cause.)

## DATASETS

No new market datasets (4 small read-only probe artifacts only:
15m×5, 50 trades, L2, ticker + sidecars/manifest).

## NEW INFRASTRUCTURE (this commit)

`data/probe_public.py`, `data/probes/` (4 artifacts + sidecars +
manifest), `docs/probe_findings_11gh.md`, research-log 11G-H entry.
(Substrate modules/events/tests referenced below are committed 11G-E
work, re-verified live this session — see §0.)

## ECONOMIC RESEARCH: NOT RUN
## HYPOTHESIS CHANGES: NONE
## PARAMETER CHANGES: NONE
## WINNER SELECTION: NONE
## LIVE: DISABLED

## READINESS CHECKLIST (§23)

1. historical coverage (trades/book): NO → verdict driver
2. provenance complete: YES
3. quality acceptable: YES (5/5 post-sort; disorder flagged pre-sort)
4. deterministic ordering: YES (tested)
5. no hidden future info: YES (availability discipline + closed-candle)
6. replay possible: YES (candles; existing Backtester)
7. raw immutable: YES (overwrite refused, tested)
8. normalized hashable: YES (tested)
9. independent sealable: YES (registry + proven pattern)
10. tests pass: YES

## FINAL VERDICT: NOT_READY_FOR_REAL_ORDERFLOW_RESEARCH

Next task per §31: acquire a legitimate historical trades/book dataset
(first choice), not tuning. OHLCV family + labeled-PROXY family remain
the only honest tracks. TRUTH before COMPLEXITY; EVIDENCE before
PERFORMANCE CLAIMS; SAFETY before LIVE TRADING.
