"""QuantEngine Phase 25 -- controlled, observable paper-session harness.

Two explicitly separated operating modes over the REAL engine assembly
(the same collaborators `build_paper_engine` produces: ExplicitSymbol
UniverseManager -> MultiSymbolSubscriptionManager -> RealTimeEngine ->
PaperRuntime -> BrokerEngine dry-run -> TradeSimulator -> TradeRegistry):

Mode A (``PaperSessionRunner``, ``SESSION_MODE_LIVE``)
    Consumes AUTHORITATIVE market data from the public Delta Global REST
    closed-candle endpoint (``RestPollingCandleTransport`` over
    ``DeltaHistory``; no credentials, no trading authority) and makes
    simulated execution decisions only. Every market observation is
    labelled exchange-sourced; every fill is labelled simulated.

Mode B (``run_replay_session``, ``SESSION_MODE_REPLAY``)
    Reuses the Phase-24 verified replay harness
    (``data.realtime.verified_replay``) over captured socket frames or
    an explicitly synthetic bundle. The report carries the harness's own
    evidence class (CAPTURED_REPLAY / SYNTHETIC_FIXTURE) and is never
    presented as a live market session.

The harness needs NO live execution privileges: the transport imports no
exchange write path and the broker runs ``dry_run=True``. Refusal is
fail-closed: any live arming (LIVE_MODE / EXECUTION_MODE=LIVE) aborts the
session before assembly.

Instrumentation (purely observational, never mutating production objects):

* ``_CountingHistory`` wraps the REST history client: per-call row
  counts, error counts, and a bounded sample of raw venue rows.
* ``InstrumentedRestTransport`` wraps each subscription callback to
  capture every delivered candle (symbol, bucket open time, OHLCV,
  local receipt wall-clock) and the poll-call index (warm-up vs live
  delivery), BEFORE the subscription worker's integrity router.
* ``_LogCountObserver`` (imported from the Phase-24 harness) counts the
  production components' own verdict log records (setup accept/reject,
  risk skips, route blocks, portfolio gate, route errors).
* Engine counters (routed / unrouted / route_errors), per-worker stream
  counters (received / delivered / duplicates / out_of_order /
  forming_skipped), per-runtime ledger / account / executed intents.
* Ledger reconciliation reuses the Phase-24 canonical checker
  (``reconcile_paper_ledger``) against the session engine.

Artifacts: a machine-readable ``session_report.json`` plus the delivered
candle capture (``delivered_candles.jsonl``) written under
``reports/PAPER_SESSIONS/<session_id>/``. A short session is always
labelled preliminary: it validates pipeline behaviour, never strategy
profitability.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

LIVE_MODE_ENV = "LIVE_MODE"
EXECUTION_MODE_ENV = "EXECUTION_MODE"

SESSION_MODE_LIVE = "authoritative_paper_session"
SESSION_MODE_REPLAY = "offline_replay"

MARKET_DATA_SOURCE_LIVE = "delta_global_public_rest_history_candles"
FILL_CLASS = "SIMULATED_PAPER_FILL"

_SUPPORTED_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")
_TIMEFRAME_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400,
}

_RAW_SAMPLE_ROWS = 5
_HEARTBEAT_PREFIX = "P25_SESSION_HEARTBEAT"


def _utc_iso(epoch: float | None = None) -> str:
    if epoch is None:
        epoch = time.time()
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ",
    )


def refuse_live_execution() -> None:
    """Fail closed when any live arming is present (paper session only)."""
    live_mode = os.getenv(LIVE_MODE_ENV, "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    execution_mode = os.getenv(EXECUTION_MODE_ENV, "").strip().upper()
    if live_mode or execution_mode == "LIVE":
        raise SystemExit(
            "REFUSED: live execution flags detected (%s=%r %s=%r); the "
            "Phase-25 paper session never starts armed." % (
                LIVE_MODE_ENV, os.getenv(LIVE_MODE_ENV, ""),
                EXECUTION_MODE_ENV, os.getenv(EXECUTION_MODE_ENV, ""),
            ),
        )
    if execution_mode not in ("", "PAPER"):
        raise SystemExit(
            "REFUSED: unknown %s=%r." % (
                EXECUTION_MODE_ENV, os.getenv(EXECUTION_MODE_ENV, ""),
            ),
        )


class _CountingHistory:
    """Observability proxy around a REST history client.

    Records per-call row counts, failures, and a bounded sample of raw
    venue rows (public OHLCV only; the payload carries no credentials).
    Never mutates the rows it returns.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self._lock = threading.Lock()
        self.calls = 0
        self.errors = 0
        self.rows_seen = 0
        self.last_error = ""
        self.raw_samples: list[dict] = []

    def candles(self, symbol, resolution="1m", start=None, end=None, days=1):
        self.calls += 1
        call_index = self.calls
        try:
            try:
                rows = self._inner.candles(
                    symbol, resolution, start=start, end=end, days=days,
                )
            except TypeError:
                # Tolerant call shape for minimal fakes whose candles()
                # accepts (symbol, resolution, days) only.
                rows = self._inner.candles(symbol, resolution, days=days)
        except Exception as exc:  # noqa: BLE001 (counted, re-raised)
            with self._lock:
                self.errors += 1
                self.last_error = "%s: %s" % (type(exc).__name__, exc)[:200]
            raise
        rows = list(rows or [])
        with self._lock:
            self.rows_seen += len(rows)
            if len(self.raw_samples) < _RAW_SAMPLE_ROWS:
                for row in rows[: _RAW_SAMPLE_ROWS - len(self.raw_samples)]:
                    try:
                        self.raw_samples.append({
                            "time": int(getattr(row, "timestamp", 0) or 0),
                            "open": float(getattr(row, "open", 0.0) or 0.0),
                            "high": float(getattr(row, "high", 0.0) or 0.0),
                            "low": float(getattr(row, "low", 0.0) or 0.0),
                            "close": float(getattr(row, "close", 0.0) or 0.0),
                            "volume": float(
                                getattr(row, "volume", 0.0) or 0.0),
                        })
                    except (TypeError, ValueError):
                        continue
        self._last_call = {"index": call_index, "rows": len(rows)}
        return rows

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "calls": self.calls,
                "errors": self.errors,
                "rows_seen": self.rows_seen,
                "last_error": self.last_error,
                "raw_sample_rows": list(self.raw_samples),
                "sample_truncated": len(self.raw_samples)
                >= _RAW_SAMPLE_ROWS,
            }


