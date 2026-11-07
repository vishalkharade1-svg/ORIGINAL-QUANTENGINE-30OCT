# Phase 9Q Baseline — 2026-05-11

> Created before any 9Q code changes. All commands executed, results verified, no guessing.

## Environment

| Field | Value |
|-------|-------|
| Branch | `main` (ahead of origin/main by 38 commits, HEAD `f92e8e7 feat(phase9k): secure remote mobile control foundation`) |
| Python | `3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]` |
| Executable | `C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe` |
| pip | `25.0.1` |
| Dependencies | `requirements.txt` (9 pins): aiohttp==3.10.5, httpx==0.27.2, websockets==12.0, orjson==3.10.7, python-dotenv==1.0.1, loguru==0.7.2, pandas==2.2.2, numpy==2.1.1, pyarrow==18.0.0 |
| Platform | `win32`, PowerShell, `F:\vishal 3\1\files\QuantEngine\QuantEngine` |
| Untracked files pre-baseline | `claude suggetions.md` only |
| Git status | clean except untracked above |

## Project Structure (verified)

```
QuantEngine/
  core/                 — canonical pipeline, engines, indicators, market_structure, liquidity, displacement, fvg, order_blocks, breaker, mitigation, risk, execution, analytics, remote, monitoring, runtime, etc.
  _archive/             — legacy quarantined tree (engine/, smartmoney/, strategy/, indicators/, execution/, analytics/, risk/, 22 examples/) — not imported by live code per import census (STATUS.md §84)
  backtesting/          — canonical Backtester + PortfolioBacktester
  data/                 — candle_builder, historical_loader, delta/, websocket_client, realtime/
  config/               — settings.py, risk_settings.py, trading_profile.py
  tests/                — 1568 tests (excluding _archive/examples)
  examples/             — 12 canonical examples (post-archive)
  docs/                 — architecture/, RUNBOOK.md, project_manifest.md, import_manifest.md, audit/
  main.py               — PAPER/PAPER-with-monitoring (default) / LIVE (BrokerEngine) / ANALYZE-ONLY switch
```

No parallel trading logic. One pipeline `core/pipeline/institutional_pipeline.py` is authoritative.

## Configuration (inspected)

- `config/settings.py` — `SYMBOLS`, `TIMEFRAME`, `PAPER_MODE=True` default, `LIVE_MODE=False`, `UNIVERSE=explicit|all|provider`, `CONTROL_API_*`, `REMOTE_GATEWAY_*`, `AUDIT_*`
- `config/risk_settings.py` — `STARTING_BALANCE=2000`, `RISK_PER_TRADE=0.01`, `MAX_ALLOCATION_PER_TRADE=500`, `QUANTITY_PRECISION=8`, `MIN_QUANTITY=1e-6`, `MAX_WAIT_BARS=30`, `ENTRY_DELAY_BARS=1`, `MAX_PENDING_ORDERS*`, `ENTRY_MODE=BREAKOUT_CONTINUATION`, etc.

## Existing Status Documents (inspected)

- `STATUS.md` — Sessions 1-6 reconstructed + Session 7 verbatim (items 74-103), up to incremental scan speedup.
- `project_status.md` — Sprint 40, Delta perps, replay→live roadmap.
- `docs/architecture/OBJECT_OWNERSHIP.md`, `docs/PIPELINE_CONTEXT_OWNERSHIP.md`, etc. — current.
- `claude suggetions.md` — prior audit synthesis (48 issues across CRITICAL/HIGH/MEDIUM/LOW).

## Compile Checks

| Command | Result | Duration |
|---------|--------|----------|
| `python -m compileall -q core` | No output (success), exit 0 | <2s |

`core`, `core/remote`, `tests/test_remote_gateway_9pk.py` all compile clean (verified via `compileall`).

## Test Collection

| Command | Result | Duration |
|---------|--------|----------|
| `python -m pytest --collect-only -q` | **1568 tests collected, 24 errors** in 58.90s | 58.90s |
| Errors | All in `_archive/examples/test_*.py` (ModuleNotFoundError: `data.bar_series`, `strategy`, `indicators`, `execution`, `analytics`, `risk.risk_manager`) + `examples/test_market_structure.py` (`MarketStructureEngine has no attribute 'registry'`) + `tests_list.txt` (UnicodeDecodeError `0xff`) | — |
| `python -m pytest --collect-only -q --ignore=_archive --ignore=examples` | Clean collection (no errors) | — |

Collection without `_archive`/`examples` is clean. Errors are legacy archive import paths, not live code.

## Targeted Test Runs

| Command | Result | Duration |
|---------|--------|----------|
| `python -m pytest tests/test_remote_gateway_9pk.py -q` | **28 passed** | 9.28s |
| `python -m pytest tests/test_api_server_9pf.py tests/test_lifecycle_9pf.py tests/test_monitoring_service_9pf.py -q` | **55 passed** | 4.11s |

Control plane (9P-f/9P-k) regression green — must remain passing through 9Q–9S.

## Full Suite

| Command | Result | Duration | Failures | Timeout |
|---------|--------|----------|----------|---------|
| `python -m pytest tests --ignore=_archive --ignore=examples -q` | **1568 passed** | **94.63s (0:01:34)** | 0 | No |
| `python -m pytest --collect-only -q` (with archive) | 1568 collected, 24 errors (see above) | 58.90s | — | No |

**No failures. No timeout. Full suite PASS when archive/examples ignored (live code).** When archive included, collection errors are pre-existing legacy import breakage, not regressions.

## Baseline Commit

- Baseline branch: `main`
- HEAD: `f92e8e7 feat(phase9k): secure remote mobile control foundation` (9 files, 2441 insertions)
- No code modified in this baseline step.

## Known Baseline Limitations (honest)

- `python -m pytest` without ignores hits 24 collection errors from `_archive/examples` + one broken example; full `pytest` invocation must use `--ignore=_archive --ignore=examples` or fix those files (not in scope for 9Q baseline).
- `data/websocket_client.py` timestamp unit and `CandleBuilder` concurrency are suspected defects (to be verified in 9Q-6/9Q-7), not baseline failures.
- `core/indicators/atr.py` uses SMA averaging (to be fixed in 9Q-2); baseline tests still pass because they assert structure, not Wilder correctness.
- No live trading, no NSE, no new AI — frozen per 9Q rules.

## Next

Baseline complete. Proceed to defect matrix and Phase 9Q-2 (ATR correctness). No implementation begun.
