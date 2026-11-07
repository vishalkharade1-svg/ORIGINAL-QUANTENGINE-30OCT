"""
====================================================

QuantEngine

Research Journal -- opportunity record (Phase 9A)

The immutable, unified research record for one market
opportunity lifecycle. Assembles the SetupRecord, OrderRecord
and TradeRecord facts plus a resolved terminal outcome.

Terminal outcome resolution (OBSERVED FACTS ONLY):

   * ORDER_NOT_CREATED      setup did not lead to an order
   * PENDING                an order exists, no terminal yet
   * EXPIRED / INVALIDATED /
     REJECTED / CANCELLED   order reached a non-fill terminal
   * FILLED_OPEN            filled, not yet closed
   * FILLED_CLOSED          filled and closed (trade outcome)

No counterfactual / simulation data (SimulatedTrade,
CounterfactualOutcome, StrategyExperiment) is represented here;
that is reserved for later phases.
====================================================
"""

from dataclasses import dataclass, field

from core.research.journal.research_enums import Provenance


@dataclass
class OpportunityRecord:
    """Unified immutable view of one opportunity lifecycle."""

    canonical_id: str = ""
    provenance: str = Provenance.BACKTEST.value
    exchange: str = ""
    instrument_id: str = ""
    timeframe: str = ""
    direction: str = ""
    strategy: str = ""
    setup_id: str = ""
    setup_id_parts: tuple = field(default_factory=tuple)

    setup: dict = field(default_factory=dict)
    order: dict = field(default_factory=dict)
    trade: dict = field(default_factory=dict)

    terminal_outcome: str = "ORDER_NOT_CREATED"
    hub_timestamp: object = None

    def to_dict(self):
        return {
            "canonical_id": self.canonical_id,
            "provenance": str(self.provenance),
            "exchange": self.exchange,
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strategy": self.strategy,
            "setup_id": self.setup_id,
            "terminal_outcome": self.terminal_outcome,
            "hub_timestamp": self.hub_timestamp,
            "setup": self.setup,
            "order": self.order,
            "trade": self.trade,
        }
