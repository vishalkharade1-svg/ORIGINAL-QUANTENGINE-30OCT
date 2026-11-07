"""Phase 27: MCP evidence context for the existing 9J discovery surface.

Research-only. Reads Phase-9I RESEARCH rows produced by the Delta MCP bridge
and summarizes which market-data domains are actually available to research.
It never creates hypotheses and never upgrades venue authentication.
"""
from __future__ import annotations

from core.research.dataset import DatasetSource, ResearchDataset

DOMAINS = (
    "product", "candles", "trades", "orderbook", "open_interest",
    "funding", "mark_price", "settlement", "options", "indices",
)


def summarize_mcp_context(dataset, symbol=""):
    """Return deterministic MCP availability without changing discovery logic."""
    dataset = dataset if dataset is not None else ResearchDataset()
    rows = dataset.rows(DatasetSource.RESEARCH)
    selected = [r for r in rows if str(r.kv.get("source", "")) == "delta_mcp_public"]
    if symbol:
        selected = [r for r in selected if r.instrument_id in (symbol, "")]

    by_domain = {}
    for row in sorted(selected, key=lambda r: (str(r.kv.get("mcp_domain", "")), r.row_id)):
        domain = str(row.kv.get("mcp_domain", ""))
        if domain in DOMAINS and domain not in by_domain:
            by_domain[domain] = row

    statuses = {
        domain: str(by_domain[domain].result)
        if domain in by_domain else "UNAVAILABLE"
        for domain in DOMAINS
    }
    return {
        "source": "delta_mcp_public",
        "symbol": symbol or "ALL",
        "domains": dict(statuses),
        "available_domains": tuple(sorted(d for d, s in statuses.items()
                                           if s in ("VERIFIED", "PARTIAL"))),
        "verified_domains": tuple(sorted(d for d, s in statuses.items()
                                          if s == "VERIFIED")),
        "unavailable_domains": tuple(sorted(d for d, s in statuses.items()
                                             if s == "UNAVAILABLE")),
        "venue_authentication": "UNVERIFIED",
        "research_only": True,
        "hypothesis_generation": "UNCHANGED",
    }


def context_limitations(context):
    """Deterministic human-readable limitations for a 9J report."""
    if not context:
        return ()
    available = ", ".join(context["available_domains"]) or "none"
    unavailable = ", ".join(context["unavailable_domains"]) or "none"
    return (
        "Delta MCP research context available domains: %s." % available,
        "Delta MCP research context unavailable domains: %s." % unavailable,
        "Delta MCP venue authentication remains UNVERIFIED; MCP context "
        "cannot by itself certify venue authenticity or production evidence.",
        "MCP context does not create hypotheses or bypass 9J/9K/9L/9M gates.",
    )