class InstrumentedRestTransport:
    """Delivery-capturing wrapper around RestPollingCandleTransport.

    Implements the exact 6D transport contract by delegation; the
    wrapped ``on_candle`` sees every candle the transport emits (closed
    bars only) BEFORE the subscription worker's integrity router, which
    is where the raw-vs-normalized boundary sits. Delivery records carry
    the local receipt time and the history-call index that produced the
    bar (index 1 == the subscribe probe; the first DELIVERY batch comes
    from the first poll call after the probe -- the warm-up batch).
    """

    def __init__(self, *, timeframe="1m", history=None, clock=None,
                 poll_interval_seconds=15.0, lookback_days=1,
                 max_failures=5, capture_delivered=True) -> None:
        from data.delta.rest_candle_transport import (
            RestPollingCandleTransport,
        )

        self._inner = RestPollingCandleTransport(
            timeframe=timeframe,
            history=history,
            clock=clock,
            poll_interval_seconds=poll_interval_seconds,
            lookback_days=lookback_days,
            max_failures=max_failures,
        )
        self.capture_delivered = bool(capture_delivered)
        self._lock = threading.Lock()
        self._delivered: dict[str, list[dict]] = defaultdict(list)

    # -- transport contract (delegated, callback wrapped) ------------

    def subscribe(self, symbol, on_candle, on_down):
        symbol = str(symbol).strip()

        def wrapped(candle):
            receipt = time.time()
            try:
                stamp = int(getattr(candle, "timestamp", 0) or 0)
            except (TypeError, ValueError):
                stamp = 0
            if self.capture_delivered and stamp > 0:
                record = {
                    "symbol": symbol,
                    "bucket_open_ts": stamp,
                    "open": float(getattr(candle, "open", 0.0) or 0.0),
                    "high": float(getattr(candle, "high", 0.0) or 0.0),
                    "low": float(getattr(candle, "low", 0.0) or 0.0),
                    "close": float(getattr(candle, "close", 0.0) or 0.0),
                    "volume": float(getattr(candle, "volume", 0.0) or 0.0),
                    "receipt_ts": round(receipt, 3),
                    "receipt_utc": _utc_iso(receipt),
                    "history_call_index": getattr(
                        self._inner.history, "_last_call", {},
                    ).get("index", 0),
                }
                with self._lock:
                    self._delivered[symbol].append(record)
            return on_candle(candle)

        self._inner.subscribe(symbol, wrapped, on_down)

    def unsubscribe(self, symbol):
        self._inner.unsubscribe(symbol)

    def close(self):
        self._inner.close()

    # -- observability ------------------------------------------------

    def delivered_candles(self, symbol=None):
        with self._lock:
            if symbol is None:
                return {
                    name: list(rows) for name, rows in self._delivered.items()
                }
            return list(self._delivered.get(str(symbol), ()))

    def delivered_count(self):
        with self._lock:
            return sum(len(rows) for rows in self._delivered.values())

    def stats(self, symbol=None):
        return self._inner.stats(symbol)

    def recent_closed(self, symbol, limit=60):
        return self._inner.recent_closed(symbol, limit)


