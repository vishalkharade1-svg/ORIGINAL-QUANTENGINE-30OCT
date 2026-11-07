"""
====================================================

QuantEngine

Research Lab -- counterfactual outcome (Phase 9B)

The structured result of replaying ONE historical opportunity
under an ExperimentConfig. Carries the baseline terminal state
(what actually happened), the experimental rule set, and the
replayed outcome.

`to_trade()` materializes an immutable SimulatedTrade. Both are
COUNTERFACTUAL and isolated from the production ledger.
====================================================
"""

from dataclasses import dataclass, field

from core.research.lab.simulated_trade import SimulatedTrade


@dataclass
class CounterfactualOutcome:
    """Result of replaying one opportunity under one config."""

    experiment_id: str = ""
    opportunity_id: str = ""
    config: object = None

    # baseline immutability (what the frozen production actually did)
    baseline_terminal: str = ""
    baseline_rejection: str = ""
    baseline_eligible: bool = True

    # experimental target economics
    experimental_entry: float = 0.0
    experimental_stop: float = 0.0
    experimental_target: float = 0.0
    experimental_rr: float = 0.0

    decision_bar: int = 0
    n_bars_available: int = 0

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

    canonical_id: str = ""
    exchange: str = ""
    instrument_id: str = ""
    timeframe: str = ""
    direction: str = ""
    strategy: str = ""
    setup_id: str = ""

    warnings: list = field(default_factory=list)

    # -------------------------------------------------

    @property
    def settled(self):
        return self.result in ("WIN", "LOSS")

    def to_trade(self):
        """Materialize the immutable SimulatedTrade for this
        outcome. It is isolated from the production TradeRegistry."""
        from core.research.lab.simulated_trade import SimulatedTrade

        c = self.config
        return SimulatedTrade(
            experiment_id=self.experiment_id,
            opportunity_id=self.opportunity_id,
            canonical_id=self.canonical_id,
            exchange=self.exchange,
            instrument_id=self.instrument_id,
            timeframe=self.timeframe,
            direction=self.direction,
            strategy=self.strategy,
            setup_id=self.setup_id,
            decision_bar=self.decision_bar,
            source_terminal=self.baseline_terminal,
            source_rejection=self.baseline_rejection,
            experimental_entry=self.experimental_entry,
            experimental_stop=self.experimental_stop,
            experimental_target=self.experimental_target,
            experimental_rr=self.experimental_rr,
            entry_model=getattr(c, "entry_model", ""),
            stop_model=getattr(c, "stop_mode", ""),
            target_model=getattr(c, "target_mode", ""),
            expiry=getattr(c, "expiry", None),
            changed_filters=getattr(c, "changed_filters", ()),
            entry_reached=self.entry_reached,
            filled=self.filled,
            exit_reason=self.exit_reason,
            exit_bar=self.exit_bar,
            exit_price=self.exit_price,
            result=self.result,
            pnl=self.pnl,
            r=self.r,
            mae=self.mae,
            mfe=self.mfe,
            bars_to_entry=self.bars_to_entry,
            bars_in_trade=self.bars_in_trade,
        )

    def to_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "opportunity_id": self.opportunity_id,
            "canonical_id": self.canonical_id,
            "exchange": self.exchange,
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strategy": self.strategy,
            "setup_id": self.setup_id,
            "baseline_terminal": self.baseline_terminal,
            "baseline_rejection": self.baseline_rejection,
            "baseline_eligible": self.baseline_eligible,
            "experimental_entry": self.experimental_entry,
            "experimental_stop": self.experimental_stop,
            "experimental_target": self.experimental_target,
            "experimental_rr": self.experimental_rr,
            "decision_bar": self.decision_bar,
            "n_bars_available": self.n_bars_available,
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
            "config": self.config.to_dict() if self.config else {},
            "warnings": list(self.warnings),
        }
