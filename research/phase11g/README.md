# Phase 11G — Institutional / Order-Flow Strategy Research Framework

Stage-A status: FEATURE ENGINEERING (no hypotheses, no execution).

## What this is

Stage A builds the causal research infrastructure for investigating
institutional market-structure hypotheses: capability matrix, feature
contracts, twelve feature modules, MTF resampler, Wyckoff/mitigation/
session/volume engines, confluence representation, and causality /
mutation / determinism tests.

## Non-negotiable rules

* Phase 11F stays frozen (adapters only, no modifications).
* Production stays untouched (`core/`, `config/`, `data/`, `backtesting/`,
  `execution/`, `risk/`, `main.py`).
* Order-flow honesty: historical delta/CVD/footprint/absorption/imbalance
  are UNAVAILABLE as REAL data. OHLCV estimates are PROXY_FEATURE only.
* D3 is SEALED (never read/hashed/loaded, not even for tests).
* No hypothesis registry, no backtests, no P&L, no winners in Stage A.
* LIVE disabled. No exchange writes.

## Layout

* `data_capability_matrix.json` — REAL/PROXY/UNAVAILABLE per field.
* `feature_contracts.json` — causal rule + result schema.
* `datasets.py` — frozen D1/D2 metadata descriptors (no candle reads).
* `features/` — twelve causal modules (dicts per result schema).
* `validation/snapshot.py` — "what was known at T" availability filter.
* `tests/` — Stage-A suite (run: `python -m pytest research/phase11g/tests -q`).
* `research_log.json` — stage record (no economic results).

## Bar dict contract (inputs)

`{time, open, high, low, close, volume}`, chronological, `time` = bar
open epoch seconds (UTC). Every feature maps `bars[0..i] -> value[i]`.