def _delivery_quality(delivered: dict[str, list[dict]], window: int) -> dict:
    """Independent post-session data-quality audit over delivered bars.

    Verifies per symbol: ascending bucket order, zero duplicate buckets,
    bucket alignment (stamp % window == 0 -- REST history buckets are
    window-aligned by construction), and internal gap structure between
    the first and last delivered bucket (expected = span/window + 1).
    Purely observational: it never bridges or repairs anything.
    """
    out: dict[str, dict] = {}
    for symbol, rows in sorted(delivered.items()):
        stamps = [int(r["bucket_open_ts"]) for r in rows]
        ascending = all(b > a for a, b in zip(stamps, stamps[1:]))
        duplicates = len(stamps) - len(set(stamps))
        aligned = all(s % window == 0 for s in stamps) if stamps else True
        if stamps:
            span = stamps[-1] - stamps[0]
            expected = span // window + 1
            actual = len(set(stamps))
            missing = expected - actual
        else:
            expected = actual = missing = 0
        out[symbol] = {
            "delivered": len(rows),
            "unique_buckets": actual,
            "ascending": ascending,
            "duplicate_buckets": duplicates,
            "window_aligned": aligned,
            "first_bucket_ts": stamps[0] if stamps else None,
            "last_bucket_ts": stamps[-1] if stamps else None,
            "expected_buckets_in_span": expected,
            "internal_missing_buckets": max(0, missing),
        }
    return out


def _cost_profile_snapshot() -> dict:
    """Resolved paper cost economics (explicit, never silent zero)."""
    from core.risk.costs import (
        describe,
        paper_cost_profile,
        paper_profile_name,
        paper_venue_realistic,
    )

    spec = paper_cost_profile()
    return {
        "profile_name": paper_profile_name(),
        "classification": describe(spec),
        "venue_realistic": paper_venue_realistic(),
        "per_trade": spec.per_trade,
        "rate": spec.rate,
        "slippage_bps": spec.slippage_bps,
        "known": spec.known,
        "venue_source": spec.venue_source,
    }


