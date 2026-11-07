# 11G-E Canonical Event Schema (`events/canonical.py`, v11ge-v1)

Frozen dataclasses (immutable): `BaseEvent` + `CandleEvent`,
`TradeEvent`, `QuoteEvent`, `BookSnapshotEvent`, `BookDeltaEvent`,
`FundingEvent`, `OpenInterestEvent`, `LiquidationEvent`.

## Common fields

`event_type, symbol, event_timestamp, exchange_timestamp,
receive_timestamp, sequence, source, provenance, schema_version`.
Plus per-type fields (price/quantity/side/bid/ask/sizes/levels/rate/
IDs). Unavailable source fields stay `None` — never synthesized.

## Semantics

* `event_timestamp` = when it happened (exchange time where known).
* `receive_timestamp` = when observed (live only; None historically).
* Candle `event_timestamp` = bar-OPEN time; `closed` defaults True
  (partial-candle handling belongs to the resampler, not the schema).
* `to_dict()` round-trips losslessly (tested incl. None preservation).
* Ordering key: (event_timestamp, sequence or 0, type rank) — total and
  deterministic (`order_stream`).
* `provenance` defaults REAL but MUST be set truthfully per event
  origin (SYNTHETIC fixtures set their own label downstream).
