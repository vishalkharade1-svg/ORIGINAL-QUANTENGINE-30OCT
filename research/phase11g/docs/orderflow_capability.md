# 11G-E Order-Flow Capability Statement

Implemented in `research/phase11g/orderflow/truth.py` (+ `book.py`).

## Truth table (enforced by `classify()`)

| Feature | With trades | With quotes | With book | With OHLCV only | With nothing |
|---------|------------|-------------|-----------|-----------------|--------------|
| delta / CVD / footprint / absorption / volume-at-price | REAL | — | — | PROXY | UNAVAILABLE |
| spread | — | REAL | — | UNAVAILABLE | UNAVAILABLE |
| imbalance / depth imbalance / stacked imbalance | — | REAL* | REAL | UNAVAILABLE | UNAVAILABLE |

(*plain imbalance from quotes; stacked/diagonal from book levels.)

## Hard rules (tested)

* `require_trades()` raises `UnavailableData` on empty input,
  non-trade events, or missing side/price/quantity.
* Footprint aggregation needs TradeEvents; OHLCV input is rejected,
  never estimated.
* Absorption uses the frozen definitional form (high trailing-relative
  volume + limited progress); thresholds definitional, untuned.
* Diagonal imbalance uses the classical ≥3× adjacent-level definition.
* Book reconstruction validates sequence/ordering/duplicates/gaps,
  rejects crossed/stale books WITHOUT applying them, and is
  deterministic (same raw → same state, tested twice).
* Synthetic fixtures (`data/synthetic.py`, seeded, labeled SYNTHETIC)
  are the only non-REAL inputs permitted — unit tests only, never
  economic results (enforced by label test).

## Current historical verdict

REAL order flow: UNAVAILABLE. PROXY order flow: OHLCV estimates only,
explicitly labeled. No silent fallback exists anywhere in the path.