def _runtime_rows(engine) -> list[dict]:
    rows = []
    for key, runtime in sorted(engine.runtimes.items()):
        broker = getattr(runtime, "engine", None)
        ledger = getattr(broker, "registry", None)
        account = getattr(broker, "account", None)
        intents = []
        try:
            for order in (runtime.executed_intents or ()):
                intents.append({
                    "setup_id": str(getattr(order, "setup_id", "") or ""),
                    "direction": str(
                        getattr(order, "direction", "") or ""),
                    "entry": float(getattr(order, "entry", 0.0) or 0.0),
                    "stop_loss": float(
                        getattr(order, "stop_loss", 0.0) or 0.0),
                    "take_profit": float(
                        getattr(order, "take_profit", 0.0) or 0.0),
                    "quantity": float(
                        getattr(order, "quantity", 0.0) or 0.0),
                    "commission": float(
                        getattr(order, "commission", 0.0) or 0.0),
                    "slippage": float(
                        getattr(order, "slippage", 0.0) or 0.0),
                })
        except Exception:  # noqa: BLE001 (observability only)
            intents = []
        trades = []
        if ledger is not None:
            for trade in ledger.all():
                trades.append({
                    "trade_id": str(getattr(trade, "trade_id", "") or ""),
                    "setup_id": str(getattr(trade, "setup_id", "") or ""),
                    "direction": str(
                        getattr(trade, "direction", "") or ""),
                    "status": str(getattr(trade, "status", "") or ""),
                    "result": str(getattr(trade, "result", "") or ""),
                    "entry": float(getattr(trade, "entry", 0.0) or 0.0),
                    "exit": float(getattr(trade, "exit", 0.0) or 0.0),
                    "pnl": float(getattr(trade, "pnl", 0.0) or 0.0),
                    "commission": float(
                        getattr(trade, "commission", 0.0) or 0.0),
                    "slippage": float(
                        getattr(trade, "slippage", 0.0) or 0.0),
                    "funding": float(
                        getattr(trade, "funding", 0.0) or 0.0),
                    "reason": str(getattr(trade, "reason", "") or ""),
                })
        rows.append({
            "key": key,
            "symbol": runtime.symbol,
            "exchange": getattr(runtime.instrument, "exchange", "") or "",
            "instrument_id": (
                getattr(runtime.instrument, "instrument_id", "") or ""),
            "retired": bool(runtime.retired),
            "processed_bars": int(runtime.processed_bars),
            "open_position": runtime.current_trade is not None,
            "balance": float(account.balance) if account else None,
            "equity": float(account.equity) if account else None,
            "orders_placed": len(intents),
            "intents": intents,
            "trades_total": len(trades),
            "trades": trades,
        })
    return rows


