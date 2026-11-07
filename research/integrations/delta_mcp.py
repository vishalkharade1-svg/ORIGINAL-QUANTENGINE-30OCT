"""Delta Exchange MCP integration metadata and fail-closed invocation boundary.

Research/operator integration only.  QuantEngine production execution never
reads MCP configuration and never delegates order authority to MCP.

The Delta MCP server runs as a local stdio subprocess. Public market-data
operations require no key; account operations require a Read Data key; trade
operations require a Trading-permission key and are intentionally excluded
from this adapter.
"""
from __future__ import annotations

from dataclasses import dataclass


MCP_ENV_PRODUCTION = "india_prod"
MCP_ENV_TESTNET = "india_testnet"
MCP_ENVS = (MCP_ENV_PRODUCTION, MCP_ENV_TESTNET)

MCP_COMMAND = "uvx"
MCP_PACKAGE = "delta-exchange-mcp"

# Public market-data tools documented by Delta.  Keep this list explicit so a
# future tool addition cannot silently expand the evidence surface.
PUBLIC_MARKET_DATA_TOOLS = (
    "get_ticker",
    "list_tickers",
    "get_product",
    "list_products",
    "get_orderbook",
    "get_recent_trades",
    "get_candles",
    "get_mark_price_history",
    "get_oi_history",
    "get_funding_history",
    "get_options_chain",
    "get_indices",
    "get_settlement_prices",
    "get_reference_data",
)

ACCOUNT_TOOLS_REQUIRE_READ_DATA = True
TRADING_TOOLS_REQUIRE_TRADING_PERMISSION = True


class McpConfigurationError(ValueError):
    """Raised when an MCP configuration would cross a safety boundary."""


@dataclass(frozen=True)
class McpConnectionProfile:
    """Non-secret MCP connection description."""

    environment: str
    credentials_configured: bool = False

    def __post_init__(self):
        if self.environment not in MCP_ENVS:
            raise McpConfigurationError(
                "unsupported Delta MCP environment: %r" % self.environment
            )

    @property
    def production(self) -> bool:
        return self.environment == MCP_ENV_PRODUCTION


def normalize_environment(value: object) -> str:
    """Normalize only documented MCP environment names; no fallback."""
    if isinstance(value, str):
        value = value.strip().lower()
        if value in MCP_ENVS:
            return value
    raise McpConfigurationError(
        "Delta MCP environment must be india_prod or india_testnet"
    )


def server_command(environment: object = MCP_ENV_TESTNET) -> tuple[str, ...]:
    """Return the documented local stdio command.

    The environment is supplied through the process environment, not a
    command-line flag.  See :func:`server_environment`.
    """
    normalize_environment(environment)
    return (MCP_COMMAND, MCP_PACKAGE)


def server_environment(environment: object = MCP_ENV_TESTNET) -> dict[str, str]:
    """Return the non-secret environment mapping for the MCP subprocess."""
    env = normalize_environment(environment)
    return {"DELTA_MCP_ENV": env}


def assert_public_tool(tool_name: object) -> str:
    """Authorize only the documented public market-data evidence surface."""
    if not isinstance(tool_name, str) or tool_name not in PUBLIC_MARKET_DATA_TOOLS:
        raise McpConfigurationError(
            "MCP tool is outside the public market-data evidence boundary"
        )
    return tool_name


def assert_no_trading_authority(*, trading_mode: object = False) -> None:
    """Fail closed if a caller attempts to enable MCP trading authority."""
    if trading_mode is True or (
        isinstance(trading_mode, str)
        and trading_mode.strip().lower() in {"1", "true", "trade"}
    ):
        raise McpConfigurationError(
            "QuantEngine evidence adapter refuses DELTA_MCP_MODE=trade"
        )


__all__ = [
    "MCP_ENV_PRODUCTION",
    "MCP_ENV_TESTNET",
    "MCP_ENVS",
    "PUBLIC_MARKET_DATA_TOOLS",
    "McpConfigurationError",
    "McpConnectionProfile",
    "normalize_environment",
    "server_command",
    "server_environment",
    "assert_public_tool",
    "assert_no_trading_authority",
]
