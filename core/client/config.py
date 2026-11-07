"""
====================================================

QuantEngine

Lightweight Desktop Control Client - configuration

Phase 9P-h.

Client-side connection configuration for the Control &
Monitoring API. Defaults mirror the existing API defaults
(127.0.0.1:8787) and a moderate polling interval.

The client NEVER writes to, or auto-enables, the engine's
Control API. It only reads these values to contact a server
the operator has already started (e.g. `python main.py`
with CONTROL_API_ENABLED=True).

Values are read from the environment on first access; a token
from the QENGINE_CLIENT_TOKEN / CONTROL_API_TOKEN environment
variable. No secret is ever hardcoded here.

Stdlib only: os.
====================================================
"""

import os


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_TIMEOUT = 5.0


class ClientConfig:

    def __init__(
        self,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        token="",
        poll_interval=DEFAULT_POLL_INTERVAL,
        timeout=DEFAULT_TIMEOUT,
    ):
        self.host = host or DEFAULT_HOST
        self.port = int(port) if port else DEFAULT_PORT
        self.token = token or ""
        self.poll_interval = (
            float(poll_interval) if poll_interval else DEFAULT_POLL_INTERVAL
        )
        self.timeout = float(timeout) if timeout else DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls, env=None):
        """Build from the process environment, falling back to the
        API defaults. The token is read from an environment variable
        only -- never a hardcoded source."""

        env = env if env is not None else os.environ

        token = env.get(
            "QENGINE_CLIENT_TOKEN", ""
        ) or env.get("CONTROL_API_TOKEN", "")

        return cls(
            host=env.get("QENGINE_CLIENT_HOST", DEFAULT_HOST),
            port=int(env.get("QENGINE_CLIENT_PORT", DEFAULT_PORT)),
            token=token,
            poll_interval=float(
                env.get("QENGINE_CLIENT_POLL", DEFAULT_POLL_INTERVAL)
            ),
            timeout=float(env.get("QENGINE_CLIENT_TIMEOUT", DEFAULT_TIMEOUT)),
        )

    def as_dict(self):
        """Non-secret view (never includes the token)."""

        return {
            "host": self.host,
            "port": self.port,
            "poll_interval": self.poll_interval,
            "timeout": self.timeout,
            "token_configured": bool(self.token),
        }
