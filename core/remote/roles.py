"""
====================================================

QuantEngine - Secure Remote / Mobile Control Foundation

roles.py -- three-tier permission model (Phase 9P-k).

Defines the VIEW / CONTROL / EMERGENCY tiers and maps every
request that may reach the remote gateway to the minimum role
required to perform it. The gateway consults this registry to
authorize a request AFTER authenticating the principal's role
token, so authorization is enforced purely at the remote
boundary and never requires knowledge of engine internals.

The tiers are strictly ordered:

    VIEW      <= CONTROL <= EMERGENCY

A principal with a higher tier satisfies any lower-tier
requirement.

Hard phase-9P-k bounds enforced here as DATA (not afterthoughts):

  * Only the read endpoints are VIEW-permitted. There are no
    strategy/risk/position/order "write" routes on the remote
    surface -- such a route does not exist in this registry, so
    it can never be reached, at ANY tier.
  * LIVE-mode enablement is absent from this registry entirely.
  * The lifecycle verbs are partitioned: start/stop/restart
    require CONTROL; emergency_stop requires EMERGENCY.

Stdlib only.
====================================================
"""

import hmac

VIEW = "VIEW"
CONTROL = "CONTROL"
EMERGENCY = "EMERGENCY"

_ROLE_ORDER = (VIEW, CONTROL, EMERGENCY)
_ROLE_RANK = {role: idx for idx, role in enumerate(_ROLE_ORDER)}


def role_rank(role):
    """Return the rank of a role (higher = more privileged)."""
    return _ROLE_RANK.get(role, -1)


def satisfies(role, required):
    """True when ROLE meets or exceeds the REQUIRED tier."""
    rr = _ROLE_RANK.get(role, -1)
    req = _ROLE_RANK.get(required, -1)
    if rr < 0 or req < 0:
        return False
    return rr >= req


# ------------------------------------------------------------------
# Route registry: (method, path) -> minimum role.
#
# All lookups normalise the path by stripping a query string and a
# trailing slash, matching the Control API's own normalisation
# (core/monitoring/api_server.py: path.split('?')[0].rstrip('/')) so
# the two tables line up 1:1.
# ------------------------------------------------------------------

READ_ROUTES = {
    ("GET", "/health"): VIEW,
    ("GET", "/universe"): VIEW,
    ("GET", "/subscriptions"): VIEW,
    ("GET", "/runtimes"): VIEW,
    ("GET", "/market"): VIEW,
    ("GET", "/signals"): VIEW,
    ("GET", "/positions"): VIEW,
    ("GET", "/orders"): VIEW,
    ("GET", "/account"): VIEW,
    ("GET", "/risk"): VIEW,
    ("GET", "/performance"): VIEW,
    ("GET", "/errors"): VIEW,
}

# lifecycle verb -> minimum role (CONTROL or EMERGENCY). start/stop/
# restart/pause/resume are CONTROL; emergency_stop is EMERGENCY-only.
CONTROL_COMMAND_ROLE = {
    "start": CONTROL,
    "stop": CONTROL,
    "restart": CONTROL,
    "pause": CONTROL,
    "resume": CONTROL,
    "emergency_stop": EMERGENCY,
}


def required_role(method, path):
    """Minimum role needed to perform (METHOD, PATH).

    Special-cases:
      * "/control" POST requires a role resolved per-command via
        CONTROL_COMMAND_ROLE (VIEW cannot issue any command).
      * The dashboard/static paths are open to any authenticated
        principal (they render no secrets on their own; data only
        arrives as JSON over the role-gated API).
      * Any method/path NOT in the allowlist is treated as
        UNREACHABLE (requires a role that nobody has) so unknown or
        non-allowlisted requests are refused at authorization time.
    """
    up_path, _sep, _q = path.partition("?")
    up_path = up_path.rstrip("/") or "/"

    if up_path in ("/", "/index.html", "/app.js", "/app.css",
                   "/manifest.json", "/favicon.ico", "/sw.js",
                   "/api/me"):
        return VIEW

    if (method, up_path) in READ_ROUTES:
        return READ_ROUTES[(method, up_path)]

    if method == "POST" and up_path == "/control":
        # per-command role; caller resolves the specific command from
        # the body and re-checks via command_required_role
        return "COMMAND"

    return None


def command_required_role(command):
    """Minimum role for a lifecycle command string, or None if the
    command is not permitted remotely at all."""
    return CONTROL_COMMAND_ROLE.get(command)


def _tokens_equal(left, right):
    a = (left or "").encode("utf-8")
    b = (right or "").encode("utf-8")
    return hmac.compare_digest(a, b)
