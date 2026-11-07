"""QuantEngine real-market-data paper-trading preview (launcher).

Starts, from VS Code or a terminal:

    python scripts/paper_preview.py

What it starts (ONE local process, localhost only):

    REAL Delta public REST closed candles (BTCUSDT 1m default)
        -> RestPollingCandleTransport (closed bars only)
        -> canonical build_paper_engine stack
           (RealTimeEngine -> PaperRuntime -> BrokerEngine dry-run)
        -> ControlApiServer on 127.0.0.1 + read-only preview routes
        -> static read-only browser dashboard at /dashboard

Safety (fail-closed, enforced before anything starts):

  * Refuses when LIVE execution is armed (LIVE_MODE/EXECUTION_MODE).
  * Explicit PAPER_ONLY mode; zero exchange writes (dry_run).
  * No credentials required (public data); none used for trading.
  * API bound to 127.0.0.1 with bearer token (dev default below is
    localhost-only; override via CONTROL_API_TOKEN).

Environment (all optional):

    PREVIEW_SYMBOLS      comma list, default "BTCUSDT"
    PREVIEW_TIMEFRAME    default "1m" (only verified square 1m/5m/15m/1h/4h/1d)
    PREVIEW_PORT         default 8787 (CONTROL_API_PORT when set)
    PREVIEW_TOKEN        dev-default bearer token (CONTROL_API_TOKEN wins)
    PREVIEW_RUN_SECONDS  bounded run then clean shutdown (manual
                         acceptance); unset = run until Ctrl+C.

Shutdown: Ctrl+C or POST /control {"command": "stop"} (PAPER-only
lifecycle verb, token required).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Repository-root bootstrap (canonical scripts/ convention):
# running `python scripts/paper_preview.py` puts scripts/ first on
# sys.path, so the repo-root packages (core/, data/, config/)
# would not resolve. Establish the root BEFORE any QuantEngine
# import. Stdlib-only: no configuration impact.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Environment-first defaults: applied BEFORE any QuantEngine
# import because config.settings reads the environment at import.
os.environ.setdefault("PAPER_MODE", "true")
os.environ.setdefault("CONTROL_API_ENABLED", "true")
os.environ.setdefault("CONTROL_API_TOKEN",
                      os.getenv("PREVIEW_TOKEN",
                               "paper-preview-local-dev"))
os.environ.setdefault("CONTROL_API_PORT",
                      os.getenv("PREVIEW_PORT", "8787"))

LIVE_FLAGS = ("LIVE_MODE", "EXECUTION_MODE")


def _refuse_live():
    """Fail closed when any live arming is present."""
    live_mode = os.getenv("LIVE_MODE", "").strip().lower() in (
        "1", "true", "yes", "on")
    execution_mode = os.getenv("EXECUTION_MODE", "").strip().upper()
    if live_mode or execution_mode == "LIVE":
        print("REFUSED: live execution flags detected "
              "(LIVE_MODE=%r EXECUTION_MODE=%r); the paper preview "
              "never starts armed." % (
                  os.getenv("LIVE_MODE", ""),
                  os.getenv("EXECUTION_MODE", "")), file=sys.stderr)
        raise SystemExit(2)
    if execution_mode not in ("", "PAPER"):
        print("REFUSED: unknown EXECUTION_MODE=%r." % execution_mode,
              file=sys.stderr)
        raise SystemExit(2)


def main() -> int:
    _refuse_live()

    symbols = [s.strip() for s in
               os.getenv("PREVIEW_SYMBOLS", "BTCUSDT").split(",")
               if s.strip()]
    if not symbols:
        print("REFUSED: PREVIEW_SYMBOLS is empty.", file=sys.stderr)
        return 2
    timeframe = os.getenv("PREVIEW_TIMEFRAME", "1m").strip() or "1m"
    run_seconds = os.getenv("PREVIEW_RUN_SECONDS", "").strip()
    stop_after = float(run_seconds) if run_seconds else None

    from core.monitoring import service as monitoring_service
    from core.monitoring.preview_routes import preview_routes
    from core.runtime.paper_main import (
        ExplicitSymbolUniverseManager,
        build_paper_engine,
    )
    from data.delta.rest_candle_transport import (
        RestPollingCandleTransport,
    )

    manager = ExplicitSymbolUniverseManager(
        symbols=symbols, timeframe=timeframe)

    # Pre-created shared transport (multiplex model): the factory
    # hands the SAME instance to every worker, and the preview
    # routes read its ring buffer + stats directly.
    transport = RestPollingCandleTransport(timeframe=timeframe)

    def transport_factory():
        return transport

    engine, _manager = build_paper_engine(
        universe_manager=manager,
        transport_factory=transport_factory,
        timeframe=timeframe,
        refresh_interval_seconds=60,
    )
    routes = preview_routes(engine, transport)

    token = os.getenv("CONTROL_API_TOKEN", "")
    port = int(os.getenv("CONTROL_API_PORT", "8787"))

    print("=" * 60)
    print("QuantEngine PAPER PREVIEW (real public market data)")
    print("=" * 60)
    print("MODE            : PAPER_ONLY (dry_run, zero exchange writes)")
    print("MARKET DATA     : LIVE PUBLIC Delta REST closed candles")
    print("SYMBOLS         : %s" % ", ".join(symbols))
    print("TIMEFRAME       : %s" % timeframe)
    print("LIVE EXECUTION  : DISABLED")
    print("PRODUCTION READY: FALSE")
    print("API             : http://127.0.0.1:%d (token required)" % port)
    print("DASHBOARD       : http://127.0.0.1:%d/dashboard" % port)
    print("API TOKEN       : %s" % token)
    print("(localhost-only development default; override with "
          "CONTROL_API_TOKEN)")
    if stop_after:
        print("BOUNDED RUN     : %.0f seconds, then clean shutdown"
              % stop_after)
    print("=" * 60)

    monitoring_service.run_paper_with_monitoring(
        engine,
        extra_routes=routes,
        stop_after_seconds=stop_after,
    )

    # End-of-run summary: bounded runs previously exited silently,
    # leaving routing/bookkeeping unverified. Read-only counters.
    try:
        runtimes = list(getattr(engine, "runtimes", {}).values())
        bars = sum(int(getattr(rt, "processed_bars", 0) or 0)
                   for rt in runtimes)
        trades = sum(int(rt.ledger.count()) for rt in runtimes
                     if hasattr(rt, "ledger")
                     and hasattr(rt.ledger, "count"))
        print("RUN_SUMMARY routed=%s unrouted=%s route_errors=%s "
              "runtimes=%d processed_bars=%d paper_trades=%d" % (
                  getattr(engine, "routed", 0),
                  getattr(engine, "unrouted", 0),
                  getattr(engine, "route_errors", 0),
                  len(runtimes), bars, trades))
        print("CLEAN_SHUTDOWN")
    except Exception as exc:
        print("RUN_SUMMARY_FAILED %s: %s"
              % (type(exc).__name__, exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