class PaperSessionRunner:
    """Mode A: an authoritative-data paper session (simulated fills).

    Assembly (real path, no shortcuts): ExplicitSymbolUniverseManager ->
    MultiSymbolSubscriptionManager (instrumented REST transport factory)
    -> RealTimeEngine -> per-instrument PaperRuntime (BrokerEngine
    dry_run). The poll loop is the production EngineLifecycle.
    """

    def __init__(
        self,
        symbols,
        *,
        timeframe="1m",
        run_seconds=None,
        heartbeat_seconds=30.0,
        poll_interval_seconds=15.0,
        lookback_days=1,
        refresh_interval_seconds=60.0,
        starting_balance=None,
        history=None,
        clock=None,
        output_dir="reports/PAPER_SESSIONS",
        session_id=None,
        capture_delivered=True,
        market_data_source=MARKET_DATA_SOURCE_LIVE,
    ) -> None:
        refuse_live_execution()
        self.symbols = [str(s).strip() for s in symbols if str(s).strip()]
        if not self.symbols:
            raise ValueError("paper session requires at least one symbol")
        if timeframe not in _SUPPORTED_TIMEFRAMES:
            raise ValueError(
                "unsupported timeframe %r (supported: %s)"
                % (timeframe, list(_SUPPORTED_TIMEFRAMES)),
            )
        self.timeframe = timeframe
        self.window = _TIMEFRAME_SECONDS[timeframe]
        self.run_seconds = (
            float(run_seconds) if run_seconds is not None else None)
        self.heartbeat_seconds = max(1.0, float(heartbeat_seconds))
        self.poll_interval_seconds = max(1.0, float(poll_interval_seconds))
        self.lookback_days = max(1, int(lookback_days))
        self.refresh_interval_seconds = max(1.0, float(
            refresh_interval_seconds))
        self.output_dir = Path(output_dir)
        self.session_id = session_id or self._default_session_id()
        self.market_data_source = market_data_source

        if history is not None:
            self.counting_history = _CountingHistory(history)
        else:
            from core.exchanges.delta.delta_history import DeltaHistory

            self.counting_history = _CountingHistory(DeltaHistory())
        self.transport = InstrumentedRestTransport(
            timeframe=timeframe,
            history=self.counting_history,
            clock=clock,
            poll_interval_seconds=poll_interval_seconds,
            lookback_days=self.lookback_days,
            capture_delivered=capture_delivered,
        )
        self._clock = clock

        from data.realtime.verified_replay import _LogCountObserver

        self._log_observer = _LogCountObserver()
        self._heartbeats: list[dict] = []
        self._engine = None
        self._lifecycle = None
        self._manager = None
        self._started_at = None
        self._stopped_at = None
        self._stop_reason = ""
        self._session_lock = threading.Lock()

    # ------------------------------------------------------------------

    def _default_session_id(self) -> str:
        return "P25-%s-%s-%s" % (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "-".join(self.symbols)[:60] if hasattr(self, "symbols") else "s",
            self.timeframe,
        )

    @property
    def engine(self):
        return self._engine

    def start(self) -> dict:
        """Build the universe, pipelines, and subscriptions."""
        from core.universe.refresh_scheduler import RefreshScheduler
        from core.runtime.realtime_engine import RealTimeEngine
        from core.runtime.lifecycle import EngineLifecycle
        from core.runtime.paper_main import ExplicitSymbolUniverseManager
        from data.realtime.subscription_manager import (
            MultiSymbolSubscriptionManager,
        )
        from data.realtime.reconnect_policy import ReconnectPolicy

        manager = ExplicitSymbolUniverseManager(
            symbols=self.symbols, timeframe=self.timeframe)
        self._manager = MultiSymbolSubscriptionManager(
            transport_factory=lambda: self.transport,
            clock=self._clock,
            policy=ReconnectPolicy(),
            candles_callback=None,
            max_stale_seconds=30.0,
        )
        self._engine = RealTimeEngine(
            universe_manager=manager,
            refresh_scheduler=RefreshScheduler(
                manager=manager,
                interval_seconds=self.refresh_interval_seconds,
                clock=self._clock,
            ),
            subscription_manager=self._manager,
            clock=self._clock,
            timeframe=self.timeframe,
            starting_balance=None,
        )
        poll_seconds = getattr(
            __import__("config.settings", fromlist=["settings"]).settings,
            "CONTROL_API_POLL_SECONDS", 10.0,
        )
        self._lifecycle = EngineLifecycle(
            self._engine,
            poll_interval_seconds=poll_seconds,
        )
        # Callback must be in place before lifecycle.start(): the first
        # refresh pass syncs subscriptions and starts the workers that
        # hand candles to the engine.
        self._manager.candles_callback = self._engine._on_closed_candle
        self._lifecycle.start()
        self._started_at = time.time()
        receipt = {
            "session_id": self.session_id,
            "session_mode": SESSION_MODE_LIVE,
            "market_data_source": self.market_data_source,
            "fills_are": FILL_CLASS,
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "run_seconds": self.run_seconds,
            "started_utc": _utc_iso(self._started_at),
            "instrument_metadata": "SYNTHETIC_SPOT_FALLBACK (explicit-cut "
                                   "universe; not derivative-realistic)",
        }
        return receipt

    def request_stop(self, reason="operator_stop") -> None:
        with self._session_lock:
            self._stop_reason = reason or self._stop_reason
        if self._lifecycle is not None:
            try:
                self._lifecycle.stop()
            except Exception:  # noqa: BLE001
                pass

    def heartbeat(self) -> dict:
        """One observational snapshot of the live session."""
        engine = self._engine
        statuses = self._manager.statuses() if self._manager else {}
        stream = {}
        for symbol, state in sorted(statuses.items()):
            stream[symbol] = {
                "status": str(getattr(state, "status", "")),
                "received": int(getattr(state, "received", 0) or 0),
                "delivered": int(getattr(state, "delivered", 0) or 0),
                "duplicates": int(getattr(state, "duplicates", 0) or 0),
                "out_of_order": int(getattr(state, "out_of_order", 0) or 0),
                "forming_skipped": int(
                    getattr(state, "forming_skipped", 0) or 0),
                "reconnect_attempts": int(
                    getattr(state, "reconnect_attempts", 0) or 0),
                "last_error": str(getattr(state, "last_error", "") or ""),
            }
        runtime_states = {}
        if engine is not None:
            for key, runtime in sorted(engine.runtimes.items()):
                runtime_states[runtime.symbol] = runtime.state()
        snapshot = {
            "utc": _utc_iso(),
            "routed": int(getattr(engine, "routed", 0) or 0),
            "unrouted": int(getattr(engine, "unrouted", 0) or 0),
            "route_errors": int(getattr(engine, "route_errors", 0) or 0),
            "transport_delivered": self.transport.delivered_count(),
            "history_calls": self.counting_history.calls,
            "history_errors": self.counting_history.errors,
            "streams": stream,
            "runtimes": runtime_states,
            "verdict_logs": self._log_observer.snapshot(),
        }
        with self._session_lock:
            self._heartbeats.append(snapshot)
        print(
            "%s routed=%d unrouted=%d delivered=%d route_errors=%d "
            "poll_errors=%d" % (
                _HEARTBEAT_PREFIX, snapshot["routed"],
                snapshot["unrouted"], snapshot["transport_delivered"],
                snapshot["route_errors"], self.counting_history.errors,
            ),
            flush=True,
        )
        return snapshot

    def run(self) -> dict:
        """Run the bounded session to completion, then finalize."""
        if self._lifecycle is None:
            self.start()
        stop_timer = None
        if self.run_seconds is not None:
            stop_timer = threading.Timer(
                self.run_seconds,
                lambda: self.request_stop("run_seconds_elapsed"),
            )
            stop_timer.daemon = True
            stop_timer.start()
        try:
            self._lifecycle.wait()
        except KeyboardInterrupt:
            self.request_stop("keyboard_interrupt")
        finally:
            if stop_timer is not None:
                stop_timer.cancel()
            self._stopped_at = time.time()
            try:
                # lifecycle.stop() joins the control thread and then
                # calls engine.stop() itself (graceful, idempotent).
                self._lifecycle.stop()
            except Exception:  # noqa: BLE001
                pass
        return self.finalize()

    def finalize(self) -> dict:
        """Collect counters, audit quality, reconcile, write artifacts."""
        engine = self._engine
        delivered = self.transport.delivered_candles()
        quality = _delivery_quality(delivered, self.window)
        warmup: dict[str, int] = {}
        for symbol, rows in delivered.items():
            warmup[symbol] = sum(
                1 for r in rows
                if int(r.get("history_call_index", 0)) <= 2
            )
        try:
            from data.realtime.verified_replay import (
                reconcile_paper_ledger,
            )

            class _Duck:
                def __init__(self, engine_ref):
                    self.engine = engine_ref

            raw_reconciliation = reconcile_paper_ledger(_Duck(engine))
            # The Phase-24 checker keys by the engine's identity tuple;
            # re-key by symbol for the JSON artifact.
            by_symbol = {}
            for key, runtime in engine.runtimes.items():
                verdict = raw_reconciliation.get("symbols", {}).get(key)
                if verdict is not None:
                    by_symbol[runtime.symbol] = verdict
            reconciliation = {
                "symbols": by_symbol,
                "consistent": all(
                    bool(v.get("reconciled"))
                    for v in by_symbol.values()
                ) and bool(by_symbol),
            }
        except Exception as exc:  # noqa: BLE001 (observability only)
            reconciliation = {"error": "%s: %s" % (type(exc).__name__, exc),
                              "consistent": False}
        report = {
            "schema": "quantengine.phase25-paper-session-report.v1",
            "session_id": self.session_id,
            "session_mode": SESSION_MODE_LIVE,
            "evidence_class": "EXCHANGE_SOURCED_PAPER_SIMULATION",
            "preliminary": True,
            "market_data_source": self.market_data_source,
            "market_data_endpoint": "https://api.delta.exchange"
                                    "/v2/history/candles",
            "fills_are": FILL_CLASS,
            "instrument_metadata": "SYNTHETIC_SPOT_FALLBACK",
            "cost_economics": _cost_profile_snapshot(),
            "config": {
                "symbols": list(self.symbols),
                "timeframe": self.timeframe,
                "window_seconds": self.window,
                "run_seconds": self.run_seconds,
                "poll_interval_seconds": self.poll_interval_seconds,
                "lookback_days": self.lookback_days,
                "refresh_interval_seconds": self.refresh_interval_seconds,
                "starting_balance_default": 2000,
            },
            "provenance": {
                "code_revision": self._git_head(),
                "utc_start": _utc_iso(self._started_at),
                "utc_end": _utc_iso(self._stopped_at),
                "wall_seconds": round(
                    (self._stopped_at or time.time())
                    - (self._started_at or time.time()), 3),
                "stop_reason": self._stop_reason or "completed",
            },
            "market_data": {
                "rest_history": self.counting_history.snapshot(),
                "transport_stats": self.transport.stats(),
                "delivered_quality": quality,
                "warmup_delivered": warmup,
                "live_delivered": {
                    symbol: max(0, entry["delivered"] - warmup.get(symbol, 0))
                    for symbol, entry in quality.items()
                },
            },
            "engine": {
                "routed": int(getattr(engine, "routed", 0) or 0),
                "unrouted": int(getattr(engine, "unrouted", 0) or 0),
                "route_errors": int(getattr(engine, "route_errors", 0) or 0),
                "last_route_error": str(
                    getattr(engine, "last_route_error", "") or ""),
                "reconcile_errors": int(
                    getattr(engine, "reconcile_errors", 0) or 0),
                "pipelines": int(getattr(engine.registry, "count", 0) or 0)
                if hasattr(engine, "registry") else None,
            },
            "decisions": self._log_observer.snapshot(),
            "runtimes": _runtime_rows(engine),
            "reconciliation": reconciliation,
            "heartbeats": list(self._heartbeats),
            "operational_errors": [
                {"symbol": s, "stage": stage, "error": str(err)[:300]}
                for (s, stage, err) in (
                    getattr(self._manager, "errors", []) or [])
            ],
        }
        self._write_artifacts(report, delivered)
        try:
            self._log_observer.detach()
        except Exception:  # noqa: BLE001
            pass
        return report

    # ------------------------------------------------------------------

    def _git_head(self) -> str:
        try:
            import subprocess

            out = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=15,
            )
            return out.stdout.strip() or "unknown"
        except Exception:  # noqa: BLE001
            return "unknown"

    def _write_artifacts(self, report, delivered) -> None:
        session_dir = self.output_dir / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        report_path = session_dir / "session_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        capture_path = session_dir / "delivered_candles.jsonl"
        with capture_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "provenance": {
                    "session_id": self.session_id,
                    "session_mode": SESSION_MODE_LIVE,
                    "market_data_source": self.market_data_source,
                    "endpoint": report["market_data_endpoint"],
                    "symbol_order": list(self.symbols),
                    "timeframe": self.timeframe,
                    "code_revision": report["provenance"][
                        "code_revision"],
                    "fills_are": FILL_CLASS,
                },
            }, sort_keys=True) + "\n")
            for symbol in sorted(delivered):
                for row in delivered[symbol]:
                    handle.write(json.dumps(
                        row, sort_keys=True) + "\n")
        summary = self._summary_text(report)
        (session_dir / "session_summary.md").write_text(
            summary, encoding="utf-8",
        )
        self.artifact_paths = {
            "session_report": str(report_path),
            "delivered_candles": str(capture_path),
            "session_summary": str(session_dir / "session_summary.md"),
        }

    @staticmethod
    def _summary_text(report) -> str:
        md = report["market_data"]
        eng = report["engine"]
        rec = report["reconciliation"]
        lines = [
            "# Phase 25 paper session — %s" % report["session_id"],
            "",
            "- Mode: %s (market data: %s)" % (
                report["session_mode"], report["market_data_source"]),
            "- Evidence class: %s (fills: %s; PRELIMINARY)" % (
                report["evidence_class"], report["fills_are"]),
            "- Window: %s .. %s (%.1fs)" % (
                report["provenance"]["utc_start"],
                report["provenance"]["utc_end"],
                report["provenance"]["wall_seconds"]),
            "- Symbols: %s @ %s" % (
                ", ".join(report["config"]["symbols"]),
                report["config"]["timeframe"]),
            "- Cost economics: %s (%s)" % (
                report["cost_economics"]["profile_name"],
                report["cost_economics"]["classification"]),
            "- REST polls: %d calls, %d rows seen, %d errors" % (
                md["rest_history"]["calls"],
                md["rest_history"]["rows_seen"],
                md["rest_history"]["errors"]),
        ]
        for symbol, q in sorted(md["delivered_quality"].items()):
            lines.append(
                "- Delivered %s: %d closed bars (warm-up %d), ascending=%s, "
                "duplicates=%d, internal_missing=%d" % (
                    symbol, q["delivered"],
                    report["market_data"]["warmup_delivered"].get(symbol, 0),
                    q["ascending"], q["duplicate_buckets"],
                    q["internal_missing_buckets"],
                ),
            )
        lines += [
            "- Engine: routed=%d unrouted=%d route_errors=%d" % (
                eng["routed"], eng["unrouted"], eng["route_errors"]),
            "- Decisions (log verdicts): %s" % (
                json.dumps(report["decisions"], sort_keys=True)),
        ]
        for symbol, row in report["reconciliation"].get(
                "symbols", {}).items():
            lines.append(
                "- Reconciled %s: equity=%.2f start=%.2f realized=%.2f "
                "reconciled=%s" % (
                    symbol, row["equity"], row["starting_balance"],
                    row["realized_pnl"], row["reconciled"]),
            )
        if not rec.get("consistent", False):
            lines.append(
                "- RECONCILIATION: %s" % json.dumps(rec, sort_keys=True))
        lines += [
            "",
            "A short session validates pipeline behaviour only; it does "
            "not establish strategy profitability.",
            "",
        ]
        return "\n".join(lines)


