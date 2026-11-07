# 11G-E Data Provenance Contract (immutable)

Implemented in `research/phase11g/provenance/model.py`.

## Record fields (all required)

`dataset_id, source, provider, exchange, instrument, market_type,
symbol, timeframe, start_timestamp, end_timestamp, row_count,
timezone, timestamp_convention, ordering_convention, duplicate_policy,
gap_policy, schema_version, retrieval_timestamp, content_hash,
raw_file_hash, transformation_hash, transformation_description,
measurement_class, contamination_status, intended_phase,
access_restrictions, freshness_verdict`

## Rules

* `freshness_verdict` ∈ FRESH / CONTAMINATED / SEALED / UNKNOWN.
  Nothing is FRESH by filename — only by explicit verdict from the
  governing phase.
* `measurement_class` ∈ REAL / PROXY / UNAVAILABLE / MIXED.
* `content_hash` = SHA-256 over canonical (sort_keys) event dicts.
* `transformation_hash` binds (description, code version).
* RAW files are immutable (`storage/store.py` refuses overwrite);
  normalization outputs carry content hashes + sidecar metadata.
* Timezone: UTC throughout. Timestamp convention: bar-open epoch for
  candles; event epoch for trades/quotes/book. Ordering: (timestamp,
  sequence, type-rank) — deterministic (`order_stream`).
* Duplicates: rejected observably (never silently dropped).
  Gaps: enumerated (`detect_gaps`), never interpolated.
