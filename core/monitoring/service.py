"""
====================================================

QuantEngine

Control & Monitoring API -- service wiring

Phase 9P-f.

Thin orchestration that gates the monitoring service on operator
config and wires it around an already-built engine + lifecycle:

    build_engine()     -- existing paper_main.build_paper_engine
    EngineLifecycle    -- the control seam (core/runtime/lifecycle)
    ControlApiServer   -- the HTTP read surface (core/monitoring)

start_api(engine, lifecycle) builds and starts the server ONLY
when CONTROL_API_ENABLED is true; otherwise returns None (the
engine+lifecycle keep running as normal, no HTTP surface). If the
API is enabled but no CONTROL_API_TOKEN is configured, this FAILS
CLOSED (raises) -- an enabled, tokenless control surface is never
started. Duplicate API servers are refused.

run_paper_with_monitoring(engine) is the PRODUCTION PAPER
ENTRYPOINT integration: it drives the engine through an
EngineLifecycle (which owns the poll-loop thread), starts the
gated monitoring API around that SAME authoritative engine, and
then blocks until the lifecycle stops (a KeyboardInterrupt or an
API /control/stop), after which both the lifecycle and the server
are shut down cleanly.

This facade contains no trading/risk/order logic; it only wires
the existing engine, the lifecycle manager, and the server.
Beginning Phase 9P-k it ALSO starts/stops the secure remote/mobile
gateway (core/remote) around the same authoritative engine when the
operator has enabled it.
====================================================
"""


class ControlApiConfigError(RuntimeError):

    """Raised when the monitoring API is enabled without the
    required bearer token (fail closed), or when a duplicate API
    server is requested."""


# guards against starting more than one API server per process
_active_server = None


def enabled():
    """True when the monitoring API is enabled by operator config."""

    from config.settings import settings

    return bool(getattr(settings, "CONTROL_API_ENABLED", False))


def config_token():
    """The configured bearer token (may be empty)."""

    from config.settings import settings

    return getattr(settings, "CONTROL_API_TOKEN", "") or ""


def start_api(engine, lifecycle, extra_routes=None):
    """Build + start the monitoring server on a daemon thread,
    gated on operator config.

    Returns the running ControlApiServer, or None when the API is
    disabled. Raises ControlApiConfigError when the API is enabled
    but no token is configured (fail closed), or when an API server
    is already running (no duplicate servers). extra_routes (an
    optional {(method, path): handler} mapping of additional
    READ-ONLY routes) is merged before serving.
    """
    global _active_server

    if not enabled():

        return None

    if _active_server is not None and _active_server.running():

        raise ControlApiConfigError(
            "A Control API server is already running; refusing to "
            "start a duplicate."
        )

    token = config_token()

    if not token:

        raise ControlApiConfigError(
            "CONTROL_API is enabled but CONTROL_API_TOKEN is empty; "
            "the monitoring surface refused to start (fail closed)."
        )

    from core.monitoring.api_server import ControlApiServer

    server = ControlApiServer.from_settings(
        engine, lifecycle, extra_routes=extra_routes)

    server.serve_forever_threaded()

    _active_server = server

    return server


def stop_api(server):
    """Shut down a running monitoring server and release the active
    server guard. Safe when SERVER is None (not started)."""

    global _active_server

    if server is not None:

        try:

            server.shutdown()

        except Exception:

            pass

    if _active_server is server:

        _active_server = None


# =====================================================
# Production PAPER entrypoint wiring
# =====================================================


def start_paper_service(
    engine,
    *,
    client=None,
    normalizer=None,
    poll_interval_seconds=None,
    extra_routes=None,
    stop_after_seconds=None,
):
    """Drive the engine through an authoritative EngineLifecycle and
    start the gated monitoring API around that SAME engine.

    Returns (lifecycle, server_or_None). The lifecycle's control
    thread owns the poll loop; the server (when enabled) is bound to
    localhost with bearer-token protection and only exposes the
    PAPER-only control verbs. The remote gateway (Phase 9P-k; when
    REMOTE_GATEWAY_ENABLED) is also started and tracked module-wide
    so block_until_stopped() cleans it up. Call block_until_stopped()
    to run and clean up.
    """
    from core.runtime.lifecycle import EngineLifecycle

    if poll_interval_seconds is None:

        from config.settings import settings

        poll_interval_seconds = getattr(
            settings, "CONTROL_API_POLL_SECONDS", 10.0
        )

    lifecycle = EngineLifecycle(
        engine,
        poll_interval_seconds=poll_interval_seconds,
        client=client,
        normalizer=normalizer,
    )

    server = start_api(engine, lifecycle, extra_routes=extra_routes)

    # Phase 9P-k: the secure remote/mobile gateway is started only
    # when operator-enabled (REMOTE_GATEWAY_ENABLED). start_remote_gateway
    # returns None when disabled and FAILS CLOSED when enabled but
    # under-configured. The active gateway is tracked in
    # core/remote/service.py; it is stopped in block_until_stopped().
    from core.remote.service import start_remote_gateway

    try:
        start_remote_gateway()
    except Exception as exc:
        stop_api(server)
        raise

    lifecycle.start()

    # Bounded preview runs: stop the lifecycle after N seconds
    # via a daemon timer (same thread-safe stop() the API
    # /control/stop path uses). None (default) runs until
    # stopped by the operator, preserving existing behaviour.
    if stop_after_seconds is not None:
        import threading as _threading

        _timer = _threading.Timer(
            max(1.0, float(stop_after_seconds)), lifecycle.stop)
        _timer.daemon = True
        _timer.start()

    return lifecycle, server


def block_until_stopped(lifecycle, server):
    """Block until the lifecycle leaves its running state (a
    KeyboardInterrupt or an API /control/stop), then shut down the
    lifecycle, the monitoring server, and (Phase 9P-k) the active
    remote gateway cleanly."""

    try:

        lifecycle.wait()

    except KeyboardInterrupt:

        pass

    finally:

        try:

            lifecycle.stop()

        except Exception:

            pass

        stop_api(server)

        from core.remote.service import stop_active_remote_gateway

        stop_active_remote_gateway()


def run_paper_with_monitoring(
    engine,
    *,
    client=None,
    normalizer=None,
    poll_interval_seconds=None,
    extra_routes=None,
    stop_after_seconds=None,
):
    """PRODUCTION PAPER entrypoint: drive the engine via an
    EngineLifecycle, start the gated monitoring API, and block until
    stopped, then clean up both. This is what main.py's PAPER path
    uses (in place of run_paper_forever) so the API and the PAPER
    runtime share the same authoritative engine.
    """

    lifecycle, server = start_paper_service(
        engine,
        client=client,
        normalizer=normalizer,
        poll_interval_seconds=poll_interval_seconds,
        extra_routes=extra_routes,
        stop_after_seconds=stop_after_seconds,
    )

    block_until_stopped(lifecycle, server)
