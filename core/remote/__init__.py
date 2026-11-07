"""
====================================================

QuantEngine

Secure Remote / Mobile Control Foundation

Phase 9P-k.

A lightweight, stdlib-only, authenticated TLS *reverse
gateway* that sits in front of the existing localhost Control
& Monitoring API (Phase 9P-f) so a mobile/web client can
monitor and -- with the right permission -- control the engine,
while keeping the existing engine, lifecycle and Control API
authoritative. NO second control system is created and no
strategy/risk/execution internals are touched.

Deployment topology (preferred):

    Phone/browser -> HTTPS Remote Gateway (new port)
                          -> 127.0.0.1:8787 Control API (Phase 9P-f)
                          -> PAPER runtime

The Control API stays bound to 127.0.0.1 and is never exposed
to the network by this module. The gateway is the ONLY new
network entry point, and by default it binds to 127.0.0.1 too;
external reachability is the operator's choice (private tunnel /
VPN / firewall), NOT something this code enables.

Design overview
---------------

This module is a facade of three cooperating pieces:

  * roles.py   -- the three-tier permission model and the route /
                  command registry that maps each request to the
                  minimum role required to perform it.
  * audit.py   -- a thread-safe, append-only audit log that records
                  every remote control action and significant auth
                  events (timestamp, principal/device, command,
                  result, prev/resulting state, correlation ID,
                  failure reason). NEVER records secrets/tokens.
  * gateway.py -- the transport + boundary enforcement: TLS
                  termination (operator-provided PEM cert/key), per-
                  role bearer-token authentication (constant-time),
                  constant-time authz, request correlation IDs
                  (X-Request-ID), rate limiting at the remote
                  boundary, a lock-out of replay/duplicate control
                  idempotency, and request forwarding to the local
                  Control API using the operator's local token. It
                  also serves the mobile-responsive PWA dashboard
                  (core/remote/dashboard.py).

What the gateway DOES NOT do (hard phase-9P-k rules):

  * It does NOT bind the Control API (127.0.0.1:8787) to any
    external address, and never binds itself to 0.0.0.0 by
    default.
  * It NOT capable of placing orders, sizing positions, changing
    leverage, changing strategy parameters, or changing risk
    limits -- those are not authorized at ANY permission tier and
    the underlying Control API does not offer them either.
  * It CANNOT enable LIVE-mode trading.
  * It uses only stdlib crypto primitives (hmac, secrets,
    ssl) -- NO custom cryptography and NO heavyweight framework.
  * It never logs or transmits a token in a body, a URL, an
    exception, or telemetry.

Permission model (three tiers)
------------------------------

  VIEW      -- read-only: every GET read endpoint of the Control
               API. Cannot issue any control verb.
  CONTROL   -- VIEW + the lifecycle verbs start / stop / restart.
  EMERGENCY -- CONTROL + the high-priority emergency_stop verb.

Per-role tokens are operator-provisioned (REMOTE_*_TOKEN env),
compared constant-time, distinct from the local CONTROL_API_TOKEN.
The gateway authenticates the remote principal against its role
token, THEN authorizes the specific request against the role, and
only then forwards it to the Control API using the local server
token. This keeps the role model at the boundary and the Control
API contract unchanged (preserving the existing desktop client).

Idempotency & replay protection
-------------------------------

Control verbs are already idempotent in the authoritative
EngineLifecycle (start/stop/emergency_stop are safe no-ops when
already in that state). The gateway additionally honours an
operator-supplied X-Request-ID so a duplicated/replayed control
request carries the same correlation ID; the audit log groups by
correlation ID, and rate limiting bounds how many control
attempts a principal/device can make in a window, deterring
blind replay/brute force at the boundary WITHOUT rate limiting
the internal engine poll loop.

Freshness & connection state (mobile client)
--------------------------------------------

The PWA tracks CONNECTED / DEGRADED / DISCONNECTED from the
reachability of the gateway + the Control API through it, and
displays a data-freshness timestamp derived from the health
surface so stale data is unmistakable. The mobile client renders
server responses verbatim and NEVER computes its own P&L / risk /
position numbers.

Stdlib only: http.server, ssl, hmac, secrets, urllib, json,
threading, time, dataclasses, pathlib.
====================================================
"""
