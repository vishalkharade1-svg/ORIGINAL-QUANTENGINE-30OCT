"""
====================================================

QuantEngine

Research Analyzer -- baseline view (Phase 9D)

A thin, read-only adapter that maps a frozen Phase 9A
OpportunityRecord into the OUTCOME surface the deterministic
metric bundles read (the same surface a 9C CounterfactualOutcome
exposes). This is what lets BASELINE (what the frozen production
actually did) and EXPERIMENT (what the counterfactual replay
produced) be measured with ONE formula surface.

Baseline facts are taken ONLY from the record's authoritative
trade facts; nothing is fabricated. Filled records without a
terminal trade result remain UNSETTLED. MAE / MFE are kept as
None when the authoritative journal does not provide them (they
are then excluded from averages, never invented).

No mutation: the source OpportunityRecord is never written.
====================================================
"""

from dataclasses import dataclass

from core.research.journal.research_enums import Result
from core.research.counterfactual.opportunity_categories import (
    classify_opportunity,
    FILLED,
)

_FILLED_TERMINALS = ("FILLED_OPEN", "FILLED_CLOSED")


@dataclass(frozen=True)
class BaselineOutcome:
    """Outcome-shaped view of ONE baseline OpportunityRecord."""

    filled: bool = False
    result: str = Result.UNSETTLED.value
    pnl: float = 0.0
    r: float = 0.0
    mae: object = None
    mfe: object = None
    bars_to_entry: object = None
    bars_in_trade: int = 0
    exit_bar: int = 0
    decision_bar: int = 0
    exit_price: float = 0.0

    category: str = ""
    canonical_id: str = ""
    exchange: str = ""
    instrument_id: str = ""
    timeframe: str = ""
    direction: str = ""
    strategy: str = ""
    setup_id: str = ""
    experiment_id: str = ""

    def to_dict(self):
        return {
            "filled": self.filled,
            "result": self.result,
            "pnl": self.pnl,
            "r": self.r,
            "MAE": self.mae,
            "MFE": self.mfe,
            "bars_to_entry": self.bars_to_entry,
            "bars_in_trade": self.bars_in_trade,
            "exit_bar": self.exit_bar,
            "decision_bar": self.decision_bar,
            "category": self.category,
            "canonical_id": self.canonical_id,
            "exchange": self.exchange,
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "strategy": self.strategy,
            "setup_id": self.setup_id,
        }


def _r_from_trade(trade):
    """Deterministic R for a filled record: prefer the journal's
    authoritative r; fall back to pnl / risk_amount (None-guarded,
    never NaN)."""
    r = trade.get("r")
    if r is not None:
        try:
            return float(r)
        except (TypeError, ValueError):
            return 0.0
    pnl = trade.get("pnl") or 0.0
    risk = trade.get("risk_amount")
    if risk:
        try:
            return float(pnl) / float(risk)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def baseline_view(record):
    """Immutable BASELINE outcome view of an OpportunityRecord.

    Read-only: never mutates the record; fail-tolerant (an empty /
    malformed trade dict yields a deterministic UNSETTLED zero view,
    not a crash).
    """
    terminal = (getattr(record, "terminal_outcome", "") or "").upper()
    setup = getattr(record, "setup", None) or {}
    trade = getattr(record, "trade", None) or {}
    filled = terminal in _FILLED_TERMINALS

    if filled:
        result = str(trade.get("result") or Result.UNSETTLED.value)
        pnl = trade.get("pnl")
        pnl = float(pnl) if pnl is not None else 0.0
        r = _r_from_trade(trade)
        mae = trade.get("mae")
        mfe = trade.get("mfe")
        bars_in_trade = int(trade.get("bars_held") or 0)
        exit_bar = int(trade.get("exit_bar") or 0)
        exit_price = trade.get("exit_price")
        exit_price = float(exit_price) if exit_price is not None else 0.0
        entry_bar = trade.get("entry_bar")
        decision_bar = int(setup.get("bar") or 0)
        bars_to_entry = None
        if entry_bar is not None and isinstance(entry_bar, int) and decision_bar is not None:
            bars_to_entry = max(entry_bar - decision_bar, 0)
    else:
        result = Result.UNSETTLED.value
        pnl = 0.0
        r = 0.0
        mae = None
        mfe = None
        bars_in_trade = 0
        exit_bar = 0
        exit_price = 0.0
        decision_bar = int(setup.get("bar") or 0)
        bars_to_entry = None

    return BaselineOutcome(
        filled=filled,
        result=result,
        pnl=pnl,
        r=r,
        mae=mae,
        mfe=mfe,
        bars_to_entry=bars_to_entry,
        bars_in_trade=bars_in_trade,
        exit_bar=exit_bar,
        decision_bar=decision_bar,
        exit_price=exit_price,
        category=classify_opportunity(record),
        canonical_id=getattr(record, "canonical_id", "") or "",
        exchange=getattr(record, "exchange", "") or "",
        instrument_id=getattr(record, "instrument_id", "") or "",
        timeframe=getattr(record, "timeframe", "") or "",
        direction=getattr(record, "direction", "") or "",
        strategy=getattr(record, "strategy", "") or "",
        setup_id=getattr(record, "setup_id", "") or "",
    )