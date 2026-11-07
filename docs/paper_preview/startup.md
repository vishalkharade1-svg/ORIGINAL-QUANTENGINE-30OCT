# Paper Preview — Startup & Operator Guide

PAPER ONLY. LIVE EXECUTION IS DISABLED. PRODUCTION_READY = FALSE.

## Prerequisites

- Python environment with the repository dependencies installed.
- Outbound HTTPS to `https://api.delta.exchange` (public market data
  only; no API key needed, none used).
- A local browser. Nothing else.

## Start

From VS Code (or any terminal) at the repository root:

```bash
python scripts/paper_preview.py
```

Optional environment (all safe; no live flags exist):

```bash
PREVIEW_SYMBOLS=BTCUSDT PREVIEW_TIMEFRAME=1m PREVIEW_PORT=8787 \
  PREVIEW_RUN_SECONDS=420 python scripts/paper_preview.py
```

| Variable | Default | Meaning |
|---|---|---|
| `PREVIEW_SYMBOLS` | `BTCUSDT` | comma list, explicit universe |
| `PREVIEW_TIMEFRAME` | `1m` | 1m/5m/15m/1h/4h/1d |
| `PREVIEW_PORT` | `8787` | localhost API port |
| `PREVIEW_TOKEN` | `paper-preview-local-dev` | bearer token (localhost-only dev default; override via `CONTROL_API_TOKEN`) |
| `PREVIEW_RUN_SECONDS` | unset (run until Ctrl+C) | bounded run then clean shutdown |

The launcher REFUSES to start when `LIVE_MODE`/`EXECUTION_MODE=LIVE`
is set. It never defaults to LIVE.

## Open the dashboard

```text
http://127.0.0.1:8787/dashboard
```

Enter the API token shown in the terminal when prompted (kept in
page memory only). Panels poll every 3 seconds.

## Shutdown

Ctrl+C in the terminal, or POST `/control {"command": "stop"}`
with the bearer token (PAPER-only lifecycle verb).

## What runs

REAL Delta public REST closed 1m candles (BTCUSDT default) →
`RestPollingCandleTransport` → canonical `build_paper_engine` stack
(RealTimeEngine → PaperRuntime → BrokerEngine dry-run, zero exchange
writes) → ControlApiServer on 127.0.0.1 + read-only preview routes
(`/preview`, `/candles`, `/evidence`, `/dashboard`).

## Troubleshooting

- `REFUSED: live execution flags detected` — unset `LIVE_MODE` /
  `EXECUTION_MODE`; the preview never starts armed.
- Dashboard shows API ERROR — enter the terminal's token; the API
  refuses tokenless requests fail-closed.
- Market shows STALE/DISCONNECTED — public REST unreachable or no
  closed bar yet this minute; the transport retries with a bounded
  budget, then the worker reconnect policy re-subscribes.
- `paper orders = 0` — normal: the strategy only trades 1:6+ setups.
  Never manufacture activity.
- Port in use — set `PREVIEW_PORT` to a free localhost port.
