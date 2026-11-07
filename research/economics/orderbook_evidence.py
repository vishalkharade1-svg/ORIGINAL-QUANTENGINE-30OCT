"""Strict Delta L2 order-book evidence and deterministic friction metrics.

A captured book snapshot is evidence of venue market state at one instant. It
is not historical execution evidence and must never be relabeled as realized
slippage.  The module therefore exposes spread and depth/impact estimates
separately from actual fill costs.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1


def _d(value: object, name: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{name} is not numeric") from exc
    if not result.is_finite() or (positive and result <= 0) or (nonnegative and result < 0):
        raise ValueError(f"{name} is invalid")
    return result


def _canonical(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def evidence_sha256(request: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical({"request": dict(request), "result": dict(result)})).hexdigest()


def normalize_orderbook(response: Mapping[str, Any], *, symbol: str) -> dict[str, Any]:
    if not isinstance(response, Mapping):
        raise ValueError("orderbook response must be an object")
    result = response.get("result", response)
    if not isinstance(result, Mapping):
        raise ValueError("orderbook response has no result object")
    if str(result.get("symbol", symbol)) != symbol:
        raise ValueError("orderbook symbol mismatch")
    try:
        updated_at = int(result["last_updated_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("orderbook timestamp is invalid") from exc
    if updated_at <= 0:
        raise ValueError("orderbook timestamp is invalid")

    def levels(name: str, descending: bool) -> list[dict[str, str]]:
        raw = result.get(name)
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"orderbook {name} side is empty")
        out: list[dict[str, str]] = []
        previous: Decimal | None = None
        for row in raw:
            if not isinstance(row, Mapping):
                raise ValueError(f"orderbook {name} level is malformed")
            price = _d(row.get("price"), f"{name}.price", positive=True)
            size = _d(row.get("size"), f"{name}.size", nonnegative=True)
            if previous is not None and ((descending and price >= previous) or (not descending and price <= previous)):
                raise ValueError(f"orderbook {name} levels are not strictly sorted")
            previous = price
            out.append({"price": str(price), "size": str(size)})
        return out

    bids = levels("buy", True)
    asks = levels("sell", False)
    bid = _d(bids[0]["price"], "best_bid", positive=True)
    ask = _d(asks[0]["price"], "best_ask", positive=True)
    if ask <= bid:
        raise ValueError("crossed or locked orderbook")
    midpoint = (bid + ask) / Decimal("2")
    spread = ask - bid
    spread_bps = spread / midpoint * Decimal("10000")
    return {
        "symbol": symbol,
        "last_updated_at": updated_at,
        "bids": bids,
        "asks": asks,
        "best_bid": str(bid),
        "best_ask": str(ask),
        "midpoint": str(midpoint),
        "spread": str(spread),
        "spread_bps": str(spread_bps),
    }


@dataclass(frozen=True, slots=True)
class OrderbookEvidenceArtifact:
    venue: str
    symbol: str
    endpoint: str
    captured_at: str
    result: Mapping[str, Any]
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "venue": self.venue,
            "symbol": self.symbol,
            "endpoint": self.endpoint,
            "captured_at": self.captured_at,
            "result": dict(self.result),
            "evidence_sha256": self.evidence_sha256,
        }


def build_artifact(*, response: Mapping[str, Any], symbol: str, captured_at: str,
                   endpoint: str = "/v2/l2orderbook/{symbol}") -> OrderbookEvidenceArtifact:
    normalized = normalize_orderbook(response, symbol=symbol)
    request = {"symbol": symbol, "endpoint": endpoint}
    fingerprint = evidence_sha256(request, normalized)
    return OrderbookEvidenceArtifact("delta", symbol, endpoint, str(captured_at), normalized, fingerprint)


def write_artifact(artifact: OrderbookEvidenceArtifact, path: str | Path) -> None:
    Path(path).write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_and_verify(path: str | Path) -> OrderbookEvidenceArtifact:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported orderbook evidence schema")
    result = raw.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("orderbook artifact has no result")
    symbol = str(raw.get("symbol", ""))
    source = {
        "result": {
            "symbol": result.get("symbol"),
            "last_updated_at": result.get("last_updated_at"),
            "buy": result.get("bids"),
            "sell": result.get("asks"),
        }
    }
    normalized = normalize_orderbook(source, symbol=symbol)
    if dict(result) != normalized:
        raise ValueError("orderbook evidence normalization mismatch")
    expected = evidence_sha256({"symbol": symbol, "endpoint": raw.get("endpoint")}, normalized)
    if raw.get("evidence_sha256") != expected:
        raise ValueError("orderbook evidence fingerprint mismatch")
    return OrderbookEvidenceArtifact("delta", symbol, str(raw["endpoint"]), str(raw["captured_at"]), normalized, expected)
