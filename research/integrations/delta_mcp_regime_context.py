"""Phase 28: Delta MCP context for the existing 9K regime layer.

Research-only.  MCP observations may tell 9K which *external market-data
contexts* are available, but they never manufacture a regime label.  Actual
9K regime labels continue to come only from the bounded decision-time
regime detector and its existing minimum-sample gates.
"""
from __future__ import annotations

from research.integrations.delta_mcp_discovery_context import (
    DOMAINS,
    summarize_mcp_context,
)

# Public domains that can provide contextual evidence to future 9K analyses.
# They are deliberately not mapped to TREND/RANGE/etc.; such a mapping would
# invent semantics not established by the MCP response itself.
CONDITIONING_DOMAINS = (
    "trades",
    "orderbook",
    "open_interest",
    "funding",
    "mark_price",
    "settlement",
    "options",
    "indices",
)


def summarize_regime_context(dataset, symbol=""):
    base = summarize_mcp_context(dataset, symbol=symbol)
    available = set(base["available_domains"])
    return {
        "source": base["source"],
        "symbol": base["symbol"],
        "available_domains": tuple(sorted(available)),
        "conditioning_domains_available": tuple(
            sorted(d for d in CONDITIONING_DOMAINS if d in available)
        ),
        "regime_labels_from_mcp": (),
        "venue_authentication": base["venue_authentication"],
        "research_only": True,
        "regime_detection": "UNCHANGED",
    }


def regime_context_limitations(context):
    if not context:
        return ()
    available = ", ".join(context["conditioning_domains_available"]) or "none"
    return (
        "Delta MCP conditioning domains available to 9K readback: %s." % available,
        "MCP observations do not map directly to 9K regime labels; TREND/RANGE "
        "and other regime dimensions remain detector-derived and data-gated.",
        "Delta MCP venue authentication remains UNVERIFIED; contextual data "
        "cannot by itself establish a regime-conditioned trading claim.",
        "MCP conditioning context cannot bypass 9K walk-forward, multiple-testing, "
        "sample-size, 9M OOS, or production-readiness gates.",
    )
