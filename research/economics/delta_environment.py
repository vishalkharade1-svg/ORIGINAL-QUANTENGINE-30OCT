"""Fail-closed Delta environment mapping for authenticated evidence capture."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeltaEnvironment:
    name: str
    rest_base_url: str
    private_ws_url: str
    public_ws_url: str


INDIA_PRODUCTION = DeltaEnvironment(
    "india_production",
    "https://api.india.delta.exchange",
    "wss://socket.india.delta.exchange",
    "wss://public-socket.india.delta.exchange",
)

INDIA_TESTNET = DeltaEnvironment(
    "india_testnet",
    "https://cdn-ind.testnet.deltaex.org",
    "wss://socket-ind.testnet.deltaex.org",
    "wss://socket-ind-pub.testnet.deltaex.org",
)


def resolve_environment(name: str) -> DeltaEnvironment:
    key = str(name).strip().lower()
    if key in {"india_testnet", "testnet", "demo"}:
        return INDIA_TESTNET
    if key in {"india_production", "production", "prod"}:
        return INDIA_PRODUCTION
    raise ValueError(f"unsupported Delta environment: {name!r}")


def validate_endpoints(environment: str, *, rest_base_url: str, private_ws_url: str) -> None:
    expected = resolve_environment(environment)
    if rest_base_url.rstrip("/") != expected.rest_base_url or private_ws_url.rstrip("/") != expected.private_ws_url:
        raise ValueError(
            f"Delta endpoint/environment mismatch for {expected.name}: "
            f"expected REST={expected.rest_base_url}, WS={expected.private_ws_url}"
        )
