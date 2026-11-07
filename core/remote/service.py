"""
====================================================

QuantEngine - Secure Remote / Mobile Control Foundation

service.py -- remote gateway service wiring (Phase 9P-k).

Thin orchestration that gates the remote gateway on operator
config, mirroring core/monitoring/service.py for the local Control
API:

    start_remote_gateway(local_token) -> RemoteGateway | None

Rules:
  * The gateway is started ONLY when REMOTE_GATEWAY_ENABLED is true
    (off by default) AND the local Control API is enabled (the
    gateway has nothing authoritative to forward to otherwise).
  * The gateway FAILS CLOSED: an enabled gateway that is
    under-configured (missing TLS cert/key, missing a required role
    token, or empty local token) raises RemoteGatewayConfigError
    rather than serving unauthenticated traffic.
  * Only ONE gateway may run per process.

This facade contains no trading/risk/order logic; it only wires the
existing Control API (as the forwarding target), the role tokens,
and the new TLS gateway.

Stdlib only.
====================================================
"""


class RemoteGatewayConfigError(RuntimeError):
    """Raised when the remote gateway is enabled but under-configured
    (fail closed) or a duplicate gateway is requested."""


_active_gateway = None


def remote_gateway_enabled():
    import os

    return os.getenv("REMOTE_GATEWAY_ENABLED", "").strip().lower() in (
        "1", "true", "yes", "on"
    )


def control_api_enabled():
    from config.settings import settings

    return bool(getattr(settings, "CONTROL_API_ENABLED", False))


def start_remote_gateway():
    """Build + start the remote gateway on a daemon thread, gated on
    operator config.

    Returns the running RemoteGateway, or None when REMOTE_GATEWAY_ENABLED
    is false. Raises RemoteGatewayConfigError when the gateway is enabled
    but the local Control API is disabled, when it is under-configured
    (cert/key/role tokens/local token missing -- fail closed), or when a
    gateway is already running.
    """
    global _active_gateway

    if not remote_gateway_enabled():
        return None

    if _active_gateway is not None and _active_gateway.running():
        raise RemoteGatewayConfigError(
            "A remote gateway is already running; refusing to start a "
            "duplicate."
        )

    if not control_api_enabled():
        raise RemoteGatewayConfigError(
            "REMOTE_GATEWAY_ENABLED requires the local Control API "
            "(CONTROL_API_ENABLED) to be enabled; refusing to start the "
            "gateway with nothing authoritative to forward to."
        )

    from core.remote.gateway import RemoteGateway, gateway_from_settings

    try:
        config = gateway_from_settings()
    except Exception as exc:
        raise RemoteGatewayConfigError(
            "failed to build remote gateway config: %s" % exc
        ) from exc

    gateway = RemoteGateway(config)
    gateway.serve_forever_threaded()

    _active_gateway = gateway
    return gateway


def stop_remote_gateway(gateway):
    """Shut down a running remote gateway and release the guard. Safe
    when GATEWAY is None (not started)."""
    global _active_gateway

    if gateway is not None:
        try:
            gateway.shutdown()
        except Exception:
            pass

    if gateway is not None and gateway.audit is not None:
        try:
            gateway.audit.close()
        except Exception:
            pass

    if _active_gateway is gateway:
        _active_gateway = None


def stop_active_remote_gateway():
    """Shut down the currently-active remote gateway (if any) and
    release the guard. Safe to call when none is running. Used by the
    monitoring service cleanup path without requiring the gateway to
    be threaded through every caller."""
    global _active_gateway

    stop_remote_gateway(_active_gateway)


def active_remote_gateway():
    """The currently-running RemoteGateway, or None."""
    return _active_gateway
