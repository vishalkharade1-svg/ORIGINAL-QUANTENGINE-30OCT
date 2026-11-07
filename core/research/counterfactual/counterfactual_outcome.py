"""
====================================================

QuantEngine

Counterfactual Simulation -- counterfactual outcome (Phase 9C)

REUSE, NOT DUPLICATION: the CounterfactualOutcome result model
lives in the frozen Phase 9B layer
(core/research/lab/counterfactual.py). This module re-exports it
plus the 9C opportunity-category vocabulary so the Phase 9C public
surface is self-contained.

The simulator sets `.category` (opportunity_categories) on the
outcome; the provenance of any materialized trade is COUNTERFACTUAL.
====================================================
"""

from core.research.lab.counterfactual import CounterfactualOutcome
from core.research.counterfactual.opportunity_categories import (
    FILLED,
    REJECTED,
    MISSED_CONTINUATION,
    INVALIDATED,
    ENTRY_NOT_REACHED,
    NON_EVALUABLE,
    classify_opportunity,
)

__all__ = [
    "CounterfactualOutcome",
    "FILLED",
    "REJECTED",
    "MISSED_CONTINUATION",
    "INVALIDATED",
    "ENTRY_NOT_REACHED",
    "NON_EVALUABLE",
    "classify_opportunity",
]
