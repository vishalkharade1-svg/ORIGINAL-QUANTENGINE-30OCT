# 11G-E Dataset Registry Spec

Implemented in `research/phase11g/registry/registry.py`.

## Questions answered

* Which datasets exist? — `Registry._sets` (explicit `register()` only).
* Which are fresh? — `freshness` field; `is_fresh_for(dataset, phase)`
  uses canonical `PHASE_ORDER` (string comparison forbidden — implemented
  and tested).
* Which phases/hypotheses touched them? — `record_use()` log;
  unregistered datasets raise `KeyError` on use.
* Which transformations/hashes? — provenance records + content/
  transformation hashes.
* Was D3 accessed? — `d3_block()` refuses before I/O; counters stay zero;
  D3 registration itself raises `ValueError`.
* Was a dataset available before hypothesis freeze? — touch log vs
  freeze phase via `PHASE_ORDER`.

## Contamination law

UNKNOWN provenance can be registered for tracking but never as usable;
`register(..., "UNKNOWN")` raises. UNKNOWN is never FRESH.
`bootstrap_11g_registry()` preloads the frozen catalog: D1/D2
CONTAMINATED, oos_fresh FRESH (11G-D verdict, preserved).

## Storage layout (implemented, `storage/store.py`)

RAW: immutable files + `.meta.json` sidecars (overwrite refused).
NORMALIZED: Parquet (pyarrow) with JSON fallback + content-hash sidecar.
RESULTS: versioned JSON. All desktop-scale, no new services.
