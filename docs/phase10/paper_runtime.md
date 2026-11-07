# Paper Runtime — Production-Grade

> Phase 10 hardening: continuous PAPER operation on real Delta data, PAPER-only safety.

## Lifecycle (EngineLifecycle)

```
STOPPED → STARTING → RUNNING ↔ PAUSED
   ↑         ↓          ↓         ↓
   └────── STOP ←───────┘     STOP
           ↓                    ↓
        FAILED → (restart) → RUNNING
           ↓
     emergency_stop → STOPPED (immediate, idempotent)
```

- **START:** `engine.start()` + poll thread, daemon, `STARTING` → `RUNNING`, fail → `FAILED`
- **RUN:** poll loop `engine.poll()` every `poll_interval_seconds` (10s), `polls` counter, `last_error` on exception
- **PAUSE:** (Phase 10 NEW) `STATE_PAUSED`, `_paused` Event, loop skips `engine.poll` but stays alive, `health()` reports `PAUSED`, idempotent, requires `RUNNING`
- **RESUME:** `PAUSED` → `RUNNING`, clears `_paused`, wakes loop
- **STOP:** graceful, `STOPPING`, `set(_stop_requested)`, `join(5s)`, `engine.stop()`, `STOPPED`, idempotent
- **EMERGENCY_STOP:** immediate, `set(_stop_requested)`, `engine.stop()` without waiting, `join(2s)`, `STOPPED`, idempotent

## Continuous Operation

- **START** → **RUN** → **MONITOR** (health, metrics) → **PAUSE** (stop new signals, finish workers) → **RESUME** → **STOP** (graceful: stop new signals, stop orders, finish workers, persist, release, report) → **EMERGENCY STOP** (immediate)

Graceful shutdown: 1) stop new signal generation (`PAUSE`), 2) stop new paper orders, 3) `join` workers, 4) persist `TradeRegistry`/`Account` if needed (currently in-memory, Parquet journal is next), 5) release `SharedCapital` reservations, 6) report final `health()`.

## Safety

- `PAPER_MODE=True` default, `LIVE_MODE=False`, `LIVE_EXECUTE` requires `1`/`true` + `DELTA_API_KEY/SECRET` + `DeltaExchange._require_auth` fail-closed
- Control API allowlist `start/stop/restart/pause/resume/emergency_stop`, PAPER-only, bearer token, `CONTROL`/`EMERGENCY` roles
- Remote never directly executes orders — only lifecycle verbs
