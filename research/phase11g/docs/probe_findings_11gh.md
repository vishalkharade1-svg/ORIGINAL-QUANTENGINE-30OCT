# 11G-H Probe Findings (read-only public endpoints, no auth)

Probed 2026 (pre-report) via `research/phase11g/data/probe_public.py`;
raw responses + provenance sidecars in `research/phase11g/data/probes/`.

## candles_15m — REAL multi-TF confirmed

`GET /v2/history/candles?symbol=BTCUSDT&resolution=15m&start=&end=` →
5 proper 15m-grid candles (900s spacing). Response is newest-first:
fed raw, the quality engine correctly rejected 4 as out-of-order;
sorted chronologically → 5/5 accepted, 0 gaps. Lesson recorded, not
hidden: ordering is a transformation step (`order_stream`), and the
validator catches its absence. Direct REAL HTF availability proven —
resampling remains valid but optional.

## recent_trades — REAL source, RECENT-ONLY

`GET /v2/trades/BTCUSDT` → 50 most recent trades; fields include
`buyer_role`/`seller_role` (maker/taker = aggressor side), microsecond
timestamps. `start`/`end` params IGNORED (same 50 returned) —
count-capped recent feed, not a historical window. Verdict:
REAL source, UNAVAILABLE historically.

## l2_snapshot — live snapshot only

`GET /v2/l2orderbook/BTCUSDT` → `{symbol, buy[], sell[]}` with
size/depth/price. No history params. Verdict: live-only, UNAVAILABLE
historically. (Naive `/v2/l2orderbook?symbol=` and `/v2/trades?symbol=`
return 404 — path-shape documented here so nobody re-probes blindly.)

## ticker — live OI/funding snapshot

`GET /v2/tickers/BTCUSDT` → `oi_contracts`, `funding_rate`,
`mark_price`, `quotes` present. Snapshot only — no history.
Mark/OI/funding HISTORY REST paths could not be verified from
authoritative docs (MCP lists tools, not REST paths); recorded
UNVERIFIED — not claimed, not used.

## Rate-limit posture

Public reads weight 3 per call against a 20000/5min quota; 4 probes
are negligible. Polite delays retained in fetchers.
