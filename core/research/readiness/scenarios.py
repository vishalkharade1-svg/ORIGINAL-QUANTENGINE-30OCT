"""
====================================================

QuantEngine -- Phase 16 economic scenario layer.

Research-only sensitivity schedules applied to RECORDED
structural economics. Pure, deterministic functions: no
strategy logic, no thresholds, no execution, no I/O, no
randomness, no network.

Every schedule carries its provenance label:

  VERIFIED   -- measured from repository config/data
  ASSUMED    -- illustrative assumption, NOT venue-verified
  UNAVAILABLE -- no data/semantics; zero is NEVER substituted

The frozen Gate-A economics always remain the zero-cost
structural baseline; scenarios are reported ALONGSIDE it,
never merged into it.
====================================================
"""

from __future__ import annotations


def scenario_structural(gross):
    """Zero-cost structural baseline. VERIFIED (matches the
    frozen Gate-A configuration: commission 0, slippage 0)."""
    return {"net": float(gross), "fees": 0.0, "slippage": 0.0,
            "funding": 0.0, "label": "VERIFIED-zero-cost"}


def scenario_conservative_fees(gross, notional, bps=2.5):
    """Conservative taker-fee schedule. ASSUMED for research
    sensitivity only: 2.5 bps per side, round trip. This is
    NOT venue-verified and must never be presented as the
    Delta fee schedule."""
    fees = abs(float(notional)) * (bps / 10000.0) * 2.0
    return {"net": float(gross) - fees, "fees": fees,
            "slippage": 0.0, "funding": 0.0,
            "label": "ASSUMED-2.5bps-per-side"}


def scenario_conservative_slippage(gross, notional, bps=1.0):
    """Conservative slippage schedule. ASSUMED for research
    sensitivity only: 1 bp adverse per side, round trip. This
    is NOT a measured venue slippage distribution."""
    slip = abs(float(notional)) * (bps / 10000.0) * 2.0
    return {"net": float(gross) - slip, "fees": 0.0,
            "slippage": slip, "funding": 0.0,
            "label": "ASSUMED-1bp-per-side"}


def scenario_combined(gross, notional):
    """Fees + slippage. ASSUMED (sums the two schedules
    above; inherits both caveats)."""
    fees = scenario_conservative_fees(gross, notional)
    slip = scenario_conservative_slippage(gross, notional)
    return {"net": float(gross) - fees["fees"] - slip["slippage"],
            "fees": fees["fees"], "slippage": slip["slippage"],
            "funding": 0.0, "label": "ASSUMED-combined"}


def scenario_funding():
    """Funding-aware scenario. UNAVAILABLE: no funding data
    or simulator semantics exist anywhere in the repository,
    so no funding-adjusted figure can be produced. Zero is
    NEVER substituted for unavailable funding."""
    return {"net": None, "fees": None, "slippage": None,
            "funding": None, "label": "UNAVAILABLE"}
