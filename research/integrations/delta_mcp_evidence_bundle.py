"""Deterministic research bundle for Delta MCP public observations.

This module never invokes MCP and never grants trading authority.  It combines
already-normalized public observations into a single evidence bundle while
preserving domain-level availability.  A bundle is not venue authentication.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any, Iterable

from .delta_mcp_observations import Observation, STATUS

SCHEMA = "quantengine.delta-mcp-evidence-bundle.v1"
DOMAINS = (
    "product",
    "candles",
    "trades",
    "orderbook",
    "open_interest",
    "funding",
    "mark_price",
    "settlement",
    "options",
    "indices",
)
_TOOL_DOMAIN = {
    "get_product": "product",
    "get_candles": "candles",
    "get_recent_trades": "trades",
    "get_orderbook": "orderbook",
    "get_oi_history": "open_interest",
    "get_funding_history": "funding",
    "get_mark_price_history": "mark_price",
    "get_settlement_prices": "settlement",
    "get_options_chain": "options",
    "get_indices": "indices",
}


class EvidenceBundleError(ValueError):
    pass


def _identity(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class EvidenceBundle:
    symbol: str
    observations: tuple[Observation, ...]
    domain_status: tuple[tuple[str, str], ...]
    consistency_errors: tuple[str, ...]
    content_identity: str
    venue_authentication: str = "UNVERIFIED"

    def __post_init__(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise EvidenceBundleError("symbol required")
        if self.venue_authentication != "UNVERIFIED":
            raise EvidenceBundleError("bundle cannot self-certify venue authentication")
        for domain, status in self.domain_status:
            if domain not in DOMAINS:
                raise EvidenceBundleError("unknown domain")
            if status not in STATUS and status != "UNAVAILABLE":
                raise EvidenceBundleError("invalid domain status")
        if len(self.content_identity) != 64:
            raise EvidenceBundleError("invalid content identity")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "symbol": self.symbol,
            "observations": [o.to_dict() for o in self.observations],
            "domain_status": dict(self.domain_status),
            "consistency_errors": list(self.consistency_errors),
            "content_identity": self.content_identity,
            "venue_authentication": self.venue_authentication,
        }


def build_evidence_bundle(observations: Iterable[Observation], *, symbol: str) -> EvidenceBundle:
    obs = tuple(observations)
    errors: list[str] = []
    seen_domains: dict[str, Observation] = {}
    for item in obs:
        if item.symbol and item.symbol != symbol:
            errors.append(f"symbol_mismatch:{item.tool}:{item.symbol}")
        domain = _TOOL_DOMAIN.get(item.tool)
        if domain is None:
            errors.append(f"unsupported_tool:{item.tool}")
            continue
        if domain in seen_domains:
            errors.append(f"duplicate_domain:{domain}")
        else:
            seen_domains[domain] = item

    domain_status: dict[str, str] = {}
    for domain in DOMAINS:
        item = seen_domains.get(domain)
        domain_status[domain] = item.status if item else "UNAVAILABLE"

    payload = {
        "schema": SCHEMA,
        "symbol": symbol,
        "observations": [
            {"tool": o.tool, "symbol": o.symbol, "status": o.status, "content_identity": o.content_identity}
            for o in obs
        ],
        "domain_status": domain_status,
        "consistency_errors": sorted(set(errors)),
    }
    return EvidenceBundle(
        symbol=symbol,
        observations=obs,
        domain_status=tuple(sorted(domain_status.items())),
        consistency_errors=tuple(sorted(set(errors))),
        content_identity=_identity(payload),
    )


__all__ = ["SCHEMA", "DOMAINS", "EvidenceBundle", "EvidenceBundleError", "build_evidence_bundle"]
