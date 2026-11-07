# Runbook — Production-Grade PAPER

> How to run QuantEngine PAPER continuously on real Delta data.

## Install

```bash
pip install -r requirements.txt
cp .env.example .env  # set DELTA_API_KEY/SECRET only for LIVE, not needed for PAPER
```

## Configure (PAPER, default)

```bash
PAPER_MODE=True
LIVE_MODE=False
SYMBOLS=BTCUSDT,ETHUSDT
TIMEFRAME=1m
UNIVERSE=explicit  # or "provider" for dynamic eligibility
# Control API (optional)
CONTROL_API_ENABLED=False
CONTROL_API_TOKEN=...
# Remote Gateway (optional)
REMOTE_GATEWAY_ENABLED=False
```

## Start

```bash
python -m main
# or
python main.py
```

Expected: `QuantEngine Started`, `Mode: PAPER TRADING`, `Runtime: Phase 6E RealTimeEngine`, `Paper-only: dry_run=True`, `Control API: disabled`, `Waiting for live candles...`

## Control (when enabled)

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/health
curl -H "Authorization: Bearer $TOKEN" -X POST http://127.0.0.1:8787/control -d '{"command":"pause"}'
curl -H "Authorization: Bearer $TOKEN" -X POST http://127.0.0.1:8787/control -d '{"command":"resume"}'
curl -H "Authorization: Bearer $TOKEN" -X POST http://127.0.0.1:8787/control -d '{"command":"stop"}'
curl -H "Authorization: Bearer $TOKEN" -X POST http://127.0.0.1:8787/control -d '{"command":"emergency_stop"}'
```

## Monitor

- Desktop: `python -m core.client`
- Remote: `https://127.0.0.1:9443` (PWA, VIEW/CONTROL/EMERGENCY roles)
- Metrics: `GET /health`, `GET /runtimes`, `GET /performance`

## Shutdown

1. `stop` (graceful) or `Ctrl-C` → finishes current poll, closes workers, persists, reports final state
2. `emergency_stop` → immediate

## Troubleshooting

- No candles: check `wss://public-socket.delta.exchange` connectivity, `MarketState.connected`, `CandleBuilder` errors
- No trades: check `risk_config_contract.md` (0 trades is valid if funnel selective), `MAX_PORTFOLIO_RISK` fraction, `Account` drawdown
- High latency: check `p99` via soak harness, `event_loop` health

## PAPER-only Safety

- `LIVE_EXECUTE` must be `0`/`false` (default), `DELTA_API_KEY/SECRET` not required for PAPER
- `BrokerEngine` `dry_run=True` by default, `DeltaExchange._require_auth` fail-closed
- Remote never directly executes orders — only lifecycle verbs
