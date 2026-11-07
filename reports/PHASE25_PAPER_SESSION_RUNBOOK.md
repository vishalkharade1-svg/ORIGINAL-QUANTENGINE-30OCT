# Phase 25 — Paper Session Runbook

Operator runbook for controlled paper sessions introduced in Phase 25.
Everything here is PAPER-only; the runner refuses live execution and the
REST transport has no order path.

## 1. Prerequisites

- Repository checkout at the delivered revision (`ffefa14` or later).
- Python environment used by the repo (no extra dependencies).
- Network reachability to `https://api.delta.exchange` (public REST only;
  no credentials required or used).
- **Never** set `LIVE_MODE=1` or `EXECUTION_MODE=LIVE` — the runner
  aborts with an explicit refusal (fail-closed).

## 2. Mode A — authoritative live paper session (real data)

Real public Delta Global REST closed candles through the real engine
assembly. Market observations are exchange-sourced; fills are simulated
(`SIMULATED_PAPER_FILL`).

```powershell
# Conservative cost economics (documented assumption; venue fees UNKNOWN)
$env:QE_PAPER_COMMISSION_PER_TRADE = '0.0'
$env:QE_PAPER_COMMISSION_RATE     = '0.0005'   # 5 bps taker assumption
$env:QE_PAPER_SLIPPAGE_BPS        = '5.0'
$env:QE_PAPER_COST_PROFILE_NAME   = 'p25-conservative-assumption'
$env:QE_PAPER_COST_VENUE_REALISTIC = 'false'

python scripts/run_paper_session.py --run-seconds 600 --symbols BTCUSDT --timeframe 1m --poll-interval-seconds 15
```

Useful flags:

- `--run-seconds 600` — bounded run (default 600; `0` runs until Ctrl+C).
- `--symbols BTCUSDT` — comma-separated list.
- `--timeframe 1m` — 1m/5m/15m/1h/4h/1d.
- `--poll-interval-seconds 15` — REST poll cadence (transport floors at
  `max(5.0, poll_interval)`).
- `--lookback-days 1` — warmup window pulled from `/v2/history/candles`.
- `--heartbeat-seconds 30` — engine heartbeat logging cadence.
- `--output-dir reports/PAPER_SESSIONS` — artifact root.
- `--no-capture` — skip the delivered-candle JSONL capture.

### Behavior on failure (fail-closed)

- Unreachable endpoint / repeated REST errors → the session reports the
  error and stops; **no fixture substitution, no fabricated candles**.
- Delivered-stream audit flags (ascending, duplicates, window
  alignment, internal missing buckets) are recorded per symbol in
  `session_report.json → market_data.delivered_quality`.
- Reconciliation verdicts are re-keyed by symbol and stored under
  `reconciliation`.

### Artifacts

`reports/PAPER_SESSIONS/<session_id>/`

- `session_report.json` — full evidence report (config, delivery
  quality, transport/REST stats, engine counters, reconciliation, cost
  economics, provenance incl. code revision and wall time).
- `delivered_candles.jsonl` — one line per delivered closed candle
  (identity + OHLCV + receipt timestamp + history-call index).
- `session_summary.md` — human-readable summary.

### Interpreting results

- `preliminary: true` — short sessions are demonstrations of pipeline
  trustworthiness, NOT strategy evaluations.
- `cost_economics.classification: CONFIGURED_SIMULATION` — costs are a
  documented assumption until the operator provisions venue-realistic
  fees (`PAPER_COST_VENUE_REALISTIC=true` + actual Delta fee numbers).
- `instrument_metadata: SYNTHETIC_SPOT_FALLBACK` — instrument metadata
  is the explicit-cut synthetic spot fallback (fail-closed for
  derivatives), not derivative-realistic metadata.

## 3. Mode B — offline replay (never a live-session claim)

Phase-24 verified replay wrapped in the Phase-25 report schema. Evidence
class is explicit (`SYNTHETIC_FIXTURE` for synthetic streams; captured
bundles keep their recorded class).

```powershell
# Synthetic stream with faults
python scripts/run_paper_session.py --mode replay --synthetic-seed 99 --synthetic-candles 600 --fault duplicate@120 --fault gap@300:2

# Replay a Phase-24 capture bundle
python scripts/run_paper_session.py --mode replay --capture reports/<path-to-capture-bundle>.json
```

Fault tokens: `duplicate@N`, `out_of_order@N:steps`, `malformed@N:mode`
(drop_volume/drop_high/swap_ohl/negative), `gap@N:missing`,
`disconnect@N:delay`.

Known-good behavior (asserted by tests): duplicates suppressed, forming
candles skipped, out-of-order resequenced, malformed frames counted and
excluded, gaps surfaced as `DATA_GAP_UNREPAIRED` (never bridged),
disconnects accounted with zero unrouted-during-outage.

## 4. Safety notes

- The runner calls `refuse_live_execution()` before anything starts;
  arming `LIVE_MODE=1` or `EXECUTION_MODE=LIVE` aborts with
  `REFUSED: live execution flags detected`.
- The REST transport is read-only public market data; no API keys are
  read, required, or logged.
- All artifacts are new files under `reports/PAPER_SESSIONS/`; frozen
  datasets under `data/history/` are never modified.

## 5. Troubleshooting

| Symptom | Meaning | Action |
| --- | --- | --- |
| `endpoint unreachable` in report/summary | Network/DNS failure | Re-run when `api.delta.exchange` is reachable; nothing is substituted |
| `DATA_GAP_UNREPAIRED` in gap status | Missing candles detected in delivery | Expected under `gap@` faults or real provider gaps; investigate source, do not backfill silently |
| `internal_missing_buckets > 0` | Warmup window had missing minutes | Increase `--lookback-days` or accept and note the coverage in the report |
| Zero orders placed | No qualifying setup in the window | Expected for short sessions; extend the run or verify against Mode-B with a setup-rich stream |
| Exit code 1 from pytest with `SNAPSHOT_GUARD_TREE_NOT_PRISTINE` | New files added since the last manifest regen | Regenerate `BUILD_MANIFEST.sha256` at phase close (manifest is regen'd LAST) |
