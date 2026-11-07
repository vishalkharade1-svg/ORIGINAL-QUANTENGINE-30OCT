"""Research-only bridge from Delta MCP evidence bundles into Phase-9I rows.

The bridge consumes an already-built EvidenceBundle. It never invokes MCP,
never authenticates a venue, and never changes production/runtime decisions.
Every domain remains visible, including UNAVAILABLE/PARTIAL states.
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from core.research.dataset import ResearchDataset, ResearchRow, DatasetSource
from .delta_mcp_evidence_bundle import DOMAINS, EvidenceBundle

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


def _stable_id(payload: object) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def bundle_to_rows(bundle: EvidenceBundle) -> tuple[ResearchRow, ...]:
    """Convert one MCP evidence bundle into deterministic 9I RESEARCH rows."""
    by_domain = {}
    for observation in bundle.observations:
        domain = _TOOL_DOMAIN.get(observation.tool)
        if domain is None or domain in by_domain:
            continue
        by_domain[domain] = observation

    rows = []
    for domain in DOMAINS:
        observation = by_domain.get(domain)
        status = dict(bundle.domain_status).get(domain, "UNAVAILABLE")
        if observation is None:
            source_identity = _stable_id({"bundle": bundle.content_identity, "domain": domain, "status": status})
            tool = ""
            observed = {}
            missing = ["observation"]
            content_identity = source_identity
        else:
            source_identity = observation.content_identity
            tool = observation.tool
            observed = dict(observation.observed)
            missing = list(observation.missing)
            content_identity = observation.content_identity

        kv = {
            "source": "delta_mcp_public",
            "mcp_domain": domain,
            "mcp_tool": tool,
            "observation_status": status,
            "venue_authentication": bundle.venue_authentication,
            "bundle_identity": bundle.content_identity,
            "observation_identity": content_identity,
            "missing": sorted(missing),
            "consistency_errors": list(bundle.consistency_errors),
        }
        measured = {}
        for key in ("row_count", "valid_rows", "invalid_rows", "min_time", "max_time", "unique_timestamps"):
            if key in observed:
                measured[key] = observed[key]

        row = ResearchRow(
            source=DatasetSource.RESEARCH,
            observation_id="MCP-%s-%s" % (bundle.symbol, domain),
            instrument_id=bundle.symbol,
            timeframe="",
            strategy="",
            decision_bar=observed.get("max_time"),
            category="DELTA_MCP_%s" % domain.upper(),
            result=status,
            source_id=source_identity,
            kv=kv,
            measured=measured,
        )
        rows.append(row)
    return tuple(rows)


def bundle_to_dataset(bundle: EvidenceBundle) -> ResearchDataset:
    """Return an append-only 9I dataset containing the bundle's research rows."""
    return ResearchDataset(bundle_to_rows(bundle))


__all__ = ["bundle_to_rows", "bundle_to_dataset"]
