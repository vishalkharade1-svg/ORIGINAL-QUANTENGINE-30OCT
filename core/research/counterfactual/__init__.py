"""
====================================================

QuantEngine

Counterfactual Simulation (Phase 9C)

Deterministic, research-only counterfactual simulator. Given an
original OpportunityRecord (from the frozen Phase 9A Journal),
historical candles, and a CounterfactualConfig, it evaluates what
would have happened under an explicitly specified alternative
configuration -- WITHOUT changing the original opportunity or any
production state.

Reuses (does not duplicate):
   * frozen 9B SimulatedTrade / CounterfactualOutcome / provenance /
     exit-geometry / experiment-id machinery
   * frozen canonical production entry deciders
     (core/execution/entry_model.get_entry_model)

LEDGER BOUNDARY: results carry provenance === COUNTERFACTUAL and
never enter TradeRegistry / Account / PortfolioState / SharedCapital
/ paper / live / production ledger.

RESEARCH ONLY: no AI, no ML, no optimizer, no auto-parameter
selection, no strategy scoring, no production changes.
====================================================
"""

from core.research.counterfactual.counterfactual_config import (
    CounterfactualConfig,
    SUPPORTED_ENTRY_MODELS,
    KNOWN_UNSUPPORTED_ENTRY_MODELS,
    setup_view,
)
from core.research.counterfactual.opportunity_categories import (
    classify_opportunity,
    FILLED,
    REJECTED,
    MISSED_CONTINUATION,
    INVALIDATED,
    ENTRY_NOT_REACHED,
    NON_EVALUABLE,
)
from core.research.counterfactual.opportunity_simulator import (
    OpportunitySimulator,
)
from core.research.counterfactual.counterfactual_runner import (
    CounterfactualRunner,
)
from core.research.counterfactual.simulated_trade import (
    SimulatedTrade,
    COUNTERFACTUAL,
)
from core.research.counterfactual.counterfactual_outcome import (
    CounterfactualOutcome,
)

__all__ = [
    "CounterfactualConfig",
    "SUPPORTED_ENTRY_MODELS",
    "KNOWN_UNSUPPORTED_ENTRY_MODELS",
    "setup_view",
    "classify_opportunity",
    "FILLED",
    "REJECTED",
    "MISSED_CONTINUATION",
    "INVALIDATED",
    "ENTRY_NOT_REACHED",
    "NON_EVALUABLE",
    "OpportunitySimulator",
    "CounterfactualRunner",
    "SimulatedTrade",
    "CounterfactualOutcome",
    "COUNTERFACTUAL",
]
