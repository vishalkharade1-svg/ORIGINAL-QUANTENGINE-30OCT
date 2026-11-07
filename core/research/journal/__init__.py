"""
====================================================

QuantEngine

Research Journal (Phase 9A)

An append-safe, deterministic research record of every market
opportunity lifecycle (setup -> eligibility -> order ->
fill/expiry/invalidation -> trade -> close).

The journal is a pure OBSERVER of the frozen engine: it reads
authoritative state (PipelineContext + TradeRegistry) at the
end of every bar, appends RESEARCH events, and assembles
immutable OpportunityRecords. It never alters a decision.

Recorded facts are OBSERVED ONLY. Counterfactual / simulation
outcomes (SimulatedTrade, CounterfactualOutcome,
StrategyExperiment) belong to later phases and are NOT
represented here.

Modules
-------
research_enums   -- Provenance / lifecycle / result enums
research_event   -- deterministic immutable lifecycle event
setup_record     -- observed setup facts (incl. rejections)
order_record     -- observed order lifecycle + excursion facts
trade_record     -- observed trade outcome (R/PnL/MAE/MFE)
opportunity_record -- immutable unified lifecycle view
research_repository -- append-safe deterministic storage
research_journal -- the per-bar observer/reconciler
journal_query    -- read-only filter surface
journal_summary  -- aggregate counts over observed facts
====================================================
"""

from core.research.journal.research_enums import (
    Provenance,
    SetupLifecycle,
    OrderLifecycle,
    Result,
    EntryReached,
    EventType,
)
from core.research.journal.research_event import ResearchEvent
from core.research.journal.setup_record import SetupRecord
from core.research.journal.order_record import OrderRecord
from core.research.journal.trade_record import TradeRecord
from core.research.journal.opportunity_record import OpportunityRecord
from core.research.journal.research_repository import ResearchRepository
from core.research.journal.research_journal import ResearchJournal
from core.research.journal.journal_query import JournalQuery
from core.research.journal.journal_summary import JournalSummary

__all__ = [
    "Provenance",
    "SetupLifecycle",
    "OrderLifecycle",
    "Result",
    "EntryReached",
    "EventType",
    "ResearchEvent",
    "SetupRecord",
    "OrderRecord",
    "TradeRecord",
    "OpportunityRecord",
    "ResearchRepository",
    "ResearchJournal",
    "JournalQuery",
    "JournalSummary",
]
