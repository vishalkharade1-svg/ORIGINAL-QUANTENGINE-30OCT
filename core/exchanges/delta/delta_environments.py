"""
====================================================

Delta Environment Authority (sandbox/production separation)

ONE authoritative environment-to-endpoint mapping for every
Delta REST path. Deterministic, explicit, centrally testable,
impossible to silently fall back.

Environments:

    PRODUCTION  live funds. REST https://api.delta.exchange
                (the pre-existing default, unchanged).
    SANDBOX     simulation funds. REST
                https://testnet-api.delta.exchange, verified
                LIVE 2026-09-23 as a responding demo-shaped
                catalog (Global symbology, 285 products vs 408
                production, zero commission rates). See
                docs/integrations/DELTA_ENVIRONMENTS.md.
    UNKNOWN     anything else (including unset). Private and
                state-changing operations MUST fail closed.

Fail-closed rules (all enforced here, all tested):

  * UNKNOWN never resolves to an endpoint.
  * SANDBOX + production endpoint is refused.
  * PRODUCTION + sandbox endpoint is refused.
  * Sandbox construction requires sandbox-sourced credentials
    (DELTA_SANDBOX_API_KEY/SECRET); production credentials are
    never reinterpreted as sandbox credentials (the venue binds
    keys to environments: demo keys work only on testnet).
  * Missing sandbox credentials refuse (SANDBOX_CREDENTIALS =
    UNAVAILABLE) instead of falling back to production keys.
  * Sandbox WebSocket is UNVERIFIED (no confirmed host): any
    sandbox WS resolution is refused until a host is verified.

What this module does NOT change (deliberate):

  * DeltaREST / DeltaSignedREST / DeltaExchange default
    constructors keep their exact production behavior
    (production default preserved and pinned by Test A).
    Environment selection happens ONLY through the explicit
    factory below — never implicitly, never by credential
    sniffing.

====================================================
"""

from __future__ import annotations


PRODUCTION = "PRODUCTION"
SANDBOX = "SANDBOX"
UNKNOWN = "UNKNOWN"

ENVIRONMENTS = (PRODUCTION, SANDBOX)

PRODUCTION_REST_URL = "https://api.delta.exchange"
SANDBOX_REST_URL = "https://testnet-api.delta.exchange"

PRODUCTION_WS_URL = "wss://public-socket.delta.exchange"

#: Sandbox WebSocket host: UNVERIFIED (no confirmed testnet WS
#: host). Resolving a sandbox WS endpoint is refused until a
#: host is verified against official venue evidence.
SANDBOX_WS_URL: str | None = None

REST_ENDPOINTS = {
    PRODUCTION: PRODUCTION_REST_URL,
    SANDBOX: SANDBOX_REST_URL,
}


class EnvironmentError(ValueError):
    """An environment/endpoint/credential combination is unsafe."""


def resolve_environment(name: object) -> str:
    """Normalize an environment name; anything unrecognized (or
    missing) is UNKNOWN. Pure, deterministic."""
    if isinstance(name, str) and name.strip().upper() in ENVIRONMENTS:
        return name.strip().upper()
    return UNKNOWN


def is_production_endpoint(url: object) -> bool:
    """True only for the exact production REST host."""
    return isinstance(url, str) and url.strip().rstrip("/") == PRODUCTION_REST_URL


def is_sandbox_endpoint(url: object) -> bool:
    """True only for the verified sandbox REST host."""
    return isinstance(url, str) and url.strip().rstrip("/") == SANDBOX_REST_URL


def resolve_rest_endpoint(environment: object) -> str:
    """Return the authoritative REST URL for an environment.

    UNKNOWN (or anything invalid) raises: there is no fallback.
    """
    normalized = resolve_environment(environment)
    if normalized == UNKNOWN:
        raise EnvironmentError(
            "UNKNOWN environment refuses endpoint resolution "
            "(no implicit production fallback)")
    return REST_ENDPOINTS[normalized]


def resolve_ws_endpoint(environment: object) -> str:
    """Return the authoritative WS URL for an environment.

    Production resolves to the existing public socket. Sandbox
    raises until a testnet WS host is verified. UNKNOWN raises.
    """
    normalized = resolve_environment(environment)
    if normalized == PRODUCTION:
        return PRODUCTION_WS_URL
    if normalized == SANDBOX:
        raise EnvironmentError(
            "sandbox WebSocket host is UNVERIFIED; refusing "
            "until a testnet WS endpoint is confirmed")
    raise EnvironmentError(
        "UNKNOWN environment refuses endpoint resolution")


def assert_endpoint_for_environment(environment: object,
                                    url: object) -> str:
    """Fail closed on any endpoint/environment mismatch.

    Returns the normalized endpoint on success. Refuses:
    SANDBOX+production host, PRODUCTION+sandbox host, UNKNOWN
    with anything, malformed URLs, and unknown hosts.
    """
    normalized = resolve_environment(environment)
    if normalized == UNKNOWN:
        raise EnvironmentError(
            "UNKNOWN environment cannot authorize an endpoint")
    if not isinstance(url, str) or not url.strip():
        raise EnvironmentError("endpoint is missing or malformed")
    canonical = url.strip().rstrip("/")
    if normalized == SANDBOX and not is_sandbox_endpoint(canonical):
        raise EnvironmentError(
            "SANDBOX environment refuses non-sandbox endpoint %r "
            "(production fallback is never silent)" % url)
    if normalized == PRODUCTION and not is_production_endpoint(canonical):
        raise EnvironmentError(
            "PRODUCTION environment refuses non-production "
            "endpoint %r" % url)
    return canonical


def credentials_for(environment: object) -> tuple[str, str]:
    """Return the (key, secret) sourced for an environment.

    Sandbox credentials come ONLY from DELTA_SANDBOX_API_KEY /
    DELTA_SANDBOX_API_SECRET; production credentials are never
    reinterpreted. Missing or UNKNOWN refuses instead of
    falling back. Values are returned, never logged here —
    callers must never print them.
    """
    from config.settings import settings

    normalized = resolve_environment(environment)
    if normalized == SANDBOX:
        key = str(getattr(settings, "SANDBOX_API_KEY", "") or "")
        secret = str(getattr(settings, "SANDBOX_API_SECRET", "") or "")
        if not key or not secret:
            raise EnvironmentError(
                "SANDBOX_CREDENTIALS = UNAVAILABLE "
                "(DELTA_SANDBOX_API_KEY/SECRET not configured; "
                "production credentials are never substituted)")
        return key, secret
    if normalized == PRODUCTION:
        key = str(getattr(settings, "API_KEY", "") or "")
        secret = str(getattr(settings, "API_SECRET", "") or "")
        if not key or not secret:
            raise EnvironmentError(
                "production credentials are not configured")
        return key, secret
    raise EnvironmentError(
        "UNKNOWN environment refuses credential resolution")


def sandbox_client() -> object:
    """Build an explicitly-sandbox DeltaExchange (fail-closed).

    Resolves the verified sandbox endpoint, sources sandbox-only
    credentials, validates the combination, and constructs the
    client against the sandbox host. Any failure raises before
    any transport exists. Reuses DeltaExchange/DeltaSignedREST —
    no second credential system.
    """
    from core.exchanges.delta.delta_exchange import DeltaExchange

    endpoint = assert_endpoint_for_environment(
        SANDBOX, resolve_rest_endpoint(SANDBOX))
    key, secret = credentials_for(SANDBOX)
    return DeltaExchange(api_key=key, api_secret=secret,
                         base_url=endpoint)
