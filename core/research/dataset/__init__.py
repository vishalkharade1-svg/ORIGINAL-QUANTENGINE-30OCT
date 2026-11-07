"""
====================================================

QuantEngine

Unified Research Dataset / Knowledge & Data Intelligence (Phase 9I)

A deterministic, research-only knowledge/data layer that unifies the
frozen 9A-9H evidence into one queryable research dataset:

   * ResearchRow     -- the single normalized research-fact model with
                        stable deterministic ids (sha1, no UUID).
   * DatasetSource   -- closed vocabulary of the seven unified sources
                        (JOURNAL / COUNTERFACTUAL / ANALYSIS /
                        INTELLIGENCE / FEATURE / ML / RESEARCH).
   * collectors      -- read-only builders that normalize each 9A-9H
                        artifact into ResearchRow lists.
   * ResearchDataset -- append-only container with deterministic
                        persistence (atomic JSON, corrupt -> fresh).
   * queries         -- the knowledge layer: entry_pipeline_breakdown
                        (why only some setups entered), recovery_
                        candidates (which missed/rejected setups could
                        have been captured profitably under alternative
                        9B/9C configs), unify_by_observation (cross-
                        source join), aggregate, and answer_context
                        (compact evidence for 9H).

Boundaries: research-only; reads every 9A-9H surface read-only; never
imports production internals, never orders, never looks ahead, never
auto-promotes. Every result is ASSOCIATION evidence for experimentation
planning -- it is not a trade directive and does not promote any
configuration to production. 7E NO-GO stays untouched.
====================================================
"""

from core.research.dataset.row import (
    ResearchRow,
    row_from_dict,
    DatasetSource,
    SOURCES,
)
from core.research.dataset.dataset import ResearchDataset
from core.research.dataset import collectors
from core.research.dataset import queries
from core.research.dataset.collectors import (
    collect_journal,
    collect_counterfactual,
    collect_analysis,
    collect_intelligence,
    collect_features,
    collect_ml,
    collect_researcher,
)
from core.research.dataset.queries import (
    entry_pipeline_breakdown,
    recovery_candidates,
    unify_by_observation,
    aggregate,
    answer_context,
)

__all__ = [
    "ResearchRow",
    "row_from_dict",
    "DatasetSource",
    "SOURCES",
    "ResearchDataset",
    "collectors",
    "queries",
    "collect_journal",
    "collect_counterfactual",
    "collect_analysis",
    "collect_intelligence",
    "collect_features",
    "collect_ml",
    "collect_researcher",
    "entry_pipeline_breakdown",
    "recovery_candidates",
    "unify_by_observation",
    "aggregate",
    "answer_context",
]
