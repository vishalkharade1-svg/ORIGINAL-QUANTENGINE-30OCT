"""Canonical, research-only normalization of Delta MCP public observations.

This module does not invoke MCP, REST, WebSocket, or trading APIs. It accepts
already-received MCP tool responses and converts them into deterministic,
credential-free evidence records. Unknown fields are not invented; missing
required fields make the corresponding observation UNAVAILABLE.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any

from .delta_mcp import assert_no_trading_authority, assert_public_tool

SCHEMA = "quantengine.delta-mcp-observation.v1"
STATUS = ("VERIFIED", "PARTIAL", "UNAVAILABLE")


class ObservationError(ValueError):
    """Raised when an MCP public observation violates its schema."""


@dataclasses.dataclass(frozen=True)
class Observation:
    tool: str
    symbol: str | None
    status: str
    observed: tuple[tuple[str, Any], ...]
    missing: tuple[str, ...]
    content_identity: str
    source: str = "delta_mcp_public"

    def __post_init__(self):
        assert_public_tool(self.tool)
        if self.status not in STATUS:
            raise ObservationError("invalid observation status")
        if not isinstance(self.observed, tuple):
            raise ObservationError("observed must be tuple")
        if not isinstance(self.missing, tuple):
            raise ObservationError("missing must be tuple")
        if not isinstance(self.content_identity, str) or len(self.content_identity) != 64:
            raise ObservationError("content_identity must be sha256 hex")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "tool": self.tool,
            "symbol": self.symbol,
            "status": self.status,
            "observed": dict(self.observed),
            "missing": list(self.missing),
            "content_identity": self.content_identity,
            "source": self.source,
        }


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def _identity(payload: Any) -> str:
    body = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _result(response: Any) -> Any:
    if not isinstance(response, dict):
        raise ObservationError("MCP response must be an object")
    if response.get("success") is False:
        raise ObservationError("MCP response reports failure")
    if response.get("success") is not True and "result" not in response:
        raise ObservationError("MCP response missing success/result envelope")
    if "result" not in response:
        raise ObservationError("MCP response missing result")
    return response["result"]


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ObservationError("%s is not numeric" % field)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ObservationError("%s is not numeric" % field) from exc
    if not number.is_finite():
        raise ObservationError("%s is not finite" % field)
    return number


def _rows(result: Any) -> list[Any]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("data", "rows", "candles", "trades", "history", "result"):
            value = result.get(key)
            if isinstance(value, list):
                return value
    raise ObservationError("result does not contain a row list")


def _symbol(result: Any, requested_symbol: str | None) -> str | None:
    if requested_symbol is not None and not isinstance(requested_symbol, str):
        raise ObservationError("requested_symbol must be str or None")
    if isinstance(result, dict):
        observed = result.get("symbol")
        if observed is not None and not isinstance(observed, str):
            raise ObservationError("observed symbol must be str")
        if observed and requested_symbol and observed != requested_symbol:
            raise ObservationError("symbol mismatch")
        return observed or requested_symbol
    return requested_symbol


def _observation(tool: str, symbol: str | None, status: str, observed: dict[str, Any], missing: list[str], identity_payload: Any) -> Observation:
    return Observation(
        tool=tool,
        symbol=symbol,
        status=status,
        observed=tuple(sorted(observed.items())),
        missing=tuple(sorted(set(missing))),
        content_identity=_identity(identity_payload),
    )


def normalize_public_response(tool: str, response: Any, *, requested_symbol: str | None = None) -> Observation:
    """Normalize one documented public Delta MCP response.

    The adapter is deliberately summary-oriented. It records counts and
    numeric extrema/identities rather than pretending absent venue fields
    exist. The original MCP response must remain available to the caller if
    full evidence retention is required.
    """
    assert_public_tool(tool)
    assert_no_trading_authority(trading_mode=False)
    result = _result(response)
    symbol = _symbol(result, requested_symbol)

    if tool in {"get_product", "get_ticker", "get_reference_data"}:
        if not isinstance(result, dict):
            raise ObservationError("%s result must be object" % tool)
        observed = {}
        for key in ("symbol", "id", "state", "contract_type", "tick_size", "contract_value", "maker_commission_rate", "taker_commission_rate", "funding_method", "funding_clamp_value"):
            if key in result and result[key] is not None:
                observed[key] = _canonical(result[key])
        required = ("symbol",) if tool != "get_reference_data" else ()
        missing = [key for key in required if key not in observed]
        status = "VERIFIED" if not missing else "PARTIAL"
        return _observation(tool, symbol, status, observed, missing, result)

    if tool in {"get_candles", "get_mark_price_history", "get_funding_history", "get_oi_history", "get_settlement_prices", "get_recent_trades"}:
        rows = _rows(result)
        required = {
            "get_candles": ("time", "open", "high", "low", "close"),
            "get_mark_price_history": ("time", "price"),
            "get_funding_history": ("time", "rate"),
            "get_oi_history": ("time", "value"),
            "get_settlement_prices": ("time", "price"),
            "get_recent_trades": ("time", "price", "size"),
        }[tool]
        valid = 0
        invalid = 0
        timestamps: list[int] = []
        for row in rows:
            if not isinstance(row, dict):
                invalid += 1
                continue
            if any(key not in row for key in required):
                invalid += 1
                continue
            try:
                ts = int(row["time"])
                if ts <= 0:
                    raise ValueError
                timestamps.append(ts)
                for key in required[1:]:
                    _decimal(row[key], key)
                if tool == "get_candles":
                    if not (_decimal(row["low"], "low") <= _decimal(row["open"], "open") <= _decimal(row["high"], "high") and _decimal(row["low"], "low") <= _decimal(row["close"], "close") <= _decimal(row["high"], "high")):
                        raise ValueError
                valid += 1
            except (ObservationError, ValueError, TypeError):
                invalid += 1
        observed = {
            "row_count": len(rows),
            "valid_rows": valid,
            "invalid_rows": invalid,
        }
        if timestamps:
            observed["min_time"] = min(timestamps)
            observed["max_time"] = max(timestamps)
            observed["unique_timestamps"] = len(set(timestamps))
        status = "VERIFIED" if rows and valid == len(rows) else ("PARTIAL" if valid else "UNAVAILABLE")
        missing = [] if valid else ["valid_observations"]
        return _observation(tool, symbol, status, observed, missing, result)

    if tool in {"get_orderbook", "get_options_chain", "get_indices", "list_products", "list_tickers"}:
        rows = result if isinstance(result, list) else (result.get("data") if isinstance(result, dict) else None)
        if not isinstance(rows, list):
            rows = [result] if isinstance(result, dict) else []
        observed = {"row_count": len(rows)}
        status = "VERIFIED" if rows else "UNAVAILABLE"
        missing = [] if rows else ["public_result_rows"]
        return _observation(tool, symbol, status, observed, missing, result)

    raise ObservationError("unsupported public tool: %s" % tool)


__all__ = ["SCHEMA", "STATUS", "Observation", "ObservationError", "normalize_public_response"]