# ----------------------------------------------------------------------
# Mode B: offline replay (delegates to the Phase-24 verified harness)
# ----------------------------------------------------------------------

def run_replay_session(
    *,
    capture_path=None,
    synthetic_seed=99,
    synthetic_candles=600,
    faults=None,
    repair_gap=False,
    output_dir="reports/PAPER_SESSIONS",
    session_id=None,
) -> dict:
    """Run an offline replay session through the Phase-24 verified
    harness and wrap the result in a Phase-25 session report.

    The Phase-24 report's own ``evidence_class`` is preserved verbatim
    (CAPTURED or SYNTHETIC_FIXTURE); this wrapper never upgrades an
    offline result into a live session claim.
    """
    from data.realtime.verified_replay import (
        load_capture,
        synthetic_candle_frames,
        VerifiedTransportReplay,
    )

    if capture_path:
        bundle = load_capture(capture_path)
        records = bundle.records
        evidence_class = bundle.evidence_class
        symbol = str(bundle.symbol or "BTCUSDT")
        source = "capture_bundle:%s" % capture_path
    else:
        records = synthetic_candle_frames(
            "BTCUSDT", candles=int(synthetic_candles),
            seed=int(synthetic_seed),
        )
        evidence_class = "SYNTHETIC_FIXTURE"
        symbol = "BTCUSDT"
        source = "synthetic_frames:seed=%d:candles=%d" % (
            synthetic_seed, synthetic_candles,
        )
    harness = VerifiedTransportReplay([symbol])
    harness.start()
    try:
        if repair_gap:
            repair = harness.repair_gap_history(harness.symbols[0])
        else:
            repair = None
        phase24_report = harness.run(records, faults=faults or ())
    finally:
        harness.close()
    counts = phase24_report.to_dict()["counts"]
    engine_counts = counts.get("engine", {})
    session_id = session_id or (
        "P25-REPLAY-%s" % _utc_iso().replace(":", "").replace("-", ""))
    report = {
        "schema": "quantengine.phase25-paper-session-report.v1",
        "session_id": session_id,
        "session_mode": SESSION_MODE_REPLAY,
        "evidence_class": phase24_report.evidence_class,
        "preliminary": True,
        "market_data_source": source,
        "market_data_endpoint": None,
        "fills_are": FILL_CLASS,
        "gap_repair": repair,
        "phase24_report": json.loads(phase24_report.to_json()),
        "cost_economics": _cost_profile_snapshot(),
    }
    session_dir = Path(output_dir) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (session_dir / "session_summary.md").write_text(
        "# Phase 25 OFFLINE replay session — %s\n\n"
        "- Evidence class: %s (NOT a live market session)\n"
        "- Data source: %s\n"
        "- Fills: %s (simulated)\n"
        "- Frames: %d input, %d ingested; routed=%s unrouted=%s\n"
        % (
            session_id, evidence_class, source,
            FILL_CLASS,
            counts.get("frames_input", 0),
            counts.get("frames_ingested", 0),
            engine_counts.get("routed"), engine_counts.get("unrouted"),
        ),
        encoding="utf-8",
    )
    report["artifact_paths"] = {
        "session_report": str(session_dir / "session_report.json"),
        "session_summary": str(session_dir / "session_summary.md"),
    }
    return report
