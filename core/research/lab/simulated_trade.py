"""
====================================================

QuantEngine

Research Lab -- simulated trade (Phase 9B)

A FIRST-CLASS counterfactual trade record. It deliberately LOOKS
different from the production `Trade` object (it is a frozen
dataclass with provenance === COUNTERFACTUAL) so that no code
path can ever mistake it for, or submit it into, the production
TradeRegistry.

It carries:

   * experiment / opportunity / canonical identity
   * the ORIGINAL (BL) historical decision facts
   * the EXPERIMENTAL rule set applied
   * the replayed OUTCOME

SimulatedTrade never enters TradeRegistry. It is isolated to the
research lab.
====================================================
"""

from dataclasses import dataclass, field

from core.research.lab.provenance import LabProvenance


@dataclass(frozen=True)
class SimulatedTrade:
    """Immutable record of one counterfactually replayed trade."""

    provenance: str = LabProvenance.COUNTERFACTUAL.value

    experiment_id: str = ""
    opportunity_id: str = ""
    canonical_id: str = ""

    exchange: str = ""
    instrument_id: str = ""
    timeframe: str = ""
    direction: str = ""
    strategy: str = ""
    setup_id: str = ""

    # historical decision information (baseline facts)
    decision_bar: int = 0
    decision_timestamp: object = None
    source_terminal: str = ""
    source_rejection: str = ""
    original_entry: float = 0.0
    original_stop: float = 0.0
    original_target: float = 0.0
    original_rr: float = 0.0

    # experimental rule set
    experimental_entry: float = 0.0
    experimental_stop: float = 0.0
    experimental_target: float = 0.0
    experimental_rr: float = 0.0
    entry_model: str = ""
    stop_model: str = ""
    target_model: str = ""
    expiry: object = None
    changed_filters: tuple = field(default_factory=tuple)

    # outcome
    entry_reached: bool = False
    filled: bool = False
    exit_reason: str = ""
    exit_bar: int = 0
    exit_price: float = 0.0
    result: str = ""
    pnl: float = 0.0
    r: float = 0.0
    mae: float = 0.0
    mfe: float = 0.0
    bars_to_entry: int = 0
    bars_in_trade: int = 0

    # -------------------------------------------------

    @property
    def is_counterfactual(self):
        return self.provenance == LabProvenance.COUNTERFACTUAL.value

    @property
    def won(self):
        return self.result == "WIN"

    @property
    def lost(self):
        return self.result == "LOSS"

    def to_dict(self):
        return {
            "provenance": self.provenance,
            "experiment_id": self.experiment_id,
            "opportunity_id": self.opportunity_id,
            "canonical_id": self.canonical_id,
            "exchange": self.exchange,
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strategy": self.strategy,
            "setup_id": self.setup_id,
            "decision_bar": self.decision_bar,
            "decision_timestamp": self.decision_timestamp,
            "source_terminal": self.source_terminal,
            "source_rejection": self.source_rejection,
            "original_entry": self.original_entry,
            "original_stop": self.original_stop,
            "original_target": self.original_target,
            "original_rr": self.original_rr,
            "experimental_entry": self.experimental_entry,
            "experimental_stop": self.experimental_stop,
            "experimental_target": self.experimental_target,
            "experimental_rr": self.experimental_rr,
            "entry_model": self.entry_model,
            "stop_model": self.stop_model,
            "target_model": self.target_model,
            "expiry": self.expiry,
            "changed_filters": list(self.changed_filters),
            "entry_reached": self.entry_reached,
            "filled": self.filled,
            "exit_reason": self.exit_reason,
            "exit_bar": self.exit_bar,
            "exit_price": self.exit_price,
            "result": self.result,
            "pnl": self.pnl,
            "R": self.r,
            "MAE": self.mae,
            "MFE": self.mfe,
            "bars_to_entry": self.bars_to_entry,
            "bars_in_trade": self.bars_in_trade,
        }
