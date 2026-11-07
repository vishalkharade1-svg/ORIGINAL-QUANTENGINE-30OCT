"""
====================================================

QuantEngine

Counterfactual Simulation -- simulated trade (Phase 9C)

REUSE, NOT DUPLICATION: the first-class SimulatedTrade model lives
in the frozen Phase 9B counterfactual layer
(core/research/lab/simulated_trade.py). This module re-exports it
here so the Phase 9C public surface carries the canonical type.

Provenance === COUNTERFACTUAL. A SimulatedTrade is a research-only
record and MUST never be inserted into TradeRegistry / Account /
PortfolioState / SharedCapital / paper / live / production ledger.
====================================================
"""

from core.research.lab.simulated_trade import SimulatedTrade
from core.research.lab.provenance import LabProvenance

COUNTERFACTUAL = LabProvenance.COUNTERFACTUAL.value

__all__ = ["SimulatedTrade", "LabProvenance", "COUNTERFACTUAL"]
